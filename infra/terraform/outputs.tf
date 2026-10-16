output "acr_login_server" {
  description = "Container Registry login server."
  value       = azurerm_container_registry.this.login_server
}

output "container_apps_default_domain" {
  description = "Default domain of the Container Apps environment (API FQDN = ca-api-<env>.<domain>)."
  value       = azurerm_container_app_environment.this.default_domain
}

output "api_app_url" {
  description = "Public URL of the API app."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "frontend_app_url" {
  description = "Public URL of the frontend app."
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint used by the apps."
  value       = local.openai_endpoint_url
}

output "content_understanding_endpoint" {
  description = "Content Understanding endpoint (same AIServices resource as OpenAI)."
  value       = local.openai_endpoint_url
}

output "foundry_account_name" {
  description = "Microsoft Foundry (AIServices) account name."
  value       = azurerm_cognitive_account.foundry.name
}

output "foundry_project_name" {
  description = "Microsoft Foundry project name."
  value       = azurerm_cognitive_account_project.foundry.name
}

output "storage_account_name" {
  description = "Storage account holding the blob containers."
  value       = azurerm_storage_account.this.name
}

output "postgres_host" {
  description = "PostgreSQL Flexible Server FQDN."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "managed_identity_client_id" {
  description = "Client ID of the user-assigned managed identity."
  value       = azurerm_user_assigned_identity.this.client_id
}

output "key_vault_name" {
  description = "Key Vault name (target of infra/set-webiq-secret.ps1)."
  value       = azurerm_key_vault.this.name
}

output "app_insights_connection_string" {
  description = "Application Insights connection string."
  value       = azurerm_application_insights.this.connection_string
  sensitive   = true
}
