# -----------------------------------------------------------------------------
# Azure Monitor log alerts on the API telemetry. Mirrors ../alerts.bicep.
# -----------------------------------------------------------------------------
variable "alert_email" {
  description = "Optional email notified when an alert fires. Empty: alerts only show in Azure Monitor."
  type        = string
  default     = ""
}

locals {
  # Any match within 15 minutes fires; the alert resolves itself once matches stop.
  alert_rules = {
    "api-5xx" = {
      description = "The API answered HTTP 5xx."
      query       = "AppRequests | where toint(ResultCode) >= 500"
    }
    "analysis-failures" = {
      description = "Analysis steps failed: the case shows the AI pipeline problem badge. The message names the application and the steps."
      query       = "AppTraces | where Message startswith \"Analysis steps failed for application\""
    }
  }
}

resource "azurerm_monitor_action_group" "alerts" {
  count               = var.alert_email == "" ? 0 : 1
  name                = "ag-${local.prefix}"
  resource_group_name = local.resource_group_name
  short_name          = substr(replace(local.prefix, "-", ""), 0, 12)
  tags                = local.tags

  email_receiver {
    name                    = "operator"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "this" {
  for_each             = local.alert_rules
  name                 = "alert-${local.prefix}-${each.key}"
  resource_group_name  = local.resource_group_name
  location             = local.location
  description          = each.value.description
  severity             = 2
  scopes               = [azurerm_log_analytics_workspace.this.id]
  evaluation_frequency = "PT15M"
  window_duration      = "PT15M"
  # The App* tables only exist once telemetry has arrived in a new workspace.
  skip_query_validation   = true
  auto_mitigation_enabled = true
  tags                    = local.tags

  criteria {
    query                   = each.value.query
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  dynamic "action" {
    for_each = azurerm_monitor_action_group.alerts
    content {
      action_groups = [action.value.id]
    }
  }
}
