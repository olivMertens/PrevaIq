# -----------------------------------------------------------------------------
# Container Apps environment
# -----------------------------------------------------------------------------
resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${local.prefix}"
  location                   = local.location
  resource_group_name        = local.resource_group_name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id   = local.private ? azurerm_subnet.apps[0].id : null
  tags                       = local.tags

  # Same environment type as the Bicep template (the Consumption profile is what ARM adds by default).
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# -----------------------------------------------------------------------------
# API backend
# -----------------------------------------------------------------------------
locals {
  api_env = {
    AZURE_CLIENT_ID                                   = azurerm_user_assigned_identity.this.client_id
    AZURE_CONTENT_UNDERSTANDING_ENDPOINT              = local.openai_endpoint_url
    AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD          = "true"
    AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT = local.primary_model
    AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT  = local.embedding_model_large
    AZURE_OPENAI_ENDPOINT                             = local.openai_endpoint_url
    AZURE_OPENAI_USE_AZURE_AD                         = "true"
    AZURE_OPENAI_DEPLOYMENT_NAME                      = local.primary_model
    AZURE_OPENAI_MODEL_NAME                           = local.primary_model
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME                 = local.primary_model
    AZURE_OPENAI_CHAT_MODEL_NAME                      = local.primary_model
    AZURE_OPENAI_NANO_DEPLOYMENT_NAME                 = local.nano_model
    AZURE_OPENAI_NANO_MODEL_NAME                      = local.nano_model
    AZURE_OPENAI_API_VERSION                          = local.openai_api_version
    AZURE_OPENAI_CHAT_API_VERSION                     = local.openai_api_version # also set by deploy.ps1; kept so re-applies do not drop it
    AZURE_OPENAI_REASONING_EFFORT                     = "low"
    # Fraud detection: 2-model pipeline
    FRAUD_VISION_DEPLOYMENT      = local.primary_model
    FRAUD_VISION_MODEL           = local.primary_model
    FRAUD_DETECTION_DEPLOYMENT   = local.primary_model
    FRAUD_DETECTION_MODEL        = local.primary_model
    STORAGE_BACKEND              = "azure_blob"
    AZURE_STORAGE_AUTH_MODE      = "default"
    AZURE_STORAGE_ACCOUNT_NAME   = azurerm_storage_account.this.name
    AZURE_STORAGE_CONTAINER_NAME = local.data_container_name
    DATABASE_BACKEND             = "postgresql"
    POSTGRESQL_HOST              = azurerm_postgresql_flexible_server.this.fqdn
    POSTGRESQL_PORT              = "5432"
    POSTGRESQL_DATABASE          = azurerm_postgresql_flexible_server_database.this.name
    POSTGRESQL_USER              = var.pg_admin_login
    POSTGRESQL_SSL_MODE          = "require"
    RAG_ENABLED                  = "true"
    EMBEDDING_DEPLOYMENT         = local.embedding_model_small
    AGENT_FRAMEWORK_ENABLED      = "true"
    # OpenTelemetry to Application Insights (agent spans for Foundry); plain env var, as in the Bicep template
    APPLICATIONINSIGHTS_CONNECTION_STRING              = nonsensitive(azurerm_application_insights.this.connection_string)
    OTEL_SERVICE_NAME                                  = var.brand_name
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "true"
    # Fabric Data Agent endpoint (the workspace and agent IDs are in fabric_env)
    FABRIC_DATA_AGENT_ENDPOINT = var.fabric_data_agent_endpoint
    # Azure AI Search (corrections index)
    AZURE_SEARCH_ENDPOINT   = "https://${azurerm_search_service.this.name}.search.windows.net"
    AZURE_SEARCH_INDEX_NAME = "corrections"
    # Web Intelligence agent (Foundry Agent Service + Bing grounding)
    WEB_INTELLIGENCE_ENABLED    = "true"
    FOUNDRY_PROJECT_ENDPOINT    = local.foundry_project_endpoint
    WEB_INTELLIGENCE_AGENT_NAME = "PrevaIQ-WebIntelligence"
  }

  # Fabric Data Agent IDs (set them after creating the Data Agent in Fabric); omitted while empty.
  fabric_env = {
    for name, value in {
      FABRIC_WORKSPACE_ID  = var.fabric_workspace_id
      FABRIC_DATA_AGENT_ID = var.fabric_data_agent_id
    } : name => value if value != ""
  }

  # Environment variable name => Container App secret name.
  api_secret_env = merge(
    {
      API_KEY             = "api-key"
      POSTGRESQL_PASSWORD = "pg-password"
    },
    var.webiq_secret_enabled ? { WEBIQ_API_KEY = "webiq-api-key" } : {},
  )
}

resource "azurerm_container_app" "api" {
  name                         = "ca-api-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = local.resource_group_name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.this.id
  }

  secret {
    name  = "api-key"
    value = var.api_key
  }

  secret {
    name  = "pg-password"
    value = var.pg_admin_password
  }

  # Only reference the secret once it exists in Key Vault, otherwise the revision cannot resolve it.
  dynamic "secret" {
    for_each = var.webiq_secret_enabled ? [1] : []

    content {
      name                = "webiq-api-key"
      key_vault_secret_id = "${azurerm_key_vault.this.vault_uri}secrets/webiq-api-key"
      identity            = azurerm_user_assigned_identity.this.id
    }
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "http"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = merge(local.api_env, local.fabric_env, local.access_email_env)

        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.api_secret_env

        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }

  lifecycle {
    # deploy.ps1 rolls out the image.
    ignore_changes = [template[0].container[0].image]
  }

  depends_on = [
    azurerm_role_assignment.identity,
    azurerm_cognitive_deployment.embedding_small,
    azurerm_private_endpoint.this,
  ]
}

# -----------------------------------------------------------------------------
# Frontend
# -----------------------------------------------------------------------------
resource "azurerm_container_app" "frontend" {
  name                         = "ca-frontend-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = local.resource_group_name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.this.id
  }

  secret {
    name  = "api-key"
    value = var.api_key
  }

  ingress {
    external_enabled           = true
    target_port                = 3000
    transport                  = "http"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "frontend"
      image  = var.frontend_image
      cpu    = 0.25
      memory = "0.5Gi"

      # API_URL is baked into the image at build time (see deploy.ps1), so it is not set here.
      env {
        name        = "API_KEY"
        secret_name = "api-key"
      }

      env {
        name  = "HOSTNAME"
        value = "0.0.0.0"
      }
    }
  }

  lifecycle {
    # deploy.ps1 rolls out the image and owns the AUTH_* settings.
    ignore_changes = [
      template[0].container[0].image,
      template[0].container[0].env,
    ]
  }

  depends_on = [azurerm_role_assignment.identity]
}
