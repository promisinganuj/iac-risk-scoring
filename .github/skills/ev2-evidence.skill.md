---
description: Gather deployment and service topology evidence from EV2 for risk scoring
name: EV2 Evidence Gathering
tools: ['ev2-mcp/get_*']
---
# EV2 Evidence Gathering Skill

## Purpose

Given EV2 service identifiers, query the EV2 MCP server to gather deployment
history, stage failure data, and service topology evidence. Returns a
structured evidence object for the synthesizer skill.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `ev2_service_id` | Yes | EV2 service identifier (GUID or short name) |
| `service_group_name` | Yes | EV2 service group name |
| `lookback_days` | No | Deployment history window (default: 30 days for frequency, 180 for failures) |
| `raw_incidents` | No | Incident list from IcM skill (for cross-referencing deployment-caused outages) |

## Outputs

Return a JSON object with these evidence keys:

```json
{
  "ev2_service_id": "<string — resolved EV2 service ID>",
  "ev2_service_group": "<string — service group name>",
  "deployment_count_30d": "<int — rollouts in last 30 days>",
  "deployment_stage_failures": "<int — failed stages in last 180 days>",
  "safefly_caused_outages_180d": "<int — rollouts correlated with IcM outages>",
  "service_regions": "<list — regions where service is deployed>",
  "region_count": "<int — number of deployment regions>",
  "registered_subscriptions": "<list — subscription details>",
  "subscription_count": "<int — number of production subscriptions>",
  "latest_rollout_status": "<string — status of most recent rollout>",
  "recent_rollouts": "<list — summary of recent rollouts>"
}
```

## Procedure

### Step 1: Validate Service Identity

Call `get_service_info` to confirm the EV2 service exists:

```
get_service_info(serviceId: "<ev2_service_id>")
```

- If the service is found, store `ev2_service_id` and note the service name.
- If not found, return all evidence keys as `null` with a note.

### Step 2: Deployment Frequency (30 days)

Call `list_rollout_history_for_custom_time_period` to get recent rollouts:

```
list_rollout_history_for_custom_time_period(
  serviceId: "<ev2_service_id>",
  serviceGroupName: "<service_group_name>",
  startTime: "<ISO 8601 — 30 days ago>",
  endTime: "<ISO 8601 — now>"
)
```

Count the returned rollouts → **`deployment_count_30d`**.

Store the rollout list as **`recent_rollouts`** (for stage failure analysis).

### Step 3: Deployment Stage Failures (180 days)

Call `list_rollout_history_for_custom_time_period` with a 180-day window:

```
list_rollout_history_for_custom_time_period(
  serviceId: "<ev2_service_id>",
  serviceGroupName: "<service_group_name>",
  startTime: "<ISO 8601 — 180 days ago>",
  endTime: "<ISO 8601 — now>"
)
```

For rollouts with non-success status, call `get_rollout_summary` to get
stage-level details:

```
get_rollout_summary(
  serviceId: "<ev2_service_id>",
  serviceGroupName: "<service_group_name>",
  rolloutId: "<rollout_id>"
)
```

Count stages with failed/error status across all rollouts →
**`deployment_stage_failures`**.

Limit to examining the 20 most recent non-success rollouts to avoid
excessive API calls.

### Step 4: Deployment-Caused Outages (Cross-Reference)

If `raw_incidents` is provided from the IcM skill, cross-reference:

1. For each Sev1/2 incident in the last 180 days, check if a rollout
   occurred within a 2-hour window before the incident's `create_date`.
2. Count matches → **`safefly_caused_outages_180d`**.

This is a heuristic correlation — if a deployment happened shortly before
an outage, it's flagged as potentially deployment-caused.

If `raw_incidents` is not available, set to `null`.

### Step 5: Service Presence (Regional Blast Radius)

Call `get_service_presence` to discover where the service is deployed:

```
get_service_presence(serviceId: "<ev2_service_id>")
```

Extract the list of regions → **`service_regions`**.
Count → **`region_count`**.

### Step 6: Registered Subscriptions

Call `get_registered_subscription` to get subscription details:

```
get_registered_subscription(
  serviceId: "<ev2_service_id>",
  serviceGroupName: "<service_group_name>"
)
```

- Store subscription details → **`registered_subscriptions`**.
- Count production subscriptions → **`subscription_count`**
  (filter by environment label if available, otherwise count all).

### Step 7: Latest Rollout Status

From the rollouts retrieved in Step 2, identify the most recent one.
Store its status → **`latest_rollout_status`** (e.g., "Completed",
"Failed", "InProgress", "Cancelled").

If available, call `get_rollout_details` for richer detail:

```
get_rollout_details(
  serviceId: "<ev2_service_id>",
  serviceGroupName: "<service_group_name>"
)
```

## Error Handling

- If `get_service_info` fails or returns no results, set all evidence
  to `null` and note: "EV2 service not found. Check the service ID and
  service group name."
- If individual steps fail, set that evidence key to `null` and continue.
- When examining rollout details for stage failures, limit to 20 rollouts.
- For time-based queries, use ISO 8601 UTC timestamps.

## Example Output

```json
{
  "ev2_service_id": "12345678-abcd-efgh-ijkl-123456789012",
  "ev2_service_group": "payments-svc",
  "deployment_count_30d": 14,
  "deployment_stage_failures": 3,
  "safefly_caused_outages_180d": 1,
  "service_regions": ["West US 2", "East US", "West Europe", "Southeast Asia"],
  "region_count": 4,
  "registered_subscriptions": [
    {"subscription_id": "sub-001", "name": "payments-prod-wus2"},
    {"subscription_id": "sub-002", "name": "payments-prod-eus"}
  ],
  "subscription_count": 2,
  "latest_rollout_status": "Completed",
  "recent_rollouts": [
    {
      "rollout_id": "r-2026-0215-001",
      "status": "Completed",
      "start_time": "2026-02-15T10:00:00Z",
      "end_time": "2026-02-15T11:30:00Z"
    }
  ]
}
```
