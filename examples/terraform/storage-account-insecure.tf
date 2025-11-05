resource "azurerm_storage_account" "example" {
  name                     = "insecurestorageacct"
  resource_group_name      = "myresourcegroup"
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  
  enable_https_traffic_only = false
  min_tls_version          = "TLS1_0"
  public_network_access_enabled = true
}
