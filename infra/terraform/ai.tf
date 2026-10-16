# -----------------------------------------------------------------------------
# Microsoft Foundry (AIServices) account + project: hosts the OpenAI model deployments,
# Content Understanding and the Foundry Agent Service. One account serves all three.
# -----------------------------------------------------------------------------
resource "azurerm_cognitive_account" "foundry" {
  name                          = local.foundry_account_name
  location                      = local.location
  resource_group_name           = local.resource_group_name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = local.foundry_account_name # deploy.ps1 derives the account name from the endpoint host
  project_management_enabled    = true
  public_network_access_enabled = local.public_access
  local_auth_enabled            = false # identity-only access
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }

  dynamic "network_acls" {
    for_each = local.restrict_public ? [1] : []

    content {
      default_action = "Deny"
      bypass         = "AzureServices"
      ip_rules       = var.admin_ip_ranges
    }
  }
}

resource "azurerm_cognitive_account_project" "foundry" {
  name                 = local.foundry_project_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = local.location
  tags                 = local.tags

  identity {
    type = "SystemAssigned"
  }
}

# The account accepts one write at a time: project first, then the deployments one after the other
# (409 RequestConflict otherwise).

# gpt-5.4-nano: background labels, folder titles, classification, JSON cleanup
resource "azurerm_cognitive_deployment" "gpt54_nano" {
  name                 = local.nano_model
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = local.nano_model
    version = local.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 50
  }

  depends_on = [azurerm_cognitive_account_project.foundry]
}

# gpt-5.4-mini: chat, agents, workflows, fraud vision/reasoning, Content Understanding completion
resource "azurerm_cognitive_deployment" "gpt54_mini" {
  name                 = local.primary_model
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = local.primary_model
    version = local.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 100
  }

  depends_on = [azurerm_cognitive_deployment.gpt54_nano]
}

# text-embedding-3-large: Content Understanding analyzer embeddings
resource "azurerm_cognitive_deployment" "embedding_large" {
  name                 = local.embedding_model_large
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = local.embedding_model_large
    version = local.embedding_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  depends_on = [azurerm_cognitive_deployment.gpt54_mini]
}

# text-embedding-3-small: RAG (pgvector) embeddings
resource "azurerm_cognitive_deployment" "embedding_small" {
  name                 = local.embedding_model_small
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = local.embedding_model_small
    version = local.embedding_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  depends_on = [azurerm_cognitive_deployment.embedding_large]
}

# Foundry project connections (AAD auth, no keys)
resource "azapi_resource" "foundry_blob_connection" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2026-01-15-preview"
  name      = "${var.project_name}-blob"
  parent_id = azurerm_cognitive_account_project.foundry.id

  schema_validation_enabled = false

  body = {
    properties = {
      authType = "AAD"
      category = "AzureBlob"
      target   = azurerm_storage_account.this.primary_blob_endpoint
      metadata = {
        AccountName   = azurerm_storage_account.this.name
        ContainerName = local.data_container_name
        ResourceId    = azurerm_storage_account.this.id
      }
    }
  }
}

resource "azapi_resource" "foundry_search_connection" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2026-01-15-preview"
  name      = "${var.project_name}-search"
  parent_id = azurerm_cognitive_account_project.foundry.id

  schema_validation_enabled = false

  body = {
    properties = {
      authType = "AAD"
      category = "CognitiveSearch"
      target   = "https://${azurerm_search_service.this.name}.search.windows.net"
      metadata = {
        ResourceId = azurerm_search_service.this.id
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Azure AI Search (corrections semantic retrieval)
# -----------------------------------------------------------------------------
resource "azurerm_search_service" "this" {
  name                         = "srch-${local.prefix}"
  location                     = coalesce(var.search_location, local.location)
  resource_group_name          = local.resource_group_name
  sku                          = "basic"
  replica_count                = 1
  partition_count              = 1
  hosting_mode                 = "default"
  local_authentication_enabled = true
  authentication_failure_mode  = "http401WithBearerChallenge"
  tags                         = local.tags

  public_network_access_enabled = local.public_access
  allowed_ips                   = local.restrict_public ? var.admin_ip_ranges : []
  network_rule_bypass_option    = local.restrict_public ? "AzureServices" : "None"
}
