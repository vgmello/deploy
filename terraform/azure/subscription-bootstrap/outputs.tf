output "bootstrap_identity_client_id" {
  value = azurerm_user_assigned_identity.bootstrap.client_id
}

output "bootstrap_identity_principal_id" {
  value = azurerm_user_assigned_identity.bootstrap.principal_id
}

output "custom_role_id" {
  value = azurerm_role_definition.bootstrap.role_definition_resource_id
}
