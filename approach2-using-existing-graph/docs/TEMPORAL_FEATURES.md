# Temporal Features in Risk Scoring

This document explains how temporal dimensions enhance risk assessment in the Neo4j graph hierarchy.

## Overview

The graph hierarchy includes three categories of temporal data:

1. **Sequential Ordering**: Timeline events and mitigation steps have explicit order properties
2. **Duration Tracking**: Deployment stages track start/end times for performance analysis
3. **Change Frequency**: Services, resource groups, and resources track deployment frequency

These temporal dimensions enable more sophisticated risk scoring by providing:
- Historical context for incident response patterns
- Deployment velocity metrics for change risk assessment
- Time-based correlation between changes and incidents

## 1. Timeline Event Ordering

**Purpose**: Establish sequential order of events during incident response.

**Implementation**: `TimelineEvent` nodes have an `order` property (integer).

**Schema**:
```cypher
(Incident)-[:HAS_TIMELINE_EVENT]->(TimelineEvent)

TimelineEvent properties:
- incidentId: string
- event: string (e.g., "detected", "mitigated", "resolved")
- timestamp: datetime
- order: integer (1, 2, 3, ...)
- source: string
- action: string
```

**Example Query**:
```cypher
// Get incident timeline in sequential order
MATCH (i:Incident {incidentId: 'ICM-2025-1001'})-[:HAS_TIMELINE_EVENT]->(te:TimelineEvent)
RETURN te.order, te.event, te.timestamp, te.action
ORDER BY te.order;
```

**Risk Scoring Impact**:
- **MTTR Calculation**: Time between "detected" (order=1) and "resolved" (last order)
- **Response Pattern Analysis**: Identify slow mitigation steps across similar incidents
- **Escalation Detection**: Multiple mitigation attempts before resolution indicates complexity

**Example Risk Factor**:
```
IF MTTR > 2 hours AND incident.severity = "High"
THEN risk_factor += 15 points
```

## 2. Deployment Stage Duration

**Purpose**: Track deployment stage performance and identify slow rollouts.

**Implementation**: `DeploymentStage` nodes have `startTime` and `endTime` properties.

**Schema**:
```cypher
(Deployment)-[:HAS_STAGE]->(DeploymentStage)

DeploymentStage properties:
- deploymentId: string
- name: string (e.g., "canary", "pilot", "production")
- order: integer (1, 2, 3, ...)
- startTime: datetime
- endTime: datetime
- status: string
- percentage: integer
- regions: array
- healthChecks: array
```

**Example Query**:
```cypher
// Calculate stage durations for a deployment
MATCH (d:Deployment {rolloutId: 'RL-2025-101'})-[:HAS_STAGE]->(ds:DeploymentStage)
WITH ds, 
     duration.between(datetime(ds.startTime), datetime(ds.endTime)).minutes AS durationMinutes
RETURN ds.name, ds.order, ds.startTime, ds.endTime, durationMinutes
ORDER BY ds.order;
```

**Risk Scoring Impact**:
- **Deployment Velocity**: Slow deployments indicate higher complexity/risk
- **Stage Failure Correlation**: Failed stages followed by quick retry indicate instability
- **Canary Safety Window**: Insufficient canary duration increases production risk

**Example Risk Factor**:
```
IF canary_duration < 15 minutes AND deployment_target = "prod"
THEN risk_factor += 10 points  // Insufficient bake time

IF deployment_duration > 4 hours
THEN risk_factor += 5 points   // Unusually slow rollout
```

## 3. Change Frequency Metadata

**Purpose**: Track how often services, resource groups, and resources are modified.

**Implementation**: Computed properties added via `add_change_frequency.cypher` script.

**Schema**:
```cypher
Service properties:
- deploymentCount: integer (number of deployments targeting this service)
- lastUpdated: datetime (when frequency was last calculated)

ResourceGroup properties:
- deploymentCount: integer (number of deployments targeting this RG)
- lastUpdated: datetime

AzureResource properties:
- changeFrequency: integer (number of deployments affecting this resource)
- lastUpdated: datetime
```

**Calculation Script** (`scripts/add_change_frequency.cypher`):
```cypher
// Calculate deployment frequency for Services
MATCH (s:Service)<-[:FOR_SERVICE]-(d:Deployment)
WITH s, count(d) AS deploymentCount
SET s.deploymentCount = deploymentCount,
    s.lastUpdated = datetime();

// Calculate change frequency for AzureResources (via their ResourceGroup)
MATCH (r:AzureResource)-[:IN_RESOURCE_GROUP]->(rg:ResourceGroup)<-[:TARGETS_RESOURCE_GROUP]-(d:Deployment)
WITH r, count(DISTINCT d) AS deploymentCount
SET r.changeFrequency = deploymentCount,
    r.lastUpdated = datetime();
```

