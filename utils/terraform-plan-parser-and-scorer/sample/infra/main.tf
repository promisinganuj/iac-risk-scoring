provider "azurerm" {
	features {}
  subscription_id = "2350ac68-93e3-433d-b06a-e0890aad9953"
}

resource "azurerm_resource_group" "example" {
	name     = "example-resources"
	location = "East US"
}

resource "azurerm_private_dns_zone" "blob" {
	name                = "privatelink.blob.core.windows.net"
	resource_group_name = azurerm_resource_group.example.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob_link" {
	name                  = "example-vnet-link"
	resource_group_name   = azurerm_resource_group.example.name
	private_dns_zone_name = azurerm_private_dns_zone.blob.name
	virtual_network_id    = azurerm_virtual_network.example.id
}

resource "azurerm_private_dns_a_record" "storage_blob" {
	name                = azurerm_storage_account.example.name
	zone_name           = azurerm_private_dns_zone.blob.name
	resource_group_name = azurerm_resource_group.example.name
	ttl                 = 300
	records             = [azurerm_private_endpoint.storage_pe.private_service_connection[0].private_ip_address]
}

resource "azurerm_virtual_network" "example" {
	name                = "example-vnet"
	address_space       = ["10.0.0.0/16"]
	location            = azurerm_resource_group.example.location
	resource_group_name = azurerm_resource_group.example.name
}

resource "azurerm_subnet" "subnet1" {
	name                 = "subnet1"
	resource_group_name  = azurerm_resource_group.example.name
	virtual_network_name = azurerm_virtual_network.example.name
	address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_subnet" "subnet2" {
	name                 = "subnet2"
	resource_group_name  = azurerm_resource_group.example.name
	virtual_network_name = azurerm_virtual_network.example.name
	address_prefixes     = ["10.0.2.0/24"]
}

resource "azurerm_storage_account" "example" {
	name                     = "examplestoracct123"
	resource_group_name      = azurerm_resource_group.example.name
	location                 = azurerm_resource_group.example.location
	account_tier             = "Standard"
	account_replication_type = "LRS"
}

resource "azurerm_private_endpoint" "storage_pe" {
	name                = "example-storage-pe"
	location            = azurerm_resource_group.example.location
	resource_group_name = azurerm_resource_group.example.name
	subnet_id           = azurerm_subnet.subnet1.id

	private_service_connection {
		name                           = "example-storage-psc"
		private_connection_resource_id = azurerm_storage_account.example.id
		subresource_names              = ["blob"]
		is_manual_connection           = false
	}
}
