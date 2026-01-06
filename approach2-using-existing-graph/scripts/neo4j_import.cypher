// Import graph from CSVs mounted at /import
// Run via: cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /import/neo4j_import.cypher

// --- Constraints ---
CREATE CONSTRAINT service_serviceId IF NOT EXISTS
FOR (s:Service) REQUIRE s.serviceId IS UNIQUE;

CREATE CONSTRAINT resource_resourceId IF NOT EXISTS
FOR (r:AzureResource) REQUIRE r.resourceId IS UNIQUE;

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
LOAD CSV WITH HEADERS FROM 'file:///data/azure_service_tree.csv' AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
SET s.name = row.name,
    s.icmTenant = row.icmTenant,
    s.icmTeamsRaw = row.icmTeams;

LOAD CSV WITH HEADERS FROM 'file:///data/azure_service_tree.csv' AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, [x IN split(coalesce(row.subscriptions,''), ';') | trim(x)] AS subs
UNWIND [x IN subs WHERE x <> ''] AS subId
MERGE (sub:Subscription {subscriptionId: subId})
MERGE (s)-[:USES_SUBSCRIPTION]->(sub);

LOAD CSV WITH HEADERS FROM 'file:///data/azure_service_tree.csv' AS row
WITH row
WHERE row.serviceId IS NOT NULL AND trim(row.serviceId) <> ''
MERGE (s:Service {serviceId: trim(row.serviceId)})
WITH s, [u IN split(coalesce(row.sourceCodeLocations,''), '|') | trim(u)] AS urls
UNWIND [u IN urls WHERE u <> ''] AS uri
MERGE (r:Repo {uri: uri})
MERGE (s)-[:HAS_REPO]->(r);

// Optional enrichment from repo.csv (best-effort by exact URI match)
LOAD CSV WITH HEADERS FROM 'file:///data/repo.csv' AS row
WITH row
WHERE row.sourceControlURI IS NOT NULL AND trim(row.sourceControlURI) <> ''
MERGE (r:Repo {uri: trim(row.sourceControlURI)})
SET r.sourceControlType = row.sourceControlType,
    r.serviceArtifacts = row.serviceArtifacts,
    r.applicationCode = row.applicationCode,
    r.iacConfiguration = row.iacConfiguration;

// --- Azure resources, subscription/RG hierarchy, and Service ownership via tags ---
LOAD CSV WITH HEADERS FROM 'file:///data/azure_resources.csv' AS row
WITH row
WHERE row.resourceId IS NOT NULL AND trim(row.resourceId) <> ''
WITH row,
     [p IN split(coalesce(row.tags,''), ';')
      WHERE trim(p) STARTS WITH 'serviceId:'] AS svcParts
WITH row,
     CASE
       WHEN size(svcParts) > 0 THEN trim(split(trim(svcParts[0]), ':')[1])
       ELSE NULL
     END AS serviceId

MERGE (res:AzureResource {resourceId: trim(row.resourceId)})
SET res.displayName = row.displayName,
    res.resourceType = row.resourceType,
    res.location = row.location,
            res.tagsRaw = row.tags

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
LOAD CSV WITH HEADERS FROM 'file:///data/ev2_deployment.csv' AS row
WITH row
WHERE row.rolloutId IS NOT NULL AND trim(row.rolloutId) <> ''
MERGE (d:Deployment {rolloutId: trim(row.rolloutId)})
SET d.serviceGroup = row.serviceGroup,
    d.rolloutInfra = row.rolloutInfra,
    d.artifactVersion = row.artifactVersion;

LOAD CSV WITH HEADERS FROM 'file:///data/ev2_deployment.csv' AS row
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

// --- Incidents (outage.csv base) ---
LOAD CSV WITH HEADERS FROM 'file:///data/outage.csv' AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
SET i.title = row.title,
    i.createdDate = row.createdDate,
    i.severity = row.severity,
    i.changeRelated = row.changeRelated,
    i.rootCause = row.rootCause,
    i.rootCauseSubcategory = row.rootCauseSubcategory,
    i.serviceName = row.serviceName,
    i.serviceIdRaw = row.serviceId,
    i.subscriptionsImpactedRaw = row.subscriptionsImpacted;

LOAD CSV WITH HEADERS FROM 'file:///data/outage.csv' AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, trim(row.serviceId) AS sid
WHERE sid IS NOT NULL AND sid <> ''
MERGE (s:Service {serviceId: sid})
MERGE (i)-[:AFFECTS_SERVICE]->(s);

// Enrichment + team ownership (icm.csv)
// Note: icm.csv has a malformed trailing line in this dataset; filter on ICM-* incident IDs.
LOAD CSV WITH HEADERS FROM 'file:///data/icm.csv' AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
SET i.causeDescription = row.causeDescription,
    i.ownerAlias = row.ownerAlias,
    i.infrastructureInvolved = row.infrastructureInvolved;

LOAD CSV WITH HEADERS FROM 'file:///data/icm.csv' AS row
WITH row
WHERE row.incidentId IS NOT NULL AND trim(row.incidentId) STARTS WITH 'ICM-'
MERGE (i:Incident {incidentId: trim(row.incidentId)})
WITH i, trim(row.owningTeam) AS teamName
WHERE teamName IS NOT NULL AND teamName <> ''
MERGE (t:Team {name: teamName})
MERGE (i)-[:OWNED_BY_TEAM]->(t);

// --- Templates (best-effort links to RG) ---
// Assumes template.csv is valid CSV (Neo4j LOAD CSV is strict about quoting).
LOAD CSV WITH HEADERS FROM 'file:///data/template.csv' AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
SET t.resourceType = row.resourceType,
    t.propertiesRaw = row.properties,
    t.resourceGroup = row.resourceGroup;

LOAD CSV WITH HEADERS FROM 'file:///data/template.csv' AS row
WITH row
WHERE row.templateName IS NOT NULL AND trim(row.templateName) <> '' AND row.resourceGroup IS NOT NULL AND trim(row.resourceGroup) <> ''
MERGE (t:Template {templateName: trim(row.templateName), templateVersion: trim(coalesce(row.templateVersion,''))})
WITH t, trim(row.resourceGroup) AS rgName
MERGE (rg:ResourceGroup {key: 'UNKNOWN|' + rgName})
SET rg.name = rgName
MERGE (t)-[:TARGETS_RESOURCE_GROUP]->(rg);
