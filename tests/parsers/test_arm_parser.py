"""Tests for ARM template parser."""
import pytest
import json
from iac_risk_scoring.parsers import ARMParser


def test_arm_parser_supports_json():
    """Test ARM parser file support detection."""
    parser = ARMParser()
    assert parser.supports_file("template.json")
    assert parser.supports_file("azuredeploy.template.json")
    assert not parser.supports_file("main.tf")


def test_arm_parser_basic_template():
    """Test parsing basic ARM template."""
    template = {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "resources": [
            {
                "type": "Microsoft.Storage/storageAccounts",
                "apiVersion": "2021-04-01",
                "name": "mystorageaccount",
                "location": "eastus",
                "sku": {
                    "name": "Standard_LRS"
                },
                "properties": {
                    "supportsHttpsTrafficOnly": True,
                    "encryption": {
                        "services": {
                            "blob": {"enabled": True}
                        }
                    }
                }
            }
        ]
    }
    
    parser = ARMParser()
    resources = parser.parse(json.dumps(template))
    
    assert len(resources) == 1
    assert resources[0].resource_type == "Microsoft.Storage/storageAccounts"
    assert resources[0].name == "mystorageaccount"
    assert resources[0].properties["supportsHttpsTrafficOnly"] is True


def test_arm_parser_multiple_resources():
    """Test parsing ARM template with multiple resources."""
    template = {
        "resources": [
            {
                "type": "Microsoft.Network/publicIPAddresses",
                "name": "myPublicIP",
                "properties": {}
            },
            {
                "type": "Microsoft.Compute/virtualMachines",
                "name": "myVM",
                "properties": {},
                "dependsOn": ["myPublicIP"]
            }
        ]
    }
    
    parser = ARMParser()
    resources = parser.parse(json.dumps(template))
    
    assert len(resources) == 2
    assert resources[0].resource_type == "Microsoft.Network/publicIPAddresses"
    assert resources[1].dependencies == ["myPublicIP"]


def test_arm_parser_invalid_json():
    """Test ARM parser with invalid JSON."""
    parser = ARMParser()
    
    with pytest.raises(ValueError, match="Invalid JSON"):
        parser.parse("not valid json")


def test_arm_parser_empty_resources():
    """Test ARM parser with no resources."""
    template = {"resources": []}
    
    parser = ARMParser()
    resources = parser.parse(json.dumps(template))
    
    assert len(resources) == 0
