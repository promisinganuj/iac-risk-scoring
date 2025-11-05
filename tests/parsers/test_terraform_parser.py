"""Tests for Terraform parser."""
import pytest
from iac_risk_scoring.parsers import TerraformParser


def test_terraform_parser_supports_tf():
    """Test Terraform parser file support detection."""
    parser = TerraformParser()
    assert parser.supports_file("main.tf")
    assert parser.supports_file("variables.tf")
    assert not parser.supports_file("template.json")


def test_terraform_parser_basic_resource():
    """Test parsing basic Terraform resource."""
    tf_content = '''
resource "azurerm_storage_account" "example" {
  name                     = "mystorageaccount"
  resource_group_name      = "myresourcegroup"
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  enable_https_traffic_only = true
}
'''
    
    parser = TerraformParser()
    resources = parser.parse(tf_content)
    
    assert len(resources) == 1
    assert resources[0].resource_type == "azurerm_storage_account"
    assert resources[0].name == "example"
    assert resources[0].properties["name"] == "mystorageaccount"
    assert resources[0].properties["enable_https_traffic_only"] is True


def test_terraform_parser_multiple_resources():
    """Test parsing multiple Terraform resources."""
    tf_content = '''
resource "azurerm_public_ip" "example" {
  name                = "myPublicIP"
  location            = "eastus"
  resource_group_name = "myresourcegroup"
}

resource "azurerm_virtual_machine" "example" {
  name                = "myVM"
  location            = "eastus"
  resource_group_name = "myresourcegroup"
}
'''
    
    parser = TerraformParser()
    resources = parser.parse(tf_content)
    
    assert len(resources) == 2
    assert resources[0].resource_type == "azurerm_public_ip"
    assert resources[1].resource_type == "azurerm_virtual_machine"


def test_terraform_parser_ignores_non_azure():
    """Test that parser ignores non-Azure resources."""
    tf_content = '''
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"
}

resource "azurerm_storage_account" "example" {
  name = "mystorageaccount"
}
'''
    
    parser = TerraformParser()
    resources = parser.parse(tf_content)
    
    assert len(resources) == 1
    assert resources[0].resource_type == "azurerm_storage_account"


def test_terraform_parser_empty_content():
    """Test parsing empty Terraform content."""
    parser = TerraformParser()
    resources = parser.parse("")
    
    assert len(resources) == 0
