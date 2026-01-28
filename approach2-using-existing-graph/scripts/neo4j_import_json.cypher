// Import graph from JSON files mounted at /import
// Run via: cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /import/neo4j_import_json.cypher

// --- Constraints ---
CREATE CONSTRAINT service_serviceId IF NOT EXISTS
FOR (s:Service) REQUIRE s.serviceId IS UNIQUE;

CREATE CONSTRAINT resource_resourceName IF NOT EXISTS
FOR (r:AzureResource) REQUIRE r.resourceName IS UNIQUE;

CREATE CONSTRAINT repo_uri IF NOT EXISTS
FOR (r:Repo) REQUIRE r.uri IS UNIQUE;

CREATE CONSTRAINT incident_incidentId IF NOT EXISTS
FOR (i:Incident) REQUIRE i.incidentId IS UNIQUE;

CREATE CONSTRAINT deployment_rolloutId IF NOT EXISTS
FOR (d:Deployment) REQUIRE d.rolloutId IS UNIQUE;

CREATE CONSTRAINT subscription_id IF NOT EXISTS
FOR (s:Subscription) REQUIRE s.subscriptionId IS UNIQUE;

CREATE CONSTRAINT rg_key IF NOT EXISTS
FOR (g:ResourceGroup) REQUIRE g.key IS UNIQUE;

CREATE CONSTRAINT team_name IF NOT EXISTS
FOR (t:Team) REQUIRE t.name IS UNIQUE;

CREATE CONSTRAINT template_compound IF NOT EXISTS
FOR (t:Template) REQUIRE (t.templateName, t.templateVersion) IS UNIQUE;

// --- Services, subscriptions, repos with hierarchies ---
CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
SET s.name = row.name,
    s.icmTenant = row.icmTenant;

// Process nested subscriptions (array of objects)
CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, row.subscriptions AS subs
UNWIND subs AS subObj
WITH s, subObj.subscriptionId AS subId, subObj.purpose AS purpose, subObj.accessLevel AS accessLevel
WHERE subId IS NOT NULL AND trim(subId) <> ''
MERGE (sub:Subscription {subscriptionId: trim(subId)})
SET sub.purpose = purpose,
    sub.accessLevel = accessLevel
MERGE (s)-[:USES_SUBSCRIPTION]->(sub);

// Process nested sourceCodeLocations (array of objects)
CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, row.sourceCodeLocations AS locations
UNWIND locations AS loc
WITH s, loc.uri AS uri, loc.type AS repoType, loc.primary AS isPrimary, loc.branch AS branch
WHERE uri IS NOT NULL AND trim(uri) <> ''
MERGE (r:Repo {uri: trim(uri)})
SET r.type = repoType,
    r.primary = isPrimary,
    r.branch = branch
MERGE (s)-[:HAS_REPO]->(r);

// Process nested icmTeams (array of objects)
CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, row.icmTeams AS teams
UNWIND teams AS team
WITH s, team.teamName AS teamName, team.role AS teamRole, team.escalationLevel AS escalationLevel
WHERE teamName IS NOT NULL AND trim(teamName) <> ''
MERGE (t:Team {name: trim(teamName)})
SET t.role = teamRole,
    t.escalationLevel = escalationLevel
MERGE (s)-[:SUPPORTED_BY_TEAM]->(t);

// Enrichment from repo.json with nested artifacts and structured metadata
CALL apoc.load.json('file:///data/repo.json') YIELD value AS row
WITH row
WHERE row.sourceControlURI IS NOT NULL AND trim(row.sourceControlURI) <> ''
MERGE (r:Repo {uri: trim(row.sourceControlURI)})
SET r.sourceControlType = row.sourceControlType,
    r.applicationLanguage = row.applicationCode.language,
    r.applicationFramework = row.applicationCode.framework,
    r.applicationVersion = row.applicationCode.version,
    r.applicationRuntime = row.applicationCode.runtime,
    r.iacTool = row.iacConfiguration.tool,
    r.iacTarget = row.iacConfiguration.target;

