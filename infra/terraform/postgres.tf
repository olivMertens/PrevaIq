# -----------------------------------------------------------------------------
# PostgreSQL Flexible Server (pgvector)
# -----------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "pg-${local.prefix}"
  location                      = local.location
  resource_group_name           = local.resource_group_name
  version                       = "16"
  sku_name                      = "GP_Standard_D2ds_v4"
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  administrator_login           = var.pg_admin_login
  administrator_password        = var.pg_admin_password
  public_network_access_enabled = !local.private
  tags                          = local.tags

  # Private access: delegated subnet and private DNS zone instead of a public endpoint.
  delegated_subnet_id = local.private ? azurerm_subnet.postgres[0].id : null
  private_dns_zone_id = local.private ? azurerm_private_dns_zone.postgres[0].id : null

  # Needed by Fabric Mirroring.
  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    # Azure picks the availability zone; it must not be reverted on later applies.
    ignore_changes = [zone]
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

# Same allow-list as scripts/setup_postgresql_rag.py (the Bicep template only allows vector).
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "vector,uuid-ossp,pg_trgm"
}

# Required for Fabric Mirroring / CDC; takes effect after a server restart.
resource "azurerm_postgresql_flexible_server_configuration" "wal_level" {
  name      = "wal_level"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "logical"

  # Server parameters must be changed one at a time.
  depends_on = [azurerm_postgresql_flexible_server_configuration.extensions]
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure_services" {
  count = local.private ? 0 : 1

  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = var.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
