// Add change frequency metadata to nodes based on deployment history
// This script computes deployment frequency for Services, ResourceGroups, and Templates

// Calculate deployment frequency for Services
MATCH (s:Service)<-[:FOR_SERVICE]-(d:Deployment)
WITH s, count(d) AS deploymentCount
SET s.deploymentCount = deploymentCount,
    s.lastUpdated = datetime();

// Calculate deployment frequency for ResourceGroups
MATCH (rg:ResourceGroup)<-[:TARGETS_RESOURCE_GROUP]-(d:Deployment)
WITH rg, count(d) AS deploymentCount
SET rg.deploymentCount = deploymentCount,
    rg.lastUpdated = datetime();

// Calculate usage frequency for Templates
MATCH (t:Template)<-[:USES_TEMPLATE]-(d:Deployment)
WITH t, count(d) AS usageCount
SET t.usageCount = usageCount,
    t.lastUpdated = datetime();

// Calculate change frequency for AzureResources (via their ResourceGroup)
MATCH (r:AzureResource)-[:IN_RESOURCE_GROUP]->(rg:ResourceGroup)<-[:TARGETS_RESOURCE_GROUP]-(d:Deployment)
WITH r, count(DISTINCT d) AS deploymentCount
SET r.changeFrequency = deploymentCount,
    r.lastUpdated = datetime();

// Add summary statistics
MATCH (s:Service)
WITH count(s) AS serviceCount, 
     avg(s.deploymentCount) AS avgDeployments,
     max(s.deploymentCount) AS maxDeployments
RETURN serviceCount, avgDeployments, maxDeployments;
