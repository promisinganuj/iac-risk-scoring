"""Data models for risk scoring."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class RiskLevel(Enum):
    """Risk severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def score(self) -> int:
        """Get numeric score for risk level."""
        return {
            RiskLevel.CRITICAL: 100,
            RiskLevel.HIGH: 75,
            RiskLevel.MEDIUM: 50,
            RiskLevel.LOW: 25,
            RiskLevel.INFO: 0,
        }[self]


class RiskCategory(Enum):
    """Categories of risks."""
    SECURITY = "security"
    COMPLIANCE = "compliance"
    RELIABILITY = "reliability"
    COST = "cost"
    PERFORMANCE = "performance"


@dataclass
class RiskFinding:
    """A single risk finding."""
    category: RiskCategory
    level: RiskLevel
    resource_type: str
    resource_name: str
    rule_id: str
    title: str
    description: str
    remediation: str
    location: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskScore:
    """Overall risk score for IaC changes."""
    total_score: int
    risk_level: RiskLevel
    findings: List[RiskFinding]
    summary: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_score": self.total_score,
            "risk_level": self.risk_level.value,
            "summary": self.summary,
            "findings": [
                {
                    "category": f.category.value,
                    "level": f.level.value,
                    "resource_type": f.resource_type,
                    "resource_name": f.resource_name,
                    "rule_id": f.rule_id,
                    "title": f.title,
                    "description": f.description,
                    "remediation": f.remediation,
                    "location": f.location,
                    "metadata": f.metadata,
                }
                for f in self.findings
            ],
            "metadata": self.metadata,
        }


@dataclass
class IaCResource:
    """Represents a resource in IaC template."""
    resource_type: str
    name: str
    properties: Dict[str, Any]
    location: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
