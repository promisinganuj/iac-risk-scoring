// Graph Data Validation Test Suite
// Run with: cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f scripts/validate_graph.cypher
//
// This script validates data quality and consistency in the Neo4j graph.
// Returns validation results with pass/fail status for each test.

// =============================================================================
// TEST 1: Orphan Detection - Incidents referencing non-existent resources
// =============================================================================
CALL {
    MATCH (i:Incident)-[:AFFECTS_RESOURCE]->(r:AzureResource)
    WHERE r.resourceType IS NULL OR r.resourceName IS NULL
    RETURN count(r) AS orphanCount
}
WITH orphanCount
RETURN 
    'Orphan Detection' AS test,
    CASE WHEN orphanCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    orphanCount AS issueCount,
    'Incidents should only reference existing resources' AS description;

// =============================================================================
// TEST 2: Service-Resource Consistency
// =============================================================================
CALL {
    MATCH (i:Incident)-[:AFFECTS_SERVICE]->(s:Service)
    MATCH (i)-[:AFFECTS_RESOURCE]->(r:AzureResource)
    OPTIONAL MATCH (r)<-[:OWNS_RESOURCE]-(owner:Service)
    WHERE owner.serviceId <> s.serviceId OR owner IS NULL
    RETURN count(DISTINCT i) AS inconsistentCount
}
WITH inconsistentCount
RETURN 
    'Service-Resource Consistency' AS test,
    CASE WHEN inconsistentCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    inconsistentCount AS issueCount,
    'Incident AFFECTS_SERVICE should match resource OWNS_RESOURCE' AS description;

// =============================================================================
// TEST 3: Deployment Stage Ordering
// =============================================================================
CALL {
    MATCH (d:Deployment)-[:HAS_STAGE]->(st:DeploymentStage)
    WHERE st.order IS NULL OR st.order < 1
    RETURN count(st) AS invalidOrderCount
}
WITH invalidOrderCount
RETURN 
    'Deployment Stage Ordering' AS test,
    CASE WHEN invalidOrderCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    invalidOrderCount AS issueCount,
    'All deployment stages should have valid order property (>= 1)' AS description;

// =============================================================================
// TEST 4: Mitigation Step Ordering
// =============================================================================
CALL {
    MATCH (i:Incident)-[:HAS_MITIGATION_STEP]->(ms:MitigationStep)
    WHERE ms.step IS NULL OR ms.step < 1
    RETURN count(ms) AS invalidStepCount
}
WITH invalidStepCount
RETURN 
    'Mitigation Step Ordering' AS test,
    CASE WHEN invalidStepCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    invalidStepCount AS issueCount,
    'All mitigation steps should have valid step property (>= 1)' AS description;

// =============================================================================
// TEST 5: Artifact Circular Dependencies
// =============================================================================
CALL {
    MATCH path = (a:Artifact)-[:DEPENDS_ON*2..10]->(a)
    RETURN count(DISTINCT a) AS cycleCount
}
WITH cycleCount
RETURN 
    'Artifact Circular Dependencies' AS test,
    CASE WHEN cycleCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    cycleCount AS issueCount,
    'Artifacts should not have circular dependencies' AS description;

// =============================================================================
// TEST 6: Template Circular Dependencies
// =============================================================================
CALL {
    MATCH path = (t:Template)-[:DEPENDS_ON_TEMPLATE*2..10]->(t)
    RETURN count(DISTINCT t) AS cycleCount
}
WITH cycleCount
RETURN 
    'Template Circular Dependencies' AS test,
    CASE WHEN cycleCount = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    cycleCount AS issueCount,
    'Templates should not have circular dependencies' AS description;

// =============================================================================
// TEST 7: Service Resource Coverage
// =============================================================================
CALL {
    MATCH (s:Service)
    WHERE NOT (s)-[:OWNS_RESOURCE]->()
    RETURN count(s) AS servicesWithoutResources
}
WITH servicesWithoutResources
RETURN 
    'Service Resource Coverage' AS test,
    CASE WHEN servicesWithoutResources = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    servicesWithoutResources AS issueCount,
    'All services should own at least one resource' AS description;

// =============================================================================
// TEST 8: Deployment Template Linkage
// =============================================================================
CALL {
    MATCH (d:Deployment)
    WHERE NOT (d)-[:USES_TEMPLATE]->()
    RETURN count(d) AS deploymentsWithoutTemplate
}
WITH deploymentsWithoutTemplate
RETURN 
    'Deployment Template Linkage' AS test,
    CASE WHEN deploymentsWithoutTemplate = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    deploymentsWithoutTemplate AS issueCount,
    'All deployments should link to a template' AS description;

// =============================================================================
// TEST 9: Resource Group Hierarchy
// =============================================================================
CALL {
    MATCH (rg:ResourceGroup)
    WHERE NOT (rg)-[:IN_SUBSCRIPTION]->()
    RETURN count(rg) AS orphanedRGs
}
WITH orphanedRGs
RETURN 
    'Resource Group Hierarchy' AS test,
    CASE WHEN orphanedRGs = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    orphanedRGs AS issueCount,
    'All resource groups should belong to a subscription' AS description;

