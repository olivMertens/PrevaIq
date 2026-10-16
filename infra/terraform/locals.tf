locals {
  prefix              = "${var.project_name}-${var.environment}"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = coalesce(var.location, data.azurerm_resource_group.this.location)

  # Terraform has no uniqueString(); hashing the resource group ID gives a stable, unique suffix.
  unique_suffix = substr(md5("${data.azurerm_resource_group.this.id}${var.project_name}"), 0, 13)

  tags = merge({
    SecurityControl = "ignore"
    CostControl     = "ignore"
    Project         = var.project_name
    Environment     = var.environment
  }, var.tags)

  foundry_account_name = "ai-${var.project_name}-foundry"
  foundry_project_name = "ai-${var.project_name}-project"

  # One AIServices account serves Azure OpenAI, Content Understanding and the Foundry Agent Service.
  openai_endpoint_url      = azurerm_cognitive_account.foundry.endpoint
  foundry_project_endpoint = "${trimsuffix(azurerm_cognitive_account.foundry.endpoint, "/")}/api/projects/${azurerm_cognitive_account_project.foundry.name}"

  # GA models, reasoning low: mini for chat/analysis/Content Understanding, nano for light tasks.
  primary_model         = "gpt-5.4-mini"
  nano_model            = "gpt-5.4-nano"
  model_version         = "2026-03-17"
  openai_api_version    = "2025-04-01-preview"
  embedding_model_large = "text-embedding-3-large"
  embedding_model_small = "text-embedding-3-small"
  embedding_version     = "1"

  data_container_name = "${var.project_name}-data"
  blob_containers     = [local.data_container_name, "corrections"]

  # Private networking: the data services are reached through private endpoints and stay open to admin_ip_ranges only.
  private         = var.private_networking_enabled
  public_access   = !local.private || length(var.admin_ip_ranges) > 0
  restrict_public = local.private && local.public_access
}
