"""Tests for main risk scorer."""
import pytest
import json
from pathlib import Path
from iac_risk_scoring import RiskScorer, RiskLevel


def test_risk_scorer_initialization():
    """Test RiskScorer initialization."""
    scorer = RiskScorer()
    
    assert len(scorer.parsers) > 0
    assert scorer.analyzer is not None


def test_score_template_arm():
    """Test scoring ARM template content."""
    scorer = RiskScorer()
    
    template = {
        "resources": [
            {
                "type": "Microsoft.Storage/storageAccounts",
                "name": "mystorage",
                "properties": {
                    "supportsHttpsTrafficOnly": False
                }
            }
        ]
    }
    
    result = scorer.score_template(json.dumps(template), "json")
    
    assert result is not None
    assert isinstance(result.total_score, int)
    assert len(result.findings) > 0


def test_score_template_terraform():
    """Test scoring Terraform content."""
    scorer = RiskScorer()
    
    tf_content = '''
resource "azurerm_storage_account" "example" {
  name = "mystorage"
  enable_https_traffic_only = false
}
'''
    
    result = scorer.score_template(tf_content, "tf")
    
    assert result is not None
    assert isinstance(result.total_score, int)


def test_score_template_invalid_type():
    """Test scoring with invalid template type."""
    scorer = RiskScorer()
    
    with pytest.raises(ValueError, match="No parser available"):
        scorer.score_template("{}", "invalid")


def test_score_file(tmp_path):
    """Test scoring a file."""
    scorer = RiskScorer()
    
    # Create a test ARM template file
    template = {
        "resources": [
            {
                "type": "Microsoft.Storage/storageAccounts",
                "name": "mystorage",
                "properties": {}
            }
        ]
    }
    
    file_path = tmp_path / "template.json"
    file_path.write_text(json.dumps(template))
    
    result = scorer.score_file(str(file_path))
    
    assert result is not None
    assert isinstance(result.total_score, int)


def test_score_file_not_found():
    """Test scoring non-existent file."""
    scorer = RiskScorer()
    
    with pytest.raises(FileNotFoundError):
        scorer.score_file("/nonexistent/file.json")


def test_score_directory(tmp_path):
    """Test scoring a directory."""
    scorer = RiskScorer()
    
    # Create multiple template files
    template1 = {
        "resources": [{
            "type": "Microsoft.Storage/storageAccounts",
            "name": "storage1",
            "properties": {"supportsHttpsTrafficOnly": False}
        }]
    }
    
    template2 = {
        "resources": [{
            "type": "Microsoft.Storage/storageAccounts",
            "name": "storage2",
            "properties": {"supportsHttpsTrafficOnly": True}
        }]
    }
    
    (tmp_path / "template1.json").write_text(json.dumps(template1))
    (tmp_path / "template2.json").write_text(json.dumps(template2))
    
    result = scorer.score_directory(str(tmp_path))
    
    assert result is not None
    assert result.metadata["resources_analyzed"] == 2


def test_score_directory_invalid():
    """Test scoring invalid directory."""
    scorer = RiskScorer()
    
    with pytest.raises(ValueError, match="Invalid directory"):
        scorer.score_directory("/nonexistent/directory")
