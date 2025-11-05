"""Tests for Azure security rules."""
import pytest
from iac_risk_scoring.models import IaCResource, RiskLevel, RiskCategory
from iac_risk_scoring.rules.azure_rules import (
    PublicIPRule, StorageEncryptionRule, HTTPSOnlyRule, TLSVersionRule
)


def test_public_ip_rule_detects_public_access():
    """Test PublicIPRule detects public IP address."""
    rule = PublicIPRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "publicNetworkAccess": "Enabled"
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is not None
    assert finding.level == RiskLevel.HIGH
    assert finding.category == RiskCategory.SECURITY
    assert finding.rule_id == "AZ-SEC-001"


def test_public_ip_rule_passes_private_access():
    """Test PublicIPRule passes for private access."""
    rule = PublicIPRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "publicNetworkAccess": "Disabled"
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is None


def test_storage_encryption_rule_detects_no_encryption():
    """Test StorageEncryptionRule detects missing encryption."""
    rule = StorageEncryptionRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "encryption": {
                "services": {}
            }
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is not None
    assert finding.level == RiskLevel.CRITICAL
    assert finding.rule_id == "AZ-SEC-002"


def test_https_only_rule_detects_disabled():
    """Test HTTPSOnlyRule detects HTTPS not enforced."""
    rule = HTTPSOnlyRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "supportsHttpsTrafficOnly": False
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is not None
    assert finding.level == RiskLevel.HIGH
    assert finding.rule_id == "AZ-SEC-003"


def test_https_only_rule_passes_enabled():
    """Test HTTPSOnlyRule passes when HTTPS is enforced."""
    rule = HTTPSOnlyRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "supportsHttpsTrafficOnly": True
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is None


def test_tls_version_rule_detects_weak_version():
    """Test TLSVersionRule detects weak TLS version."""
    rule = TLSVersionRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "minimumTlsVersion": "TLS1_0"
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is not None
    assert finding.level == RiskLevel.HIGH
    assert finding.rule_id == "AZ-SEC-004"


def test_tls_version_rule_passes_strong_version():
    """Test TLSVersionRule passes for TLS 1.2."""
    rule = TLSVersionRule()
    resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="mystorage",
        properties={
            "minimumTlsVersion": "TLS1_2"
        }
    )
    
    finding = rule.evaluate(resource)
    
    assert finding is None


def test_rule_applies_to_correct_types():
    """Test rules only apply to relevant resource types."""
    rule = StorageEncryptionRule()
    
    storage_resource = IaCResource(
        resource_type="Microsoft.Storage/storageAccounts",
        name="storage",
        properties={}
    )
    
    vm_resource = IaCResource(
        resource_type="Microsoft.Compute/virtualMachines",
        name="vm",
        properties={}
    )
    
    assert rule.applies_to(storage_resource.resource_type) is True
    assert rule.applies_to(vm_resource.resource_type) is False
