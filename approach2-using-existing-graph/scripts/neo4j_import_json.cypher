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

// --- Services, subscriptions, repos ---
CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
SET s.name = row.name,
    s.icmTenant = row.icmTenant,
    s.icmTeamsRaw = row.icmTeams;

CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, row.subscriptions AS subs
UNWIND subs AS subId
WITH s, trim(subId) AS subId
WHERE subId <> ''
MERGE (sub:Subscription {subscriptionId: subId})
MERGE (s)-[:USES_SUBSCRIPTION]->(sub);

CALL apoc.load.json('file:///data/azure_service_tree.json') YIELD value AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, row.sourceCodeLocations AS urls
UNWIND urls AS uri
WITH s, trim(uri) AS uri
WHERE uri <> ''
MERGE (r:Repo {uri: uri})
MERGE (s)-[:HAS_REPO]->(r);

// Optional enrichment from repo.json (best-effort by exact URI match)
CALL apoc.load.json('file:///data/repo.json') YIELD value AS row
WITH row
WHERE row.sourceControlURI IS NOT NULL AND trim(row.sourceControlURI) <> ''
MERGE (r:Repo {uri: trim(row.sourceControlURI)})
SET r.sourceControlType = row.sourceControlType,
    r.applicationCode = row.applicationCode,
    r.iacConfiguration = row.iacConfiguration
WITH r, row.serviceArtifacts AS artifacts
UNWIND artifacts AS artifact
WITH r, collect(artifact) AS allArtifacts
SET r.serviceArtifacts = allArtifacts;

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

// --- Deployments ---
CALL apoc.load.json('file:///data/ev2_deployment.json') YIELD value AS row
WITH row
WHERE row.rolloutId IS NOT NULL AND trim(row.rolloutId) <> ''
MERGE (d:Deployment {rolloutId: trim(row.rolloutId)})
SET d.serviceGroup = row.serviceGroup,
    d.rolloutInfra = row.rolloutInfra,
    d.artifactVersion = row.artifactVersion;

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

// --- Incidents (outage.json base) ---
CALL apoc.load.json('file:///data/outage.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
SET i.title = row.title,
    i.createdDate = row.createdDate,
    i.severity = row.severity,
    i.changeRelated = row.changeRelated,
    i.rootCause = row.rootCause,
    i.rootCauseSubcategory = row.rootCauseSubcategory,
    i.serviceName = row.serviceName
WITH i, row.serviceId AS sid, row.subscriptionsImpacted AS subsImpacted
WHERE sid IS NOT NULL AND sid <> ''
SET i.serviceIdRaw = sid
WITH i, subsImpacted
WHERE subsImpacted IS NOT NULL
SET i.subscriptionsImpactedList = subsImpacted;

CALL apoc.load.json('file:///data/outage.json') YIELD value AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, trim(row.serviceId) AS sid
WHERE sid IS NOT NULL AND sid <> ''
MERGE (s:Service {serviceId: sid})
MERGE (i)-[:AFFECTS_SERVICE]->(s);

// Enrichment + team ownership (icm.json)
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

// --- Templates (best-effort links to RG) ---
CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
SET t.resourceType = row.resourceType,
    t.prop_sku = row.properties.sku,
    t.prop_runtime = row.properties.runtime,
    t.resourceGroup = row.resourceGroup;

CALL apoc.load.json('file:///data/template.json') YIELD value AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> '' AND row.resourceGroup IS NOT NULL AND trim(row.resourceGroup) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, trim(row.resourceGroup) AS rgName
MERGE (rg:ResourceGroup {key: 'UNKNOWN|' + rgName})
SET rg.name = rgName
MERGE (t)-[:TARGETS_RESOURCE_GROUP]->(rg);
