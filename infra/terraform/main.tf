# =============================================================================
# PrevaIQ — Azure Infrastructure (Terraform)
# Same resources as ../main.bicep. Pick one of the two tools per environment.
# =============================================================================

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

# -----------------------------------------------------------------------------
# Log Analytics + Application Insights (APM and OpenTelemetry traces for the agents)
# -----------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.prefix}"
  location            = local.location
  resource_group_name = local.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "this" {
  name                = "appi-${local.prefix}"
  location            = local.location
  resource_group_name = local.resource_group_name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  retention_in_days   = 30
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# User-assigned managed identity shared by both Container Apps
# -----------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "this" {
  name                = "id-${local.prefix}"
  location            = local.location
  resource_group_name = local.resource_group_name
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# Container Registry
# -----------------------------------------------------------------------------
resource "azurerm_container_registry" "this" {
  name                = "acr${var.project_name}${var.environment}"
  location            = local.location
  resource_group_name = local.resource_group_name
  sku                 = var.acr_sku
  admin_enabled       = false
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# Key Vault: the Web IQ secret is written out-of-band by infra/set-webiq-secret.ps1, never by IaC
# -----------------------------------------------------------------------------
resource "azurerm_key_vault" "this" {
  name                       = "kv-${local.prefix}"
  location                   = local.location
  resource_group_name        = local.resource_group_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 90
  purge_protection_enabled   = true
  tags                       = local.tags

  public_network_access_enabled = local.public_access

  dynamic "network_acls" {
    for_each = local.restrict_public ? [1] : []

    content {
      default_action = "Deny"
      bypass         = "AzureServices"
      ip_rules       = var.admin_ip_ranges
    }
  }
}

# -----------------------------------------------------------------------------
# Storage account + blob containers (identity-only access: shared keys are disabled)
# -----------------------------------------------------------------------------
resource "azurerm_storage_account" "this" {
  name                            = substr("st${var.project_name}${local.unique_suffix}", 0, 24)
  location                        = local.location
  resource_group_name             = local.resource_group_name
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  https_traffic_only_enabled      = true
  public_network_access           = local.public_access ? "Enabled" : "Disabled"
  tags                            = local.tags

  # Selected networks: the Foundry blob connection reaches the account as a trusted resource instance.
  dynamic "network_rules" {
    for_each = local.restrict_public ? [1] : []

    content {
      default_action = "Deny"
      bypass         = ["AzureServices"]
      ip_rules       = var.admin_ip_ranges

      private_link_access {
        endpoint_resource_id = azurerm_cognitive_account.foundry.id
      }
    }
  }
}

resource "azurerm_storage_container" "this" {
  for_each = toset(local.blob_containers)

  name               = each.key
  storage_account_id = azurerm_storage_account.this.id
}

# -----------------------------------------------------------------------------
# RBAC. The apps use the user-assigned identity; the Foundry project identity backs the
# project's Entra-authenticated connections (Storage, AI Search).
# -----------------------------------------------------------------------------
locals {
  app_identity     = azurerm_user_assigned_identity.this.principal_id
  project_identity = azurerm_cognitive_account_project.foundry.identity[0].principal_id

  identity_roles = {
    acr_pull                   = { principal_id = local.app_identity, scope = azurerm_container_registry.this.id, role = "AcrPull" }
    keyvault_secrets_user      = { principal_id = local.app_identity, scope = azurerm_key_vault.this.id, role = "Key Vault Secrets User" }
    storage_blob_contributor   = { principal_id = local.app_identity, scope = azurerm_storage_account.this.id, role = "Storage Blob Data Contributor" }
    openai_user                = { principal_id = local.app_identity, scope = azurerm_cognitive_account.foundry.id, role = "Cognitive Services OpenAI User" }
    cognitive_services_user    = { principal_id = local.app_identity, scope = azurerm_cognitive_account.foundry.id, role = "Cognitive Services User" }
    search_index_contributor   = { principal_id = local.app_identity, scope = azurerm_search_service.this.id, role = "Search Index Data Contributor" }
    search_service_contributor = { principal_id = local.app_identity, scope = azurerm_search_service.this.id, role = "Search Service Contributor" }

    project_storage_blob_contributor   = { principal_id = local.project_identity, scope = azurerm_storage_account.this.id, role = "Storage Blob Data Contributor" }
    project_search_index_contributor   = { principal_id = local.project_identity, scope = azurerm_search_service.this.id, role = "Search Index Data Contributor" }
    project_search_service_contributor = { principal_id = local.project_identity, scope = azurerm_search_service.this.id, role = "Search Service Contributor" }
  }

  # Data-plane access for the people or pipelines running deploy.ps1, set-webiq-secret.ps1 and the maintenance scripts.
  admin_role_targets = {
    foundry  = { scope = azurerm_cognitive_account.foundry.id, role = "Cognitive Services User" }
    keyvault = { scope = azurerm_key_vault.this.id, role = "Key Vault Secrets Officer" }
    storage  = { scope = azurerm_storage_account.this.id, role = "Storage Blob Data Contributor" }
  }

  admin_roles = {
    for pair in setproduct(var.admin_principal_ids, keys(local.admin_role_targets)) :
    "${pair[0]}/${pair[1]}" => merge(local.admin_role_targets[pair[1]], { principal_id = pair[0] })
  }
}

resource "azurerm_role_assignment" "identity" {
  for_each = local.identity_roles

  scope                            = each.value.scope
  role_definition_name             = each.value.role
  principal_id                     = each.value.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "admin" {
  for_each = local.admin_roles

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = each.value.principal_id
}
