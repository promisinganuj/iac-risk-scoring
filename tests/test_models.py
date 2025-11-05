"""Tests for data models."""
import pytest
from iac_risk_scoring.models import (
    RiskLevel, RiskCategory, RiskFinding, RiskScore, IaCResource
)


def test_risk_level_scores():
    """Test risk level score mapping."""
    assert RiskLevel.CRITICAL.score == 100
    assert RiskLevel.HIGH.score == 75
    assert RiskLevel.MEDIUM.score == 50
    assert RiskLevel.LOW.score == 25
    assert RiskLevel.INFO.score == 0


def test_risk_finding_creation():
    """Test creating a risk finding."""
    finding = RiskFinding(
        category=RiskCategory.SECURITY,
        level=RiskLevel.HIGH,
        resource_type="Microsoft.Storage/storageAccounts",
        resource_name="mystorageaccount",
        rule_id="AZ-SEC-001",
        title="Test Finding",
        description="Test description",
        remediation="Test remediation"
    )
    
    assert finding.category == RiskCategory.SECURITY
    assert finding.level == RiskLevel.HIGH
    assert finding.resource_name == "mystorageaccount"


def test_risk_score_to_dict():
    """Test risk score serialization."""
    finding = RiskFinding(
        category=RiskCategory.SECURITY,
        level=RiskLevel.MEDIUM,
        resource_type="test",
        resource_name="test-resource",
        rule_id="TEST-001",
        title="Test",
        description="Test desc",
        remediation="Test fix"
    )
    
    score = RiskScore(
        total_score=50,
        risk_level=RiskLevel.MEDIUM,
        findings=[finding],
        summary={"total": 1}
    )
    
    result = score.to_dict()
    assert result["total_score"] == 50
    assert result["risk_level"] == "medium"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["rule_id"] == "TEST-001"


def test_iac_resource_creation():
    """Test IaC resource creation."""
    resource = IaCResource(
        resource_type="Microsoft.Compute/virtualMachines",
        name="myvm",
        properties={"size": "Standard_D2s_v3"},
        metadata={"location": "eastus"}
    )
    
    assert resource.resource_type == "Microsoft.Compute/virtualMachines"
    assert resource.name == "myvm"
    assert resource.properties["size"] == "Standard_D2s_v3"
    assert len(resource.dependencies) == 0
