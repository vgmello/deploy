output "function_name" {
  value = azurerm_linux_function_app.this.name
}

output "default_hostname" {
  value = azurerm_linux_function_app.this.default_hostname
}

output "plan_sku" {
  value = azurerm_service_plan.this.sku_name
}
