"""Risk analyzer that applies rules to resources."""
from typing import List
from ..models import IaCResource, RiskFinding, RiskScore, RiskLevel
from ..rules.base import RiskRule


class RiskAnalyzer:
    """Analyzes IaC resources for risks using defined rules."""

    def __init__(self, rules: List[RiskRule]):
        """
        Initialize analyzer with rules.
        
        Args:
            rules: List of risk assessment rules to apply
        """
        self.rules = rules

    def analyze(self, resources: List[IaCResource]) -> RiskScore:
        """
        Analyze resources and generate risk score.
        
        Args:
            resources: List of IaC resources to analyze
            
        Returns:
            RiskScore with findings and overall score
        """
        findings: List[RiskFinding] = []

        # Evaluate each resource against applicable rules
        for resource in resources:
            for rule in self.rules:
                if rule.applies_to(resource.resource_type):
                    finding = rule.evaluate(resource)
                    if finding:
                        findings.append(finding)

        # Calculate overall score and risk level
        total_score = self._calculate_score(findings)
        risk_level = self._determine_risk_level(total_score)
        summary = self._generate_summary(findings)

        return RiskScore(
            total_score=total_score,
            risk_level=risk_level,
            findings=findings,
            summary=summary,
            metadata={
                "resources_analyzed": len(resources),
                "rules_applied": len(self.rules),
            }
        )

    def _calculate_score(self, findings: List[RiskFinding]) -> int:
        """Calculate total risk score from findings."""
        if not findings:
            return 0
        
        # Sum up risk scores, with diminishing returns for multiple findings
        total = sum(finding.level.score for finding in findings)
        
        # Apply a ceiling to prevent unrealistic scores
        return min(total, 100)

    def _determine_risk_level(self, score: int) -> RiskLevel:
        """Determine risk level based on score."""
        if score >= 90:
            return RiskLevel.CRITICAL
        elif score >= 70:
            return RiskLevel.HIGH
        elif score >= 40:
            return RiskLevel.MEDIUM
        elif score >= 10:
            return RiskLevel.LOW
        else:
            return RiskLevel.INFO

    def _generate_summary(self, findings: List[RiskFinding]) -> dict:
        """Generate summary statistics."""
        summary = {
            "total_findings": len(findings),
            "by_level": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0,
            },
            "by_category": {
                "security": 0,
                "compliance": 0,
                "reliability": 0,
                "cost": 0,
                "performance": 0,
            }
        }

        for finding in findings:
            summary["by_level"][finding.level.value] += 1
            summary["by_category"][finding.category.value] += 1

        return summary