// =============================================================================
// TEST 10: Incident Coverage
// =============================================================================
CALL {
    MATCH (i:Incident)
    WHERE NOT (i)-[:HAS_MITIGATION_STEP]->() AND NOT (i)-[:HAS_TIMELINE_EVENT]->()
    RETURN count(i) AS incidentsWithoutDetails
}
WITH incidentsWithoutDetails
RETURN 
    'Incident Coverage' AS test,
    CASE WHEN incidentsWithoutDetails = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    incidentsWithoutDetails AS issueCount,
    'All incidents should have mitigation steps or timeline events' AS description;

// =============================================================================
// SUMMARY: Count Passes and Failures
// =============================================================================
CALL {
    // Rerun all tests to collect results
    MATCH (i:Incident)-[:AFFECTS_RESOURCE]->(r:AzureResource)
    WHERE r.resourceType IS NULL OR r.resourceName IS NULL
    WITH count(r) AS orphanCount
    WITH CASE WHEN orphanCount = 0 THEN 1 ELSE 0 END AS t1
    
    MATCH (i:Incident)-[:AFFECTS_SERVICE]->(s:Service)
    MATCH (i)-[:AFFECTS_RESOURCE]->(r:AzureResource)
    OPTIONAL MATCH (r)<-[:OWNS_RESOURCE]-(owner:Service)
    WHERE owner.serviceId <> s.serviceId OR owner IS NULL
    WITH t1, count(DISTINCT i) AS inconsistentCount
    WITH t1, CASE WHEN inconsistentCount = 0 THEN 1 ELSE 0 END AS t2
    
    MATCH (d:Deployment)-[:HAS_STAGE]->(st:DeploymentStage)
    WHERE st.order IS NULL OR st.order < 1
    WITH t1, t2, count(st) AS invalidOrderCount
    WITH t1, t2, CASE WHEN invalidOrderCount = 0 THEN 1 ELSE 0 END AS t3
    
    MATCH (i:Incident)-[:HAS_MITIGATION_STEP]->(ms:MitigationStep)
    WHERE ms.step IS NULL OR ms.step < 1
    WITH t1, t2, t3, count(ms) AS invalidStepCount
    WITH t1, t2, t3, CASE WHEN invalidStepCount = 0 THEN 1 ELSE 0 END AS t4
    
    MATCH path = (a:Artifact)-[:DEPENDS_ON*2..10]->(a)
    WITH t1, t2, t3, t4, count(DISTINCT a) AS cycleCount
    WITH t1, t2, t3, t4, CASE WHEN cycleCount = 0 THEN 1 ELSE 0 END AS t5
    
    MATCH path = (t:Template)-[:DEPENDS_ON_TEMPLATE*2..10]->(t)
    WITH t1, t2, t3, t4, t5, count(DISTINCT t) AS cycleCount
    WITH t1, t2, t3, t4, t5, CASE WHEN cycleCount = 0 THEN 1 ELSE 0 END AS t6
    
    MATCH (s:Service)
    WHERE NOT (s)-[:OWNS_RESOURCE]->()
    WITH t1, t2, t3, t4, t5, t6, count(s) AS servicesWithoutResources
    WITH t1, t2, t3, t4, t5, t6, CASE WHEN servicesWithoutResources = 0 THEN 1 ELSE 0 END AS t7
    
    MATCH (d:Deployment)
    WHERE NOT (d)-[:USES_TEMPLATE]->()
    WITH t1, t2, t3, t4, t5, t6, t7, count(d) AS deploymentsWithoutTemplate
    WITH t1, t2, t3, t4, t5, t6, t7, CASE WHEN deploymentsWithoutTemplate = 0 THEN 1 ELSE 0 END AS t8
    
    MATCH (rg:ResourceGroup)
    WHERE NOT (rg)-[:IN_SUBSCRIPTION]->()
    WITH t1, t2, t3, t4, t5, t6, t7, t8, count(rg) AS orphanedRGs
    WITH t1, t2, t3, t4, t5, t6, t7, t8, CASE WHEN orphanedRGs = 0 THEN 1 ELSE 0 END AS t9
    
    MATCH (i:Incident)
    WHERE NOT (i)-[:HAS_MITIGATION_STEP]->() AND NOT (i)-[:HAS_TIMELINE_EVENT]->()
    WITH t1, t2, t3, t4, t5, t6, t7, t8, t9, count(i) AS incidentsWithoutDetails
    WITH t1, t2, t3, t4, t5, t6, t7, t8, t9, CASE WHEN incidentsWithoutDetails = 0 THEN 1 ELSE 0 END AS t10
    
    RETURN t1 + t2 + t3 + t4 + t5 + t6 + t7 + t8 + t9 + t10 AS passed
}
WITH passed, 10 AS total
RETURN 
    '=== VALIDATION SUMMARY ===' AS test,
    CASE WHEN passed = total THEN 'PASS' ELSE 'FAIL' END AS status,
    passed AS passed,
    total AS total,
    CASE WHEN passed = total THEN 'All validations passed!' ELSE 'Some validations failed - check results above' END AS description;
