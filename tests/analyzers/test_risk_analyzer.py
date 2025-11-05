"""Tests for risk analyzer."""
import pytest
from iac_risk_scoring.models import IaCResource, RiskLevel
from iac_risk_scoring.analyzers import RiskAnalyzer
from iac_risk_scoring.rules.azure_rules import AzureSecurityRules


def test_analyzer_with_no_issues():
    """Test analyzer with clean resources."""
    rules = AzureSecurityRules.get_all_rules()
    analyzer = RiskAnalyzer(rules)
    
    resources = [
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="mystorage",
            properties={
                "supportsHttpsTrafficOnly": True,
                "minimumTlsVersion": "TLS1_2",
                "encryption": {
                    "services": {
                        "blob": {"enabled": True}
                    }
                }
            }
        )
    ]
    
    result = analyzer.analyze(resources)
    
    assert result.total_score == 0
    assert result.risk_level == RiskLevel.INFO
    assert len(result.findings) == 0


def test_analyzer_with_security_issues():
    """Test analyzer detects security issues."""
    rules = AzureSecurityRules.get_all_rules()
    analyzer = RiskAnalyzer(rules)
    
    resources = [
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="mystorage",
            properties={
                "supportsHttpsTrafficOnly": False,
                "publicNetworkAccess": "Enabled"
            }
        )
    ]
    
    result = analyzer.analyze(resources)
    
    assert result.total_score > 0
    assert len(result.findings) > 0
    assert result.summary["total_findings"] > 0


def test_analyzer_calculates_correct_risk_level():
    """Test risk level calculation."""
    rules = AzureSecurityRules.get_all_rules()
    analyzer = RiskAnalyzer(rules)
    
    # Create resource with critical issue
    resources = [
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="mystorage",
            properties={
                "encryption": {"services": {}}
            }
        )
    ]
    
    result = analyzer.analyze(resources)
    
    # Should have critical finding
    assert any(f.level == RiskLevel.CRITICAL for f in result.findings)
    assert result.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]


def test_analyzer_generates_summary():
    """Test summary generation."""
    rules = AzureSecurityRules.get_all_rules()
    analyzer = RiskAnalyzer(rules)
    
    resources = [
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="storage1",
            properties={"supportsHttpsTrafficOnly": False}
        ),
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="storage2",
            properties={"publicNetworkAccess": "Enabled"}
        )
    ]
    
    result = analyzer.analyze(resources)
    
    assert "by_level" in result.summary
    assert "by_category" in result.summary
    assert result.summary["total_findings"] > 0
    assert result.summary["by_category"]["security"] > 0


def test_analyzer_with_multiple_resources():
    """Test analyzer with multiple resources."""
    rules = AzureSecurityRules.get_all_rules()
    analyzer = RiskAnalyzer(rules)
    
    resources = [
        IaCResource(
            resource_type="Microsoft.Storage/storageAccounts",
            name="storage1",
            properties={"supportsHttpsTrafficOnly": False}
        ),
        IaCResource(
            resource_type="Microsoft.Compute/virtualMachines",
            name="vm1",
            properties={}
        ),
        IaCResource(
            resource_type="Microsoft.Network/publicIPAddresses",
            name="pip1",
            properties={}
        )
    ]
    
    result = analyzer.analyze(resources)
    
    assert result.metadata["resources_analyzed"] == 3
    assert isinstance(result.total_score, int)
