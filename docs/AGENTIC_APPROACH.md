# Agentic Risk Scoring via MCP Skills

## Context

The existing deterministic risk scoring engine gathers evidence by running
**KQL queries against Kusto clusters** (IcM, SafeFly, Service Tree, ARG).
This requires the Azure Kusto SDK, multi-cluster auth, and a hand-maintained
KQL allowlist with parameter validation.

We now have access to four MCP servers that expose the source systems
directly:

| MCP Server | Scope | Key Capabilities |
|------------|-------|-------------------|
| **Service Tree** (`service-tree`) | Tenant-wide | Service identity, production subscriptions, HVT/TCB classification, DHE compliance, org hierarchy, repo→service mapping |
| **IcM** (`icm-prod`) | Tenant-wide | Incident search, details, severity, MTTM, customer impact, similar incidents, AI summaries |
| **EV2** (`ev2-mcp`) | Tenant-wide | Rollout history, stage failures, service presence (regions), subscriptions, service groups |
| **Azure DevOps** (`ado`) | Single org | Builds/pipelines, security alerts (AdvSec), commits, PRs, repos, code search |

## The Idea

Instead of touching the existing deterministic engine, we build a **parallel
agentic approach** that uses an AI agent + MCP tools directly. The agent
_is_ the scoring engine — it gathers evidence by calling MCP tools, applies
a prompt-defined scoring rubric, and synthesizes a risk report.

### Deterministic Engine vs. Agentic Approach

| Aspect | Deterministic Engine | Agentic Approach |
|--------|---------------------|------------------|
| Evidence source | KQL queries → Kusto clusters | MCP tool calls → Service Tree/IcM/EV2/ADO APIs |
| Service identity | Kusto k7 query (Service Tree cluster) | Service Tree MCP: `get_service_details` |
| Subscription mapping | Kusto k10 query | Service Tree MCP: `get_prod_subscriptions_for_service` |
| HVT/TCB detection | Not available | Service Tree MCP: `get_hvt_and_tcb_services` |
| DHE compliance | Not available | Service Tree MCP: `get_dhe_violations_for_service` |
| Scoring | Hardcoded rules in Python (`scoring.py`) | Agent-applied rubric (prompt-defined) |
| Modularity | Monolithic provider classes | Skills-based (composable, independently testable) |
| Extensibility | Add KQL query + Python rule | Add a skill file |
| Customer impact | Not available | IcM `get_impacted_s500_customers` |
| Regional blast radius | Not available | EV2 `get_service_presence` |
| Pipeline health | Not available | ADO `get_builds` |
| Security posture | Not available | ADO `get_alerts` (AdvSec) |
| Auth | Multi-cluster Kusto SDK + env vars | MCP servers handle their own auth |

## Architecture

```
User: "Assess risk for service X in prod"
         │
         ▼
┌───────────────────────────────────────────┐
│  risk-scoring-agentic.agent.md            │
│  (Orchestrator Agent)                     │
│                                           │
│  1. Parse inputs (service, env, repo)     │
│  2. Invoke skills sequentially            │
│  3. Combine evidence                      │
│  4. Produce final report                  │
└──┬───────────┬───────────┬───────────┬────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Service │ │ IcM     │ │ EV2     │ │ ADO     │
│Tree    │ │ Skill   │ │ Skill   │ │ Skill   │
│Skill   │ │         │ │         │ │         │
│        │ │icm-prod │ │ev2-mcp  │ │ado tools│
│service-│ │ tools   │ │ tools   │ │         │
│tree    │ │         │ │         │ │         │
│tools   │ │         │ │         │ │         │
└───┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
    │           │           │           │
    └───────────┴─────┬─────┴───────────┘
                      │
                      ▼
┌──────────────────────────────────────────┐
│  risk-synthesizer.skill.md               │
│                                          │
│  Takes all evidence from all skills      │
│  Applies scoring rubric (10 factors)     │
│  Produces structured risk report         │
└──────────────────────────────────────────┘
```

### Execution Order

1. **Service Tree** (first) — validates the service, provides canonical
   identity and production subscription count for blast radius scoring
2. **IcM** — incident evidence using the validated service name
3. **EV2** — deployment evidence (if identifiers provided)
4. **ADO** (optional) — pipeline/security enrichment
5. **Synthesizer** — scoring and report generation

Service Tree runs first because it provides:
- Service identity validation (does this service exist?)
- Production subscription count (authoritative source for Factor 3)
- HVT/TCB flags (critical context for the report)
- Repo→service resolution (fallback if user provides repo instead of service name)

## Skills Design

Each skill is a `.skill.md` file that:
- Declares which MCP tools it needs (via `tools` frontmatter)
- Defines the inputs it expects and outputs it produces
- Contains step-by-step instructions for one evidence domain
- Is independently invocable (call the skill alone for testing)

### Skill Inventory

| Skill | File | MCP Tools Used | Evidence Produced |
|-------|------|----------------|-------------------|
| **Service Tree Evidence** | `service-tree-evidence.skill.md` | `service-tree/*` | Service identity, production subscriptions (blast radius), HVT/TCB status, DHE violations, PC codes |
| **IcM Evidence** | `icm-evidence.skill.md` | `icm-prod/*` | Team ID, incidents, outages, MTTM, severity, customer impact, similar incidents, AI summary |
| **EV2 Evidence** | `ev2-evidence.skill.md` | `ev2-mcp/*` | Rollout history, deployment count, stage failures, regional presence, subscriptions (fallback) |
| **ADO Evidence** | `ado-evidence.skill.md` | `ado/*` | Pipeline health, security alerts, commit velocity, PR review quality |
| **Risk Synthesizer** | `risk-synthesizer.skill.md` | (none — pure reasoning) | Risk score, factor breakdown, recommendations |