**Example Queries**:
```cypher
// Find high-churn services (frequent deployments)
MATCH (s:Service)
WHERE s.deploymentCount IS NOT NULL
RETURN s.serviceId, s.name, s.deploymentCount
ORDER BY s.deploymentCount DESC
LIMIT 10;

// Find resources affected by multiple deployments
MATCH (r:AzureResource)
WHERE r.changeFrequency > 2
RETURN r.resourceName, r.changeFrequency, r.displayName;
```

**Risk Scoring Impact**:
- **Change Fatigue**: High deployment frequency increases operator error risk
- **Stability Correlation**: Frequent changes + recent incidents = high risk
- **Blast Radius Amplification**: High-churn services have larger blast radius

**Example Risk Factors**:
```
IF service.deploymentCount > 10 (in last 180 days)
THEN risk_factor += 5 points  // High change frequency

IF resource.changeFrequency > 5 AND recent_incidents > 0
THEN risk_factor += 10 points  // Unstable high-churn resource

IF deploymentCount = 0 AND service_age > 1 year
THEN risk_factor += 3 points   // Stale service (no recent changes)
```

## 4. Updating Change Frequency

The change frequency script should be run periodically to keep metadata current.

**Manual Execution**:
```bash
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  -f /import/add_change_frequency.cypher
```

**Automated Execution** (recommended):
- Add to cron job or scheduled task
- Run after each deployment import
- Typical frequency: daily or after batch imports

**Verification**:
```cypher
// Check when frequencies were last updated
MATCH (s:Service)
WHERE s.lastUpdated IS NOT NULL
RETURN s.serviceId, s.deploymentCount, s.lastUpdated
ORDER BY s.lastUpdated DESC
LIMIT 5;
```

## 5. Combined Temporal Risk Analysis

Temporal data from all three categories can be combined for sophisticated risk assessment.

**Example: High-Risk Change Detection**:
```cypher
// Find services with high change frequency AND recent incidents with slow MTTR
MATCH (s:Service)<-[:AFFECTS_SERVICE]-(i:Incident)-[:HAS_TIMELINE_EVENT]->(te:TimelineEvent)
WHERE s.deploymentCount > 5  // High change frequency
  AND i.createdDate > date() - duration({days: 90})  // Recent incident
  AND te.event = "resolved"
WITH s, i, te.order AS resolveOrder
MATCH (i)-[:HAS_TIMELINE_EVENT]->(te_detect:TimelineEvent {order: 1})
WITH s, i, duration.between(datetime(te_detect.timestamp), datetime(te.timestamp)).hours AS mttr
WHERE mttr > 2  // Slow resolution
RETURN s.serviceId, s.name, s.deploymentCount, count(i) AS recentIncidents, avg(mttr) AS avgMTTR
ORDER BY recentIncidents DESC, avgMTTR DESC;
```

**Risk Score Calculation**:
```
Base Risk: 20 points (production environment)

Temporal Factors:
+ 10 points: High deployment frequency (>5 in 90 days)
+ 15 points: Slow average MTTR (>2 hours)
+ 10 points: Recent incident within 30 days
+ 5 points: Insufficient canary duration (<15 min)
---
Total: 60 points (MEDIUM risk)

Verdict: PROCEED_WITH_CAUTION
Recommendation: "Schedule change during off-peak hours due to recent incident history"
```

## 6. Future Enhancements

Potential temporal features for future implementation:

1. **Time-to-Detect (TTD)**: Time between change deployment and incident detection
2. **Change Correlation Score**: Statistical correlation between deployments and incidents
3. **Deployment Pattern Analysis**: Detect risky patterns (e.g., Friday deployments with higher incident rates)
4. **Seasonal Risk Modeling**: Adjust risk scores based on time of day/week/month
5. **Aging Resource Detection**: Flag resources that haven't been updated in a long time

## Summary

Temporal dimensions provide critical context for risk assessment:

| Feature | Property | Risk Insight |
|---------|----------|--------------|
| Timeline Order | `TimelineEvent.order` | Incident response efficiency (MTTR) |
| Stage Duration | `DeploymentStage.startTime/endTime` | Deployment velocity and stability |
| Change Frequency | `Service.deploymentCount`, `Resource.changeFrequency` | Change fatigue and stability correlation |

These features enable the risk scoring engine to move beyond static graph topology to incorporate historical behavior patterns, making risk assessments more accurate and actionable.
