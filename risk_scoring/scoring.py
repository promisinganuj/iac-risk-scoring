from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
FactorStatus = Literal["hit", "miss", "unknown", "na"]


@dataclass(frozen=True)
class ChangeContext:
    """Canonical change inputs for deterministic scoring.

    This is intentionally small for now (Approach 2 MVP) and can be extended
    later by the canonicalization feature.
    """

    environment: Optional[str] = None
    operations: Tuple[str, ...] = ()

    @staticmethod
    def normalize_environment(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip().lower()
        if not v:
            return None
        # Keep a small normalized set; anything else is preserved but lowercased.
        if v in {"prod", "production"}:
            return "prod"
        if v in {"stage", "staging"}:
            return "staging"
        if v in {"dev", "development"}:
            return "dev"
        if v in {"test", "testing"}:
            return "test"
        return v

    @staticmethod
    def normalize_operation(value: str) -> str:
        return value.strip().lower()

    @classmethod
    def create(
        cls, *, environment: Optional[str] = None, operations: Optional[Sequence[str]] = None
    ) -> "ChangeContext":
        ops: Tuple[str, ...] = ()
        if operations:
            # Canonicalize operations for determinism (input order should not matter).
            normalized = [cls.normalize_operation(o) for o in operations if o and o.strip()]
            ops = tuple(sorted(set(normalized)))
        return cls(environment=cls.normalize_environment(environment), operations=ops)


@dataclass(frozen=True)
class ScoreFactor:
    """A single scoring factor produced by a rule."""

    factor_id: str
    title: str
    status: FactorStatus
    points: int
    max_points: int
    reason: str
    evidence: Dict[str, Any]


@dataclass(frozen=True)
class ScoreResult:
    risk_model_version: str
    risk_score: int
    risk_level: RiskLevel
    factors: Tuple[ScoreFactor, ...]
    unknowns: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_model_version": self.risk_model_version,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "factors": [asdict(f) for f in self.factors],
            "unknowns": list(self.unknowns),
        }


DEFAULT_RISK_MODEL_VERSION = "0.1"

# Deterministic thresholds.
_LOW_MAX = 33
_MEDIUM_MAX = 66


def _risk_level(score: int) -> RiskLevel:
    if score <= _LOW_MAX:
        return "LOW"
    if score <= _MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


def _require_int(evidence: Dict[str, Any], key: str) -> Optional[int]:
    val = evidence.get(key)
    if val is None:
        return None
    if isinstance(val, bool):
        # bool is a subclass of int; explicitly reject.
        raise TypeError(f"Evidence field '{key}' must be an int, got bool")
    if not isinstance(val, int):
        raise TypeError(f"Evidence field '{key}' must be an int, got {type(val).__name__}")
    return val


def _require_str_list(evidence: Dict[str, Any], key: str) -> Optional[List[str]]:
    val = evidence.get(key)
    if val is None:
        return None
    if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
        raise TypeError(f"Evidence field '{key}' must be a list[str]")
    return val


