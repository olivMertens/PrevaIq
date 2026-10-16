provider "azurerm" {
  subscription_id = var.subscription_id

  # azurerm 5.x no longer registers resource providers on its own.
  resource_providers_to_register = [
    "Microsoft.App",
    "Microsoft.CognitiveServices",
    "Microsoft.ContainerRegistry",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.Insights",
    "Microsoft.KeyVault",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
    "Microsoft.Search",
    "Microsoft.Storage",
  ]

  features {
    key_vault {
      # The vault has purge protection, so it cannot be purged on destroy.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

# Only used for the Foundry project connections, which azurerm does not model.
provider "azapi" {
  subscription_id = var.subscription_id
}