## Evidence → Factor Mapping

### Tier 1: Core Factors (Service Tree + IcM + EV2 — always available)

| # | Factor | Max Pts | Evidence Source | MCP Tool Chain |
|---|--------|---------|-----------------|----------------|
| 1 | SafeFly/EV2-caused outages (180d) | 15 | IcM incidents cross-referenced with EV2 rollouts | `search_incidents_by_owning_team_id` + `list_rollout_history_for_custom_time_period` |
| 2 | Similar past incidents | 12 | IcM similar incident lookup | `search_incidents_by_owning_team_id` → pick recent → `get_similar_incidents` |
| 3 | Blast radius — subscriptions | 12 | **Service Tree** production subscriptions (fallback: EV2) | `get_prod_subscriptions_for_service` (preferred) or `get_registered_subscription` (fallback) |
| 4 | Recent outages (180d) | 10 | IcM incident search filtered by date | `search_incidents_by_owning_team_id` → filter Sev1/2 |
| 5 | Slow incident mitigation (MTTM) | 10 | IcM incident details (timestamps) | `get_incident_details_by_id` per incident → compute avg |
| 6 | Deployment frequency (30d) | 10 | EV2 rollout history | `list_rollout_history_for_custom_time_period` (last 30d) |
| 7 | Destructive operations | 10 | Caller-supplied (change context) | N/A — user provides |
| 8 | High-severity incidents (Sev1/2) | 8 | IcM incident search | `search_incidents_by_owning_team_id` → filter severity |
| 9 | Regional blast radius | 8 | EV2 service presence | `get_service_presence` → count regions |
| 10 | Recent active outages (7d) | 5 | IcM incidents filtered recent + active | `search_incidents_by_owning_team_id` → filter |

### Tier 2: Enrichment Factors (Advisory — not scored)

| # | Factor | Source | MCP Tool Chain |
|---|--------|--------|----------------|
| E1 | Pipeline health | ADO | `get_builds` with time filter → count failures |
| E2 | Security posture | ADO | `get_alerts` with `states: ["Active"]` |
| E3 | Customer impact history | IcM | `get_impacted_s500_customers` per incident |
| E4 | HVT/TCB classification | Service Tree | `get_hvt_and_tcb_services` → match service |
| E5 | DHE compliance violations | Service Tree | `get_dhe_violations_for_service` |
| E6 | Change velocity | ADO | `search_commits` in last 30d |

**Total maximum (Tier 1):** 100 pts.
**Enrichment factors** are advisory — surfaced in the report as additional context but not added to the 100-point score.

## Resolution Chain

The agent needs to resolve identities across systems:

```
Service Name (user input)
    │
    ├─→ Service Tree: get_service_details(ServiceName)
    │        → canonical name, service ID, org, division
    │        → get_prod_subscriptions_for_service(ServiceName) → subscription count
    │        → get_hvt_and_tcb_services() → HVT/TCB flag
    │
    ├─→ IcM: get_teams_by_name(ServiceName)
    │        → teamId (for incident search)
    │
    ├─→ EV2: requires serviceId (GUID) + serviceGroupName
    │        → user provides, or agent asks
    │
    └─→ ADO: requires project + repository name
             → user provides repo URI, or discovered from context

Fallback: If service_name unknown but repo is provided:
    Service Tree: get_services_for_repo(RepoName) → resolved service name
```

### Key Constraints

- **ADO is single-org.** The ADO MCP server is connected to one Azure DevOps
  organization. ADO-based factors are only available for repos in that org.
- **Subscription source priority.** Service Tree is the canonical source for
  production subscriptions (Factor 3). EV2 subscriptions are a fallback.

## File Layout

```
.github/
  agents/
    risk-scoring-agentic.agent.md          # Main orchestrator agent
  skills/
    service-tree-evidence.skill.md         # Service Tree identity/subscription/HVT evidence
    icm-evidence.skill.md                  # IcM incident evidence gathering
    ev2-evidence.skill.md                  # EV2 deployment evidence gathering
    ado-evidence.skill.md                  # AzDo repo/pipeline evidence
    risk-synthesizer.skill.md              # Score synthesis and reporting
```

## Usage

Invoke the agent in VS Code Copilot Chat:

```
@risk-scoring-agentic Assess risk for "Azure App Service (Payments)"
in prod. EV2 service ID is 12345678-abcd-efgh-ijkl-123456789012,
service group is "payments-svc".
```

The agent will:
1. Call the Service Tree skill to validate identity and get blast radius
2. Call the IcM skill to gather incident evidence
3. Call the EV2 skill to gather deployment evidence
4. Optionally call the ADO skill if a repo is known
5. Call the synthesizer skill to score and produce the report

## Design Principles

1. **No code changes.** The entire approach is prompt-based — no Python,
   no new dependencies, no config files.
2. **Skills are composable.** Each skill works independently. You can
   invoke just the IcM skill to get incident data without scoring.
3. **Graceful degradation.** Missing Service Tree match? Fall back to EV2
   for subscriptions. Missing EV2 service ID? Skip EV2 factors. No repo?
   Skip ADO factors. The score adjusts.
4. **Transparent.** Every MCP tool call is visible in the chat. The user
   sees exactly what data was gathered and how it was scored.
5. **Extensible.** Adding a new factor = adding a skill or extending an
   existing one. No code deployment needed.
6. **Authoritative sources first.** Service Tree is the canonical source
   for service identity and production subscriptions. Other sources are
   supplementary or fallbacks.
