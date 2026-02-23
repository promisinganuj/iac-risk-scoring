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


DEFAULT_RISK_MODEL_VERSION = "0.2"

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

    Model v0.2: 10 factors, max 100 points, no cap needed.
    All factors are available in Kusto-only mode (except change.destructive
    which depends on caller input).

    This function must not perform any DB queries; it only interprets `evidence`.
    """

    unknowns: List[str] = []
    factors: List[ScoreFactor] = []

    def unknown(field: str) -> None:
        unknowns.append(field)

    # Rule 1: SafeFly deployment-caused outages (15 pts).
    safefly_caused_outages = _require_int(evidence, "safefly_caused_outages_180d")
    if safefly_caused_outages is None:
        unknown("safefly_caused_outages_180d")
        factors.append(
            ScoreFactor(
                factor_id="deployment.change_caused_outages",
                title="SafeFly-caused outages (180d)",
                status="unknown",
                points=0,
                max_points=15,
                reason="safefly_caused_outages_180d is missing.",
                evidence={"safefly_caused_outages_180d": None},
            )
        )
    else:
        if safefly_caused_outages >= 3:
            pts = 15
        elif safefly_caused_outages >= 2:
            pts = 10
        elif safefly_caused_outages == 1:
            pts = 5
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="deployment.change_caused_outages",
                title="SafeFly-caused outages (180d)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=15,
                reason="Sev1/2 outages caused by SafeFly deployments indicate high deployment risk.",
                evidence={"safefly_caused_outages_180d": safefly_caused_outages},
            )
        )

    # Rule 2: incident recurrence (12 pts).
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

    # Rule 3: blast radius by subscription count (12 pts).
    subscription_count = _require_int(evidence, "subscription_count")
    if subscription_count is None:
        unknown("subscription_count")
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.subscriptions",
                title="Blast radius (subscriptions)",
                status="unknown",
                points=0,
                max_points=12,
                reason="subscription_count is missing.",
                evidence={"subscription_count": None},
            )
        )
    else:
        if subscription_count >= 10:
            pts = 12
        elif subscription_count >= 5:
            pts = 8
        elif subscription_count >= 2:
            pts = 5
        elif subscription_count == 1:
            pts = 2
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="blast_radius.subscriptions",
                title="Blast radius (subscriptions)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=12,
                reason="More subscriptions under a service increases the blast radius.",
                evidence={"subscription_count": subscription_count},
            )
        )

    # Rule 4: recent outages (10 pts).
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

    # Rule 5: slow incident mitigation — MTTM (10 pts).
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

    # Rule 6: deployment frequency (10 pts).
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

    # Rule 7: destructive operations (10 pts).
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

    # Rule 8: incident severity mix — Sev1/Sev2 ratio (8 pts).
    # Measures how many of the recent incidents were Sev1 or Sev2.
    sev12_incident_count = _require_int(evidence, "sev12_incident_count")
    if sev12_incident_count is None:
        unknown("sev12_incident_count")
        factors.append(
            ScoreFactor(
                factor_id="incident.severity_mix",
                title="High-severity incidents (Sev1/2, 180d)",
                status="unknown",
                points=0,
                max_points=8,
                reason="sev12_incident_count is missing.",
                evidence={"sev12_incident_count": None},
            )
        )
    else:
        if sev12_incident_count >= 3:
            pts = 8
        elif sev12_incident_count >= 2:
            pts = 5
        elif sev12_incident_count == 1:
            pts = 3
        else:
            pts = 0
        factors.append(
            ScoreFactor(
                factor_id="incident.severity_mix",
                title="High-severity incidents (Sev1/2, 180d)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=8,
                reason="High-severity incidents indicate service fragility.",
                evidence={"sev12_incident_count": sev12_incident_count},
            )
        )

    # Rule 9: peer resources in same ResourceGroup (8 pts).
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

    # Rule 10: recent active outages (5 pts).
    recent_outages = _require_int(evidence, "recent_active_outages")
    if recent_outages is None:
        unknown("recent_active_outages")
        factors.append(
            ScoreFactor(
                factor_id="ops.recent_active_outages",
                title="Recent active outages (7d)",
                status="unknown",
                points=0,
                max_points=5,
                reason="recent_active_outages is missing.",
                evidence={"recent_active_outages": None},
            )
        )
    else:
        pts = 5 if recent_outages > 0 else 0
        factors.append(
            ScoreFactor(
                factor_id="ops.recent_active_outages",
                title="Recent active outages (7d)",
                status="hit" if pts > 0 else "miss",
                points=pts,
                max_points=5,
                reason="Active outage incidents increase operational risk during changes.",
                evidence={"recent_active_outages": recent_outages},
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