// Process nested serviceArtifacts (array of objects with dependencies)
CALL apoc.load.json('file:///data/repo.json') YIELD value AS row
WITH row
WHERE row.sourceControlURI IS NOT NULL AND trim(row.sourceControlURI) <> ''
MERGE (r:Repo {uri: trim(row.sourceControlURI)})
WITH r, row.serviceArtifacts AS artifacts
UNWIND artifacts AS artifact
WITH r, artifact.name AS artifactName, artifact.type AS artifactType, artifact.buildConfig AS buildConfig, artifact.dependencies AS deps
WHERE artifactName IS NOT NULL
MERGE (a:Artifact {name: artifactName, repoUri: r.uri})
SET a.type = artifactType,
    a.dockerfilePath = buildConfig.dockerfile,
    a.buildContext = buildConfig.context,
    a.dependencies = deps
MERGE (r)-[:PRODUCES_ARTIFACT]->(a);

// Process artifact dependencies (nested array within artifact)
CALL apoc.load.json('file:///data/repo.json') YIELD value AS row
WITH row
WHERE row.sourceControlURI IS NOT NULL
MERGE (r:Repo {uri: trim(row.sourceControlURI)})
WITH r, row.serviceArtifacts AS artifacts
UNWIND artifacts AS artifact
WITH r, artifact.name AS artifactName, artifact.dependencies AS deps
WHERE artifactName IS NOT NULL AND deps IS NOT NULL AND size(deps) > 0
MERGE (a:Artifact {name: artifactName, repoUri: r.uri})
WITH a, deps
UNWIND deps AS depName
WITH a, depName
WHERE depName IS NOT NULL
MERGE (dep:Artifact {name: depName, repoUri: a.repoUri})
MERGE (a)-[:DEPENDS_ON]->(dep);

// --- Azure resources, subscription/RG hierarchy, and Service ownership via tags ---
CALL apoc.load.json('file:///data/azure_resources.json') YIELD value AS row
WITH row
WHERE row.resourceName IS NOT NULL AND trim(row.resourceName) <> ''
WITH row, row.tags.serviceId AS serviceId

MERGE (res:AzureResource {resourceName: trim(row.resourceName)})
SET res.displayName = row.displayName,
    res.resourceType = row.resourceType,
    res.location = row.location,
    res.tag_owner = row.tags.owner,
    res.tag_env = row.tags.env,
    res.tag_serviceId = row.tags.serviceId

WITH row, serviceId, res
MERGE (sub:Subscription {subscriptionId: trim(row.subscriptionId)})
MERGE (rg:ResourceGroup {key: trim(row.subscriptionId) + '|' + trim(row.resourceGroup)})
SET rg.name = trim(row.resourceGroup),
    rg.subscriptionId = trim(row.subscriptionId)
MERGE (rg)-[:IN_SUBSCRIPTION]->(sub)
MERGE (res)-[:IN_RESOURCE_GROUP]->(rg)
MERGE (res)-[:IN_SUBSCRIPTION]->(sub)

WITH res, serviceId
WHERE serviceId IS NOT NULL AND serviceId <> ''
MERGE (s:Service {serviceId: serviceId})
MERGE (s)-[:OWNS_RESOURCE]->(res);

// --- Deployments with nested stages and rollout plan ---
CALL apoc.load.json('file:///data/ev2_deployment.json') YIELD value AS row
WITH row
WHERE row.rolloutId IS NOT NULL AND trim(row.rolloutId) <> ''
MERGE (d:Deployment {rolloutId: trim(row.rolloutId)})
SET d.serviceGroup = row.serviceGroup,
    d.rolloutInfra = row.rolloutInfra,
    d.artifactVersion = row.artifactVersion,
    d.overallStatus = row.status.overallStatus,
    d.healthScore = row.status.healthScore,
    d.rollbackStrategy = row.rolloutPlan.rollbackStrategy,
    d.approvalRequired = row.rolloutPlan.approvalRequired;

