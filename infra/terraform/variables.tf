variable "subscription_id" {
  description = "Azure subscription ID. Defaults to ARM_SUBSCRIPTION_ID, then to the Azure CLI's current subscription."
  type        = string
  default     = null
}

variable "resource_group_name" {
  description = "Existing resource group to deploy into (create it with 'az group create')."
  type        = string
  default     = "rg-prevaiq-demo"
}

variable "environment" {
  description = "Environment name (demo, dev, staging), used in resource names."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z0-9]{2,10}$", var.environment))
    error_message = "environment must be 2-10 lowercase letters or digits."
  }
}

variable "location" {
  description = "Azure region for deployment. Defaults to the resource group's region."
  type        = string
  default     = null
}

variable "search_location" {
  description = "Region of Azure AI Search (Sweden Central lacked Search capacity at provisioning time)."
  type        = string
  default     = "francecentral"
}

variable "postgres_database_name" {
  description = "PostgreSQL database name. Kept as workbenchiq: the application schema and existing data live in it."
  type        = string
  default     = "workbenchiq"
}

variable "project_name" {
  description = "Project name used as prefix for resource names (3-11 characters; the storage account name is truncated to 24)."
  type        = string
  default     = "prevaiq"

  validation {
    condition     = can(regex("^[a-z0-9]{3,11}$", var.project_name))
    error_message = "project_name must be 3-11 lowercase letters or digits."
  }
}

variable "brand_name" {
  description = "Brand display name, used as the OpenTelemetry service name. BRAND_NAME itself is baked into the images."
  type        = string
  default     = "PrevaIQ"
}

variable "acr_sku" {
  description = "Container Registry SKU. Premium is required for dedicated build agent pools (demo uses Premium)."
  type        = string
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "acr_sku must be Basic, Standard or Premium."
  }
}

variable "api_key" {
  description = "API key for backend authentication (min 32 chars). Pass it with TF_VAR_api_key rather than a tfvars file."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.api_key) >= 32
    error_message = "api_key must be at least 32 characters."
  }
}

variable "fabric_data_agent_endpoint" {
  description = "Fabric API endpoint for Data Agent calls."
  type        = string
  default     = "https://api.fabric.microsoft.com"
}

variable "fabric_workspace_id" {
  description = "Fabric workspace ID that contains the Data Agent item."
  type        = string
  default     = ""
}

variable "fabric_data_agent_id" {
  description = "Fabric Data Agent item ID."
  type        = string
  default     = ""
}

variable "pg_admin_login" {
  description = "PostgreSQL administrator login."
  type        = string
  default     = "prevaiqadmin"
}

variable "pg_admin_password" {
  description = "PostgreSQL administrator password. Pass it with TF_VAR_pg_admin_password rather than a tfvars file."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.pg_admin_password) >= 8
    error_message = "pg_admin_password must be at least 8 characters."
  }
}

variable "webiq_secret_enabled" {
  description = "Wire the Web IQ key (Key Vault secret webiq-api-key) into the API app. Enable after running infra/set-webiq-secret.ps1."
  type        = bool
  default     = false
}

variable "admin_principal_ids" {
  description = "Object IDs of the people or pipelines that run deploy.ps1, set-webiq-secret.ps1 and the maintenance scripts. They get the data-plane roles those need on Foundry, Key Vault and Storage, which Owner/Contributor does not include (e.g. az ad signed-in-user show --query id -o tsv)."
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for id in var.admin_principal_ids : can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", id))])
    error_message = "admin_principal_ids must be object IDs (GUIDs), e.g. from az ad signed-in-user show --query id -o tsv."
  }
}

variable "private_networking_enabled" {
  description = "Isolate the data services: Container Apps environment in a VNet, private endpoints for Storage, Key Vault, AI Search and Foundry, PostgreSQL with private access. ACR stays public (ACR Tasks builds). Public access to the other services is closed except for admin_ip_ranges."
  type        = bool
  default     = false
}

variable "vnet_address_space" {
  description = "Address space (a /16) of the VNet created when private_networking_enabled is true."
  type        = string
  default     = "10.60.0.0/16"

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/16$", var.vnet_address_space)) && can(cidrhost(var.vnet_address_space, 0))
    error_message = "vnet_address_space must be a /16 CIDR block, e.g. 10.60.0.0/16."
  }
}

variable "admin_ip_ranges" {
  description = "Public IPs or CIDR ranges (a single address without /32) allowed through the Storage, Key Vault, AI Search and Foundry firewalls when private_networking_enabled is true, so deploy.ps1 and set-webiq-secret.ps1 still work from an operator machine. Empty keeps those services private-only."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for range in var.admin_ip_ranges : can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}(/([0-9]|[12][0-9]|30))?$", range))])
    error_message = "admin_ip_ranges entries must be IPv4 addresses or CIDR ranges up to /30 (use a plain address instead of /31 or /32)."
  }
}

variable "api_image" {
  description = "Initial image of the API app. The default placeholder lets the first apply succeed before ACR holds any image; deploy.ps1 rolls out prevaiq-api:<tag> and Terraform ignores later image changes."
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "frontend_image" {
  description = "Initial image of the frontend app (see api_image)."
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "tags" {
  description = "Extra tags merged into the default tags of every resource."
  type        = map(string)
  default     = {}
}
