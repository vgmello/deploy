output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "plan_identity_client_id" {
  value = azurerm_user_assigned_identity.plan.client_id
}

output "apply_identity_client_id" {
  value = azurerm_user_assigned_identity.apply.client_id
}