CALL apoc.load.json('file:///data/ev2_deployment.json') YIELD value AS row
WITH row
WHERE row.rolloutId IS NOT NULL AND trim(row.rolloutId) <> ''
MERGE (d:Deployment {rolloutId: trim(row.rolloutId)})
WITH d, row
MERGE (s:Service {serviceId: trim(row.serviceId)})
MERGE (d)-[:FOR_SERVICE]->(s)
WITH d, row
MERGE (sub:Subscription {subscriptionId: trim(row.subscriptionId)})
MERGE (rg:ResourceGroup {key: trim(row.subscriptionId) + '|' + trim(row.resourceGroup)})
SET rg.name = trim(row.resourceGroup),
    rg.subscriptionId = trim(row.subscriptionId)
MERGE (d)-[:TARGETS_RESOURCE_GROUP]->(rg)
MERGE (rg)-[:IN_SUBSCRIPTION]->(sub);

// Process nested deployment stages
CALL apoc.load.json('file:///data/ev2_deployment.json') YIELD value AS row
WITH row
WHERE row.rolloutId IS NOT NULL AND row.stages IS NOT NULL
MERGE (d:Deployment {rolloutId: trim(row.rolloutId)})
WITH d, row.stages AS stages
UNWIND stages AS stage
WITH d, stage
WHERE stage.name IS NOT NULL
MERGE (st:DeploymentStage {deploymentId: d.rolloutId, name: stage.name})
SET st.order = stage.order,
    st.percentage = stage.percentage,
    st.status = stage.status,
    st.startTime = stage.startTime,
    st.endTime = stage.endTime,
    st.regions = stage.regions,
    st.healthChecks = stage.healthChecks
MERGE (d)-[:HAS_STAGE]->(st);

