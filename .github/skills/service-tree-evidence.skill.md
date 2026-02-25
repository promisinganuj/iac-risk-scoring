---
description: Gather service identity, subscription blast radius, HVT/TCB status, and compliance evidence from Service Tree
name: Service Tree Evidence Gathering
tools: ['service-tree/*']
---
# Service Tree Evidence Gathering Skill

## Purpose

Given a service name, query the Service Tree MCP server to validate the
service identity, gather production subscription data (blast radius),
determine High Value Target (HVT) / Trusted Computing Base (TCB) status,
and surface compliance signals like DHE violations.

Service Tree is the **authoritative source** for:
- Service identity and metadata
- Production subscription mappings (blast radius — Factor 3)
- HVT/TCB classification
- Repo-to-service resolution

This skill should run **before** IcM and EV2 skills because it validates
the service and provides context that downstream skills may use.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `service_name` | Yes | The service name as it appears in Service Tree |
| `repo_name` | No | Repository name (for repo→service resolution if service_name is unknown) |

## Outputs

Return a JSON object with these evidence keys:

```json
{
  "service_identity": {
    "service_name": "<string — canonical Service Tree name>",
    "service_id": "<string — Service Tree service ID>",
    "organization": "<string — owning org>",
    "division": "<string — owning division>",
    "service_group": "<string — service group>",
    "metadata": "<object — additional service metadata>"
  },
  "prod_subscriptions": "<list — production subscription details>",
  "subscription_count": "<int — number of production subscriptions>",
  "all_subscriptions": "<list — all subscriptions (prod + non-prod)>",
  "all_subscription_count": "<int — total subscription count>",
  "is_hvt": "<bool — is this a High Value Target service?>",
  "is_tcb": "<bool — is this a Trusted Computing Base service?>",
  "dhe_violations": "<list — DHE violation details>",
  "dhe_violation_count": "<int — number of DHE violations>",
  "pc_codes": "<list — PC codes for the service>",
  "resolved_from_repo": "<bool — was service_name resolved from repo_name?>"
}
```

## Procedure

### Step 1: Resolve Service Identity

If `service_name` is provided, call `get_service_details` to validate:

```
get_service_details(ServiceName: "<service_name>")
```

- If found, store service identity fields (name, ID, org, division).
- If NOT found and `repo_name` is provided, try Step 1b.
- If NOT found and no `repo_name`, return all evidence as `null` with note.

### Step 1b: Repo-to-Service Resolution (Fallback)

If the service name was not found but a `repo_name` is available:

```
get_services_for_repo(RepoName: "<repo_name>")
```

- If this returns one or more services, use the first match as the resolved
  service name, set `resolved_from_repo = true`, and re-run Step 1 with
  the resolved name.
- If no match, return all evidence as `null`.

### Step 2: Service Metadata

Call `get_service_metadata_for_service` for richer context:

```
get_service_metadata_for_service(ServiceName: "<service_name>")
```

Store as `service_identity.metadata`.

Optionally call `get_moreservice_details` if additional fields are needed:

```
get_moreservice_details(ServiceName: "<service_name>")
```

### Step 3: Production Subscriptions (Blast Radius)

Call `get_prod_subscriptions_for_service` to get **production** subscriptions:

```
get_prod_subscriptions_for_service(ServiceName: "<service_name>")
```

- Store the list → **`prod_subscriptions`**
- Count → **`subscription_count`** (this feeds Factor 3: Blast Radius — Subscriptions)

Also call `get_subscriptions_for_service` for the complete picture:

```
get_subscriptions_for_service(ServiceName: "<service_name>")
```

- Store → **`all_subscriptions`**
- Count → **`all_subscription_count`**

**Important:** `subscription_count` (production only) is the value used
for Factor 3 scoring. `all_subscription_count` is advisory context.

### Step 4: HVT/TCB Classification

Call `get_hvt_and_tcb_services` to get the HVT and TCB service lists:

```
get_hvt_and_tcb_services()
```

Search the returned list for the current service name:
- If found in HVT list → **`is_hvt = true`**
- If found in TCB list → **`is_tcb = true`**
- If found in both → both true
- If not found → both false

**Note:** HVT/TCB status is an enrichment signal, not part of the
numeric score. However, it is a critical context flag — HVT services
warrant extra caution regardless of the numeric risk score.

### Step 5: DHE Compliance Violations

Call `get_dhe_violations_for_service` to check compliance:

```
get_dhe_violations_for_service(ServiceName: "<service_name>")
```

- Store violation details → **`dhe_violations`**
- Count → **`dhe_violation_count`**

DHE violations are an enrichment signal — they appear in the report as
a compliance concern but do not contribute to the numeric score.

### Step 6: PC Codes

Call `get_pccodes_for_services` for financial/org traceability:

```
get_pccodes_for_services(ServiceName: "<service_name>")
```

- Store → **`pc_codes`** (enrichment — not scored)

## Error Handling

- If `get_service_details` returns no results, return all evidence as `null`.
  Note: "Service not found in Service Tree. Verify the service name."
- If individual steps fail (e.g., `get_prod_subscriptions_for_service`
  returns an error), set that evidence key to `null` and continue with
  remaining steps.
- The `get_hvt_and_tcb_services` call returns all HVT/TCB services. If it
  fails, set `is_hvt` and `is_tcb` to `null`.
- For repo resolution (Step 1b), if multiple services map to the same repo,
  use the first result and note the ambiguity.

## Example Output

```json
{
  "service_identity": {
    "service_name": "Azure App Service (Payments)",
    "service_id": "svc-12345",
    "organization": "Azure Compute",
    "division": "Cloud + AI",
    "service_group": "App Service",
    "metadata": {
      "category": "PaaS",
      "lifecycle_stage": "GA",
      "pm_owner": "jane@microsoft.com"
    }
  },
  "prod_subscriptions": [
    {"subscription_id": "sub-001", "name": "payments-prod-wus2"},
    {"subscription_id": "sub-002", "name": "payments-prod-eus"},
    {"subscription_id": "sub-003", "name": "payments-prod-weu"}
  ],
  "subscription_count": 3,
  "all_subscriptions": [
    {"subscription_id": "sub-001", "name": "payments-prod-wus2"},
    {"subscription_id": "sub-002", "name": "payments-prod-eus"},
    {"subscription_id": "sub-003", "name": "payments-prod-weu"},
    {"subscription_id": "sub-dev-001", "name": "payments-dev"}
  ],
  "all_subscription_count": 4,
  "is_hvt": true,
  "is_tcb": false,
  "dhe_violations": [],
  "dhe_violation_count": 0,
  "pc_codes": ["PC-12345"],
  "resolved_from_repo": false
}
```
