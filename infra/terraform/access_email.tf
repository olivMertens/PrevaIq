variable "access_email_enabled" {
  type    = bool
  default = false
}

variable "access_email_data_location" {
  type    = string
  default = "Europe"
}

variable "access_request_email" {
  type    = string
  default = ""
}

variable "access_admin_url" {
  type    = string
  default = ""
}

resource "azurerm_email_communication_service" "access" {
  count               = var.access_email_enabled ? 1 : 0
  name                = "email-${local.prefix}"
  resource_group_name = local.resource_group_name
  data_location       = var.access_email_data_location
  tags                = local.tags
}

resource "azurerm_email_communication_service_domain" "access" {
  count             = var.access_email_enabled ? 1 : 0
  name              = "AzureManagedDomain"
  email_service_id  = azurerm_email_communication_service.access[0].id
  domain_management = "AzureManaged"
  tags              = local.tags
}

resource "azapi_resource" "access_communication" {
  count     = var.access_email_enabled ? 1 : 0
  type      = "Microsoft.Communication/communicationServices@2023-03-31"
  name      = "acs-${local.prefix}"
  parent_id = data.azurerm_resource_group.this.id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      dataLocation  = var.access_email_data_location
      linkedDomains = [azurerm_email_communication_service_domain.access[0].id]
    }
  }
  response_export_values = ["properties.hostName"]
}

resource "azurerm_role_definition" "access_email_sender" {
  count              = var.access_email_enabled ? 1 : 0
  role_definition_id = uuidv5("11fb06fb-712d-4ddd-98c7-e71bbd588830", "${data.azurerm_resource_group.this.id}-${local.prefix}-access-email-sender")
  name               = "${local.prefix}-access-email-sender"
  scope              = data.azurerm_resource_group.this.id
  description        = "Submit access-request emails using Entra authentication on the dedicated ACS resource."
  permissions {
    actions = [
      "Microsoft.Communication/CommunicationServices/read",
      "Microsoft.Communication/CommunicationServices/write",
    ]
  }
  assignable_scopes = [data.azurerm_resource_group.this.id]
}

resource "azurerm_role_assignment" "access_email_sender" {
  count              = var.access_email_enabled ? 1 : 0
  name               = uuidv5("11fb06fb-712d-4ddd-98c7-e71bbd588830", "${azapi_resource.access_communication[0].id}-${azurerm_user_assigned_identity.this.principal_id}-${azurerm_role_definition.access_email_sender[0].role_definition_resource_id}")
  scope              = azapi_resource.access_communication[0].id
  role_definition_id = azurerm_role_definition.access_email_sender[0].role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.this.principal_id
  principal_type     = "ServicePrincipal"
}

locals {
  access_email_env = var.access_email_enabled ? {
    ACCESS_EMAIL_ENDPOINT = "https://${azapi_resource.access_communication[0].output.properties.hostName}"
    ACCESS_EMAIL_SENDER   = "DoNotReply@${azurerm_email_communication_service_domain.access[0].from_sender_domain}"
    ACCESS_REQUEST_EMAIL  = var.access_request_email
    ACCESS_ADMIN_URL      = var.access_admin_url
  } : {}
}

output "access_email_endpoint" {
  value = var.access_email_enabled ? local.access_email_env.ACCESS_EMAIL_ENDPOINT : ""
}

output "access_email_sender" {
  value = var.access_email_enabled ? local.access_email_env.ACCESS_EMAIL_SENDER : ""
}
