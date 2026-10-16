# -----------------------------------------------------------------------------
# Optional private networking (private_networking_enabled). The Container Apps environment joins a
# VNet and reaches Storage, Key Vault, AI Search and Foundry through private endpoints; PostgreSQL
# uses private access. ACR stays public: it is RBAC-protected and ACR Tasks builds need it.
# -----------------------------------------------------------------------------
locals {
  # Private Link target => private DNS zones (Foundry needs three).
  private_endpoints = {
    for name, endpoint in {
      storage = {
        resource_id = azurerm_storage_account.this.id
        subresource = "blob"
        zones       = ["privatelink.blob.core.windows.net"]
      }
      vault = {
        resource_id = azurerm_key_vault.this.id
        subresource = "vault"
        zones       = ["privatelink.vaultcore.azure.net"]
      }
      search = {
        resource_id = azurerm_search_service.this.id
        subresource = "searchService"
        zones       = ["privatelink.search.windows.net"]
      }
      foundry = {
        resource_id = azurerm_cognitive_account.foundry.id
        subresource = "account"
        zones       = ["privatelink.cognitiveservices.azure.com", "privatelink.openai.azure.com", "privatelink.services.ai.azure.com"]
      }
    } : name => endpoint if local.private
  }

  private_dns_zones = toset(flatten([for endpoint in local.private_endpoints : endpoint.zones]))
}

resource "azurerm_virtual_network" "this" {
  count = local.private ? 1 : 0

  name                = "vnet-${local.prefix}"
  location            = local.location
  resource_group_name = local.resource_group_name
  address_space       = [var.vnet_address_space]
  tags                = local.tags
}

# Workload profiles environment: at least a /27, delegated to Microsoft.App/environments.
resource "azurerm_subnet" "apps" {
  count = local.private ? 1 : 0

  name                 = "snet-apps"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 10, 0)]

  delegation {
    name = "container-apps"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  count = local.private ? 1 : 0

  name                 = "snet-private-endpoints"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 8, 1)]
}

resource "azurerm_subnet" "postgres" {
  count = local.private ? 1 : 0

  name                 = "snet-postgres"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 8, 2)]

  delegation {
    name = "postgres"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "this" {
  for_each = local.private_dns_zones

  name                = each.key
  resource_group_name = local.resource_group_name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each = azurerm_private_dns_zone.this

  name                 = "link-${local.prefix}"
  private_dns_zone_id  = each.value.id
  virtual_network_id   = azurerm_virtual_network.this[0].id
  registration_enabled = false
  tags                 = local.tags
}

resource "azurerm_private_endpoint" "this" {
  for_each = local.private_endpoints

  name                = "pe-${each.key}-${local.prefix}"
  location            = local.location
  resource_group_name = local.resource_group_name
  subnet_id           = azurerm_subnet.private_endpoints[0].id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-${each.key}"
    private_connection_resource_id = each.value.resource_id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [for zone in each.value.zones : azurerm_private_dns_zone.this[zone].id]
  }

  # The Foundry account takes one write at a time: attach the endpoint after the model deployments.
  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.this,
    azurerm_cognitive_deployment.embedding_small,
  ]
}

# PostgreSQL private access: the zone name must end with .postgres.database.azure.com.
resource "azurerm_private_dns_zone" "postgres" {
  count = local.private ? 1 : 0

  name                = "${local.prefix}.private.postgres.database.azure.com"
  resource_group_name = local.resource_group_name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  count = local.private ? 1 : 0

  name                 = "link-${local.prefix}"
  private_dns_zone_id  = azurerm_private_dns_zone.postgres[0].id
  virtual_network_id   = azurerm_virtual_network.this[0].id
  registration_enabled = false
  tags                 = local.tags

  depends_on = [azurerm_subnet.postgres]
}