def score_change(
    change: ChangeContext,
    evidence: Dict[str, Any],
    *,
    risk_model_version: str = DEFAULT_RISK_MODEL_VERSION,
) -> ScoreResult:
    """Compute a deterministic risk score from already-gathered evidence.

    This function must not perform any DB queries; it only interprets `evidence`.
    """

    unknowns: List[str] = []
    factors: List[ScoreFactor] = []

    def unknown(field: str) -> None:
        unknowns.append(field)

    # Rule 1: production environment.
    if change.environment is None:
        unknown("change.environment")
        factors.append(
            ScoreFactor(
                factor_id="env.production",
                title="Production environment",
                status="unknown",
                points=0,
                max_points=20,
                reason="Change environment is missing.",
                evidence={"environment": None},
            )
        )
    elif change.environment == "prod":
        factors.append(
            ScoreFactor(
                factor_id="env.production",
                title="Production environment",
                status="hit",
                points=20,
                max_points=20,
                reason="Changes in production carry higher risk.",
                evidence={"environment": change.environment},
            )
        )
    else:
        factors.append(
            ScoreFactor(
                factor_id="env.production",
                title="Production environment",
                status="miss",
                points=0,
                max_points=20,
                reason="Non-production environments are generally lower risk.",
                evidence={"environment": change.environment},
            )
        )

    # Rule 2: blast radius by impacted services.
    services_impacted = _require_int(evidence, "services_impacted")
    if services_impacted is None:
        unknown("services_impacted")
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.services",
                title="Blast radius (services impacted)",
                status="unknown",
                points=0,
                max_points=25,
                reason="services_impacted is missing.",
                evidence={"services_impacted": None},
            )
        )
    else:
        if services_impacted >= 5:
            pts = 25
        elif services_impacted >= 3:
            pts = 18
        elif services_impacted == 2:
            pts = 10
        elif services_impacted == 1:
            pts = 5
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.services",
                title="Blast radius (services impacted)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=25,
                reason="More impacted services increases operational risk.",
                evidence={"services_impacted": services_impacted},
            )
        )

    # Rule 3: critical services.
    critical_services = _require_str_list(evidence, "critical_services")
    if critical_services is None:
        unknown("critical_services")
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.critical_services",
                title="Critical services impacted",
                status="unknown",
                points=0,
                max_points=15,
                reason="critical_services is missing.",
                evidence={"critical_services": None},
            )
        )
    else:
        pts = 15 if len(critical_services) > 0 else 0
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.critical_services",
                title="Critical services impacted",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=15,
                reason="Impacts to critical services are higher risk.",
                evidence={"critical_services": list(critical_services)},
            )
        )

    # Rule 4: recent outages.
    outages_180d = _require_int(evidence, "historical_outages_180d")
    if outages_180d is None:
        unknown("historical_outages_180d")
        factors.append(
            ScoreFactor(
                factor_id="history.outages_180d",
                title="Recent outages (180d)",
                status="unknown",
                points=0,
                max_points=10,
                reason="historical_outages_180d is missing.",
                evidence={"historical_outages_180d": None},
            )
        )
    else:
        if outages_180d <= 0:
            pts = 0
        elif outages_180d == 1:
            pts = 5
        else:
            pts = 10
        factors.append(
            ScoreFactor(
                factor_id="history.outages_180d",
                title="Recent outages (180d)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Recent outages suggest fragility and elevated change risk.",
                evidence={"historical_outages_180d": outages_180d},
            )
        )

    # Rule 5: open incidents (ICMs).
    open_icms = _require_int(evidence, "open_icms")
    if open_icms is None:
        unknown("open_icms")
        factors.append(
            ScoreFactor(
                factor_id="ops.open_icms",
                title="Open incidents",
                status="unknown",
                points=0,
                max_points=5,
                reason="open_icms is missing.",
                evidence={"open_icms": None},
            )
        )
    else:
        pts = 5 if open_icms > 0 else 0
        factors.append(
            ScoreFactor(
                factor_id="ops.open_icms",
                title="Open incidents",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=5,
                reason="Active incidents increase operational risk during changes.",
                evidence={"open_icms": open_icms},
            )
        )

    # Rule 6: deployment frequency.
    deployment_count_30d = _require_int(evidence, "deployment_count_30d")
    if deployment_count_30d is None:
        unknown("deployment_count_30d")
        factors.append(
            ScoreFactor(
                factor_id="ops.deployments_30d",
                title="Deployment frequency (30d)",
                status="unknown",
                points=0,
                max_points=10,
                reason="deployment_count_30d is missing.",
                evidence={"deployment_count_30d": None},
            )
        )
    else:
        if deployment_count_30d >= 20:
            pts = 10
        elif deployment_count_30d >= 10:
            pts = 5
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="ops.deployments_30d",
                title="Deployment frequency (30d)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Higher deployment cadence increases concurrent-change risk.",
                evidence={"deployment_count_30d": deployment_count_30d},
            )
        )

    # Rule 7: destructive operations.
    destructive_ops = {"delete", "destroy"}
    if not change.operations:
        # Explicitly NA instead of unknown: operations list is optional for MVP.
        factors.append(
            ScoreFactor(
                factor_id="change.destructive",
                title="Destructive operations",
                status="na",
                points=0,
                max_points=10,
                reason="No change operations provided.",
                evidence={"operations": []},
            )
        )
    else:
        is_destructive = any(op in destructive_ops for op in change.operations)
        pts = 10 if is_destructive else 0
        factors.append(
            ScoreFactor(
                factor_id="change.destructive",
                title="Destructive operations",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Destructive operations are higher risk.",
                evidence={"operations": list(change.operations)},
            )
        )

    # Rule 8: deployment stage failures.
    stage_failures = _require_int(evidence, "deployment_stage_failures")
    if stage_failures is None:
        unknown("deployment_stage_failures")
        factors.append(
            ScoreFactor(
                factor_id="deployment.stage_failures",
                title="Recent deployment stage failures",
                status="unknown",
                points=0,
                max_points=15,
                reason="deployment_stage_failures is missing.",
                evidence={"deployment_stage_failures": None},
            )
        )
    else:
        if stage_failures >= 3:
            pts = 15
        elif stage_failures >= 2:
            pts = 10
        elif stage_failures == 1:
            pts = 5
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="deployment.stage_failures",
                title="Recent deployment stage failures",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=15,
                reason="Failed deployment stages indicate deployment instability.",
                evidence={"deployment_stage_failures": stage_failures},
            )
        )

    # Rule 9: mean time to mitigate (MTTM).
    avg_mttm_minutes = _require_int(evidence, "avg_mttm_minutes")
    if avg_mttm_minutes is None:
        unknown("avg_mttm_minutes")
        factors.append(
            ScoreFactor(
                factor_id="incident.mttm",
                title="Slow incident mitigation",
                status="unknown",
                points=0,
                max_points=10,
                reason="avg_mttm_minutes is missing.",
                evidence={"avg_mttm_minutes": None},
            )
        )
    else:
        if avg_mttm_minutes >= 60:
            pts = 10
        elif avg_mttm_minutes >= 30:
            pts = 7
        elif avg_mttm_minutes >= 15:
            pts = 4
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="incident.mttm",
                title="Slow incident mitigation",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Slow mitigation suggests recovery challenges.",
                evidence={"avg_mttm_minutes": avg_mttm_minutes},
            )
        )

    # Rule 10: deep artifact dependencies.
    max_dependency_depth = _require_int(evidence, "max_dependency_depth")
    if max_dependency_depth is None:
        unknown("max_dependency_depth")
        factors.append(
            ScoreFactor(
                factor_id="artifact.deep_deps",
                title="Deep artifact dependency chains",
                status="unknown",
                points=0,
                max_points=10,
                reason="max_dependency_depth is missing.",
                evidence={"max_dependency_depth": None},
            )
        )
    else:
        if max_dependency_depth >= 3:
            pts = 10
        elif max_dependency_depth == 2:
            pts = 5
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="artifact.deep_deps",
                title="Deep artifact dependency chains",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Deep dependency chains increase cascading failure risk.",
                evidence={"max_dependency_depth": max_dependency_depth},
            )
        )

    # Rule 11: peer resources in same ResourceGroup.
    peer_resource_count = _require_int(evidence, "peer_resource_count")
    if peer_resource_count is None:
        unknown("peer_resource_count")
        factors.append(
            ScoreFactor(
                factor_id="resource.peer_impact",
                title="Resources in same ResourceGroup",
                status="unknown",
                points=0,
                max_points=8,
                reason="peer_resource_count is missing.",
                evidence={"peer_resource_count": None},
            )
        )
    else:
        if peer_resource_count >= 10:
            pts = 8
        elif peer_resource_count >= 5:
            pts = 5
        elif peer_resource_count >= 2:
            pts = 3
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="resource.peer_impact",
                title="Resources in same ResourceGroup",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=8,
                reason="More peer resources increase blast radius.",
                evidence={"peer_resource_count": peer_resource_count},
            )
        )

    # Rule 12: incident recurrence.
    related_incidents = _require_int(evidence, "related_incidents")
    if related_incidents is None:
        unknown("related_incidents")
        factors.append(
            ScoreFactor(
                factor_id="incident.recurrence",
                title="Similar past incidents",
                status="unknown",
                points=0,
                max_points=12,
                reason="related_incidents is missing.",
                evidence={"related_incidents": None},
            )
        )
    else:
        if related_incidents >= 3:
            pts = 12
        elif related_incidents >= 2:
            pts = 8
        elif related_incidents == 1:
            pts = 4
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="incident.recurrence",
                title="Similar past incidents",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=12,
                reason="Recurring incidents suggest systematic issues.",
                evidence={"related_incidents": related_incidents},
            )
        )

    # Rule 13: template complexity.
    required_dependency_count = _require_int(evidence, "template_required_dependency_count")
    max_dependency_depth = _require_int(evidence, "template_max_dependency_depth")
    
    if required_dependency_count is None or max_dependency_depth is None:
        if required_dependency_count is None:
            unknown("template_required_dependency_count")
        if max_dependency_depth is None:
            unknown("template_max_dependency_depth")
        factors.append(
            ScoreFactor(
                factor_id="template.complexity",
                title="Template dependency complexity",
                status="unknown",
                points=0,
                max_points=10,
                reason="Template dependency data is missing.",
                evidence={
                    "template_required_dependency_count": required_dependency_count,
                    "template_max_dependency_depth": max_dependency_depth,
                },
            )
        )
    else:
        pts = 0
        # Award 5 points if > 3 required dependencies
        if required_dependency_count > 3:
            pts += 5
        # Award 5 points if dependency chain depth > 2 hops
        if max_dependency_depth > 2:
            pts += 5
        
        factors.append(
            ScoreFactor(
                factor_id="template.complexity",
                title="Template dependency complexity",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=10,
                reason="Complex template dependencies increase deployment risk.",
                evidence={
                    "template_required_dependency_count": required_dependency_count,
                    "template_max_dependency_depth": max_dependency_depth,
                },
            )
        )

    score = sum(f.points for f in factors)
    if score > 100:
        score = 100

    # Deterministic unknown ordering.
    unknowns_sorted = tuple(sorted(set(unknowns)))

    return ScoreResult(
        risk_model_version=risk_model_version,
        risk_score=score,
        risk_level=_risk_level(score),
        factors=tuple(factors),
        unknowns=unknowns_sorted,
    )
