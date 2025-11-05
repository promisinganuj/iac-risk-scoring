resource "azurerm_storage_account" "example" {
  name                     = "securestorageacct"
  resource_group_name      = "myresourcegroup"
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  
  enable_https_traffic_only = true
  min_tls_version          = "TLS1_2"
  public_network_access_enabled = false
}
