# Vision & Strategy

## North Star

**Reduce outages in production services by scoring code changes at PR time
and surfacing risk signals to engineers — before changes reach production.**

## Problem

Infrastructure-as-code changes are reviewed by humans with limited context.
Reviewers don't know whether a service has active incidents, a history of
outages, or a wide blast radius spanning dozens of subscriptions. This
context exists in IcM, Service Tree, SafeFly, and the deployment graph — but
it's scattered and not surfaced at review time.

## Solution

A deterministic risk scoring engine that:

1. Accepts a change identity (resource, service, or repo).
2. Resolves it to a service via Service Tree.
3. Gathers evidence from production data sources (IcM incidents, SafeFly
   deployments, Service Tree subscriptions, Neo4j graph).
4. Applies deterministic scoring rules — no ML, no randomness.
5. Produces a structured risk report (0-100 score + factor breakdown).

The same engine powers three interfaces: CLI, FastAPI REST API, and MCP
server (for AI agent consumption).

## Strategy

### Kusto-first hybrid

Kusto (Azure Data Explorer) is the primary evidence source:

- **IcM cluster** — incident counts, outage history, MTTM, related incidents
- **SafeFly cluster** — deployment frequency, stage failures
- **Service Tree cluster** — service identity resolution, subscription mapping

Neo4j is optional — useful for deep graph traversals (blast radius via
dependency chains, peer resources) but not required for the core flow.

### Coarse-grain mapping

Mapping is repo → service, not file → resource. This is intentional:

- Service Tree's `GetServicesByName()` and `GetSubscriptionsAssociatedWith()`
  operate at the service level.
- IcM incidents are tagged by `OwningTenantName` (service name), not by
  individual resources.
- This gives useful signal without requiring file-level resource resolution.

### Shadow mode first

The system will run in shadow mode before gating:

1. Score every PR and post a risk comment — but never block the merge.
2. Collect scores for 2-4 weeks to calibrate.
3. Analyze: do HIGH scores correlate with actual outages within 30 days?
4. Tune factor weights based on real data.
5. Only then enable gating (configurable score threshold to fail the
   pipeline).

## Phases

### Phase 1: Kusto-Powered Evidence ✅

Connect real data sources and wire all scoring factors.

- Kusto client wrapper (azure-kusto-data SDK)
- KQL query allowlist with parameter validation
- Pluggable evidence provider architecture
- Service Tree resolver (service name → ServiceId → subscriptions)
- CLI with `--service-name`, `--data-source` flags
- PR assessment API endpoint (`POST /api/v1/assess-pr`)

### Phase 2: AzDo Pipeline Integration (next)

PR-time scoring with PR comments.

- AzDo pipeline YAML template callable from any PR pipeline
- Posts markdown risk report as PR comment
- Shadow mode by default (comment, never block)
- Configurable gating threshold (disabled initially)

### Phase 3: Production Hardening

- Containerize and deploy to AKS
- AAD / Managed Identity auth for all connections
- Observability: structured logging, metrics, alerts
- Optional Neo4j for deep graph queries

## Success Metric

Reduction in outage count for services using risk scoring vs. control group.

Secondary metrics:

- Factor coverage: what % of assessments have all factors populated?
- Score distribution: are scores differentiated enough to be useful?
- Correlation: does HIGH score predict outages within 30 days?
- Adoption: how many teams integrate the pipeline task?

## Design Principles

1. **Deterministic.** Same input → same output. No timestamps in scoring,
   no randomness, no model drift. Scores are reproducible.
2. **Evidence-based.** Every factor cites specific evidence (incident
   counts, deployment stats). No gut feelings, no heuristics.
3. **Transparent.** The full factor breakdown is always shown. Engineers
   can see exactly why a score is HIGH and which evidence drove it.
4. **Graceful degradation.** Missing evidence → factor marked "unknown"
   with 0 points. The system never guesses.
5. **Auditable.** Every query is allowlisted. KQL templates are
   parameterized with injection-safe validation.
