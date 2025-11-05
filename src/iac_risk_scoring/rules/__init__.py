"""Risk assessment rules for Azure resources."""
from .base import RiskRule
from .azure_rules import AzureSecurityRules

__all__ = ["RiskRule", "AzureSecurityRules"]