// --- Incidents (outage.json base) with nested hierarchies ---
CALL apoc.load.json('file:///data/outage.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
SET i.title = row.title,
    i.createdDate = row.createdDate,
    i.severity = row.severity,
    i.changeRelated = row.changeRelated,
    i.serviceName = row.serviceName,
    i.rootCauseCategory = row.rootCause.category,
    i.rootCauseSubcategory = row.rootCause.subcategory,
    i.rootCauseDescription = row.rootCause.description,
    i.triggeringChange = row.rootCause.triggeringChange
WITH i, trim(row.serviceId) AS sid
WHERE sid IS NOT NULL AND sid <> ''
MERGE (s:Service {serviceId: sid})
MERGE (i)-[:AFFECTS_SERVICE]->(s);

// Process nested subscriptionsImpacted with user impact details
CALL apoc.load.json('file:///data/outage.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, row.subscriptionsImpacted AS subsImpacted
UNWIND subsImpacted AS subImpact
WITH i, subImpact
WHERE subImpact.subscriptionId IS NOT NULL
MERGE (sub:Subscription {subscriptionId: trim(subImpact.subscriptionId)})
MERGE (i)-[impact:IMPACTS_SUBSCRIPTION]->(sub)
SET impact.impactLevel = subImpact.impactLevel,
    impact.usersAffected = subImpact.userImpact.usersAffected,
    impact.transactionsFailed = subImpact.userImpact.transactionsFailed,
    impact.duration = subImpact.userImpact.duration;

// Process nested timeline events
CALL apoc.load.json('file:///data/outage.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND row.timeline IS NOT NULL
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, row.timeline AS timeline
UNWIND timeline AS event
WITH i, event
WHERE event.event IS NOT NULL
MERGE (te:TimelineEvent {incidentId: i.incidentId, event: event.event, timestamp: event.timestamp})
SET te.source = event.source,
    te.action = event.action
MERGE (i)-[:HAS_TIMELINE_EVENT]->(te);

// Enrichment + team ownership (icm.json) with nested hierarchies
CALL apoc.load.json('file:///data/icm.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
SET i.causeDescription = row.causeDescription,
    i.ownerAlias = row.ownerAlias,
    i.infrastructureInvolved = row.infrastructureInvolved;

CALL apoc.load.json('file:///data/icm.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, trim(row.owningTeam) AS teamName
WHERE teamName IS NOT NULL AND teamName <> ''
MERGE (t:Team {name: teamName})
MERGE (i)-[:OWNED_BY_TEAM]->(t);

// Process nested relatedIncidents
CALL apoc.load.json('file:///data/icm.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND row.relatedIncidents IS NOT NULL AND size(row.relatedIncidents) > 0
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, row.relatedIncidents AS relatedList
UNWIND relatedList AS related
WITH i, related
WHERE related.incidentId IS NOT NULL
MERGE (related_i:Incident {incidentId: trim(related.incidentId)})
MERGE (i)-[rel:RELATED_TO_INCIDENT]->(related_i)
SET rel.relationship = related.relationship,
    rel.description = related.description;

// Process nested affectedResources
CALL apoc.load.json('file:///data/icm.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND row.affectedResources IS NOT NULL
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, row.affectedResources AS resources
UNWIND resources AS resource
WITH i, resource
WHERE resource.resourceId IS NOT NULL
MERGE (r:AzureResource {resourceName: trim(resource.resourceId)})
MERGE (i)-[affects:AFFECTS_RESOURCE]->(r)
SET affects.impactType = resource.impactType,
    affects.duration = resource.duration;

// Process nested mitigationSteps
CALL apoc.load.json('file:///data/icm.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND row.mitigationSteps IS NOT NULL
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, row.mitigationSteps AS steps
UNWIND steps AS step
WITH i, step
WHERE step.step IS NOT NULL
MERGE (ms:MitigationStep {incidentId: i.incidentId, step: step.step})
SET ms.action = step.action,
    ms.timestamp = step.timestamp,
    ms.assignee = step.assignee
MERGE (i)-[:HAS_MITIGATION_STEP]->(ms);

// --- Templates with nested hierarchies ---
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
SET t.resourceType = row.resourceType,
    t.resourceGroup = row.resourceGroup,
    t.computeSku = row.properties.compute.sku,
    t.computeRuntime = row.properties.compute.runtime,
    t.computeInstances = row.properties.compute.instances,
    t.networkVnetIntegration = row.properties.network.vnetIntegration,
    t.networkPrivateEndpoint = row.properties.network.privateEndpoint,
    t.storageTier = row.properties.storage.tier,
    t.storageReplication = row.properties.storage.replication;

// Process template dependencies
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND row.dependencies IS NOT NULL
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, row.dependencies AS deps
UNWIND deps AS dep
WITH t, dep
WHERE dep.templateName IS NOT NULL
MERGE (dep_t:Template {templateName: trim(dep.templateName), templateVersion: coalesce(dep.version, '')})
MERGE (t)-[depends:DEPENDS_ON_TEMPLATE]->(dep_t)
SET depends.required = dep.required;

// Process template parameters
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND row.parameters IS NOT NULL
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, row.parameters AS params
UNWIND params AS param
WITH t, param
WHERE param.name IS NOT NULL
MERGE (p:TemplateParameter {templateName: t.templateName, parameterName: param.name})
SET p.type = param.type,
    p.default = param.default,
    p.validationRules = apoc.convert.toJson(param.validation)
MERGE (t)-[:HAS_PARAMETER]->(p);

// Process template outputs
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND row.outputs IS NOT NULL
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, row.outputs AS outputs
UNWIND outputs AS output
WITH t, output
WHERE output.name IS NOT NULL
MERGE (o:TemplateOutput {templateName: t.templateName, outputName: output.name})
SET o.type = output.type,
    o.description = output.description
MERGE (t)-[:HAS_OUTPUT]->(o);

// Link templates to resource groups (best-effort)
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> '' AND row.resourceGroup IS NOT NULL AND trim(row.resourceGroup) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, trim(row.resourceGroup) AS rgName
MERGE (rg:ResourceGroup {key: 'UNKNOWN|' + rgName})
SET rg.name = rgName
MERGE (t)-[:TARGETS_RESOURCE_GROUP]->(rg);
