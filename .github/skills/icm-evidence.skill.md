---
description: Gather incident and outage evidence from IcM for risk scoring
name: IcM Evidence Gathering
tools: ['icm-prod/*']
---
# IcM Evidence Gathering Skill

## Purpose

Given a **service name**, query the IcM MCP server to gather incident and
outage evidence. Returns a structured evidence object that the synthesizer
skill uses for scoring.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `service_name` | Yes | The IcM service/team name (matches `OwningTenantName`) |
| `lookback_days` | No | How far back to search (default: 180 days) |

## Outputs

Return a JSON object with these evidence keys:

```json
{
  "icm_team_id": "<string — IcM team ID>",
  "icm_team_name": "<string — resolved team name>",
  "recent_active_outages": "<int — active Sev1/2 incidents in last 7 days>",
  "historical_outages_180d": "<int — Sev1/2 incidents in last 180 days>",
  "sev12_incident_count": "<int — total Sev1+Sev2 count in 180d>",
  "avg_mttm_minutes": "<int — average time-to-mitigate in minutes>",
  "related_incidents": "<int — count of similar incidents found>",
  "open_icms": "<int — currently active incidents>",
  "customer_impact_summary": "<string — S500/ACE customer impact narrative>",
  "ai_incident_summary": "<string — AI-generated summary of recent incidents>",
  "raw_incidents": "<list — raw incident details for cross-reference>"
}
```

## Procedure

### Step 1: Resolve Service to Team ID

Call `get_teams_by_name` to find the IcM team:

```
get_teams_by_name(teamName: "<service_name>")
```

- Extract `teamId` from the response.
- If no match, try `get_services_by_names(serviceNames: ["<service_name>"])` as fallback.
- If still no match, return all evidence keys as `null` with a note explaining
  the service was not found in IcM.

Store `icm_team_id` and `icm_team_name`.

### Step 2: Search Incidents by Team

Call `search_incidents_by_owning_team_id` to get recent incidents:

```
search_incidents_by_owning_team_id(
  teamId: "<icm_team_id>",
  incidentCountToFetch: 50
)
```

From the returned incidents, compute:

- **`recent_active_outages`**: Count incidents where severity ≤ 2 AND
  status is active/mitigated AND created within last 7 days.
- **`historical_outages_180d`**: Count incidents where severity ≤ 2 AND
  created within last 180 days.
- **`sev12_incident_count`**: Count all Sev1 + Sev2 incidents in 180 days.
- **`open_icms`**: Count incidents with active status (not resolved/closed).

### Step 3: Compute MTTM

For each Sev1/Sev2 incident in the last 180 days that has been mitigated
or resolved, compute time-to-mitigate:

- If `MitigatedDate` and `CreateDate` are available from the search results,
  compute `MTTM = MitigatedDate - CreateDate` in minutes.
- If not available in search results, call `get_incident_details_by_id`
  for up to 10 recent Sev1/2 incidents to get precise timestamps.

```
get_incident_details_by_id(incidentId: <id>)
```

Compute **`avg_mttm_minutes`** as the average across all sampled incidents.
Round to nearest integer.

### Step 4: Find Similar Incidents

Pick the most recent Sev1/2 incident and call:

```
get_similar_incidents(incidentId: <most_recent_sev12_id>)
```

Set **`related_incidents`** to the count of similar incidents returned.

### Step 5: Customer Impact (Enrichment)

For the most impactful recent incident (highest severity, most recent),
gather customer impact data:

```
get_impacted_s500_customers(incidentId: <id>)
get_impacted_ace_customers(incidentId: <id>)
```

Summarize into **`customer_impact_summary`**: e.g., "3 S500 customers and
1 ACE customer impacted by incident #12345."

If no Sev1/2 incidents exist, skip this step and set to `null`.

### Step 6: AI Summary (Enrichment)

For the most recent Sev1/2 incident:

```
get_ai_summary(incidentId: <id>)
```

Store as **`ai_incident_summary`** — this provides rich narrative context
for the final report (not used for scoring, but valuable for the user).

### Step 7: Store Raw Incidents

Save the incident list as **`raw_incidents`** — the EV2 skill may
cross-reference deployment times with incident times to detect
deployment-caused outages.

Each entry should include at minimum:
- `incident_id`
- `severity`
- `status`
- `create_date`
- `mitigated_date` (if available)
- `title`

## Error Handling

- If `get_teams_by_name` returns no results, set all evidence to `null`
  and note: "Service not found in IcM. The service name may not match any
  IcM team. Try an alternate name."
- If individual tool calls fail, set that specific evidence key to `null`
  and continue with remaining steps. Never fail the entire skill.
- Rate limit: If fetching incident details for MTTM, limit to 10 incidents
  max to avoid excessive API calls.

## Example Output

```json
{
  "icm_team_id": "12345",
  "icm_team_name": "Azure App Service (Payments)",
  "recent_active_outages": 1,
  "historical_outages_180d": 4,
  "sev12_incident_count": 6,
  "avg_mttm_minutes": 47,
  "related_incidents": 3,
  "open_icms": 2,
  "customer_impact_summary": "2 S500 customers impacted by incident #98765",
  "ai_incident_summary": "A routing misconfiguration caused payment processing failures across 3 regions...",
  "raw_incidents": [
    {
      "incident_id": 98765,
      "severity": 2,
      "status": "Mitigated",
      "create_date": "2026-01-15T08:00:00Z",
      "mitigated_date": "2026-01-15T09:23:00Z",
      "title": "Payment processing failures in West US 2"
    }
  ]
}
```
