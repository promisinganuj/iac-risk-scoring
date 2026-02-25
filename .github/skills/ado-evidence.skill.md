---
description: Gather pipeline health and security evidence from Azure DevOps for risk scoring
name: ADO Evidence Gathering
tools: ['ado/*']
---
# Azure DevOps Evidence Gathering Skill

## Purpose

Given an Azure DevOps repository or project, query the ADO MCP server to
gather pipeline health, security posture, and change velocity evidence.
Returns a structured evidence object for the synthesizer skill.

**Important constraint:** This MCP server is connected to a single Azure
DevOps organization. Evidence is only available for repos within that org.
If the repo is not in this org, this skill should be skipped entirely.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `repo_uri` | Yes* | Full ADO repo URI (e.g., `https://dev.azure.com/org/project/_git/repo`) |
| `project_name` | Yes* | ADO project name (can be extracted from `repo_uri`) |
| `repository_name` | Yes* | ADO repository name (can be extracted from `repo_uri`) |

*Either `repo_uri` (from which project and repo are extracted) or both
`project_name` and `repository_name` must be provided.

## Outputs

Return a JSON object with these evidence keys:

```json
{
  "ado_project": "<string — ADO project name>",
  "ado_repository": "<string — repository name>",
  "pipeline_failure_rate_30d": "<float — % of failed builds in last 30d>",
  "failed_builds_30d": "<int — count of failed builds>",
  "total_builds_30d": "<int — total builds in last 30d>",
  "active_security_alerts": "<int — active AdvSec alerts (dependency + code + secret)>",
  "security_alert_breakdown": {
    "dependency": "<int>",
    "code": "<int>",
    "secret": "<int>"
  },
  "commit_count_30d": "<int — commits to default branch in last 30d>",
  "active_pr_count": "<int — open pull requests>",
  "pr_without_reviewers": "<int — open PRs with no reviewers assigned>"
}
```

## Procedure

### Step 1: Parse Repository Identity

If `repo_uri` is provided, extract:
- `project_name` from the URI path segment after the org
- `repository_name` from the segment after `_git/`

Example: `https://dev.azure.com/myorg/MyProject/_git/payments-api`
→ project = `MyProject`, repo = `payments-api`

### Step 2: Validate Repository Exists

Call `get_repo_by_name_or_id` to confirm the repo exists:

```
get_repo_by_name_or_id(
  projectName: "<project_name>",
  repoName: "<repository_name>"
)
```

If not found, return all evidence as `null` with a note: "Repository not
found in the connected ADO org."

### Step 3: Pipeline Health (Build Results)

Call `get_builds` to get recent build history:

```
get_builds(
  projectName: "<project_name>",
  repositoryId: "<repository_name>",
  repositoryType: "TfsGit",
  top: 50,
  minTime: "<ISO 8601 — 30 days ago>"
)
```

From the results:
- **`total_builds_30d`**: Count of all builds.
- **`failed_builds_30d`**: Count where `result` is `failed`.
- **`pipeline_failure_rate_30d`**: `failed / total * 100`, rounded to 1 decimal.

### Step 4: Security Posture (AdvSec Alerts)

Call `get_alerts` to get active security alerts:

```
get_alerts(
  projectName: "<project_name>",
  repositoryName: "<repository_name>",
  states: ["Active"]
)
```

From the results:
- **`active_security_alerts`**: Total count.
- **`security_alert_breakdown`**: Group by alert type (dependency, code,
  secret scanning).

If AdvSec is not enabled for this project/repo, the call may return empty
or an error — set to `null` and note "AdvSec not enabled."

### Step 5: Change Velocity (Commits)

Call `search_commits` to get recent commit activity:

```
search_commits(
  projectName: "<project_name>",
  repositoryName: "<repository_name>",
  fromDate: "<ISO 8601 — 30 days ago>",
  toDate: "<ISO 8601 — now>"
)
```

**`commit_count_30d`** = count of returned commits.

### Step 6: PR Review Quality

Call `list_pull_requests_by_repo_or_project` to get open PRs:

```
list_pull_requests_by_repo_or_project(
  projectName: "<project_name>",
  repositoryName: "<repository_name>",
  status: "active"
)
```

From the results:
- **`active_pr_count`**: Total count of open PRs.
- **`pr_without_reviewers`**: Count of PRs where `reviewers` is empty or
  has no required reviewers.

## Error Handling

- If the repo is not found, return all evidence as `null`. This is expected
  for services whose repos are not in the connected ADO org.
- If AdvSec alerts return an error, set security evidence to `null` and
  continue. AdvSec may not be enabled for all repos.
- If any individual step fails, set that evidence key to `null` and
  continue with remaining steps.
- All time-based parameters use ISO 8601 UTC format.

## Example Output

```json
{
  "ado_project": "Payments",
  "ado_repository": "payments-api",
  "pipeline_failure_rate_30d": 12.5,
  "failed_builds_30d": 3,
  "total_builds_30d": 24,
  "active_security_alerts": 7,
  "security_alert_breakdown": {
    "dependency": 5,
    "code": 1,
    "secret": 1
  },
  "commit_count_30d": 42,
  "active_pr_count": 5,
  "pr_without_reviewers": 1
}
```
