"""Base rule interface for risk assessment."""
from abc import ABC, abstractmethod
from typing import List, Optional
from ..models import IaCResource, RiskFinding


class RiskRule(ABC):
    """Base class for risk assessment rules."""

    def __init__(self):
        self.rule_id: str = ""
        self.title: str = ""
        self.description: str = ""
        self.remediation: str = ""

    @abstractmethod
    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        """
        Evaluate a resource against this rule.
        
        Args:
            resource: The IaC resource to evaluate
            
        Returns:
            RiskFinding if rule is violated, None otherwise
        """
        pass

    @abstractmethod
    def applies_to(self, resource_type: str) -> bool:
        """
        Check if this rule applies to the given resource type.
        
        Args:
            resource_type: The type of resource
            
        Returns:
            True if rule applies to this resource type
        """
        pass
