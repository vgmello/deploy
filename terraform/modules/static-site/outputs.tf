output "site_name" {
  value = azurerm_static_web_app.this.name
}

output "default_host_name" {
  value = azurerm_static_web_app.this.default_host_name
}
