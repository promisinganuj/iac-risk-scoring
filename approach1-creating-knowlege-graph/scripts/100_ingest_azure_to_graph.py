#!/usr/bin/env python3
import os
import sys
import time
import yaml
import re

from dotenv import load_dotenv
from json import dumps
from azure.identity import AzureCliCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.resourcegraph.models import QueryRequest
from gremlin_python.driver import client, serializer
from jsonpath_ng import parse as jsonpath_parse

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"))

subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
resource_group = os.getenv("RESOURCE_GROUP")  # optional filter
gremlin_host = os.getenv("COSMOS_GREMLIN_HOST")
gremlin_db = os.getenv("COSMOS_GREMLIN_DATABASE")
gremlin_graph = os.getenv("COSMOS_GREMLIN_GRAPH")
gremlin_key = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY")

required = [subscription_id, gremlin_host, gremlin_db, gremlin_graph, gremlin_key]
if not all(required):
    print("Missing required env vars. Ensure AZURE_SUBSCRIPTION_ID, COSMOS_GREMLIN_HOST, COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH, COSMOS_GREMLIN_PRIMARY_KEY are set.")
    sys.exit(1)

# Load relationship config
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "relationship-config.yaml")
if not os.path.exists(CONFIG_PATH):
    print(f"Missing {CONFIG_PATH} in working directory. See sample in repository.")
    sys.exit(1)

with open(CONFIG_PATH, "r") as fh:
    relationship_config = yaml.safe_load(fh)

print("Loaded relationship configuration.")

# ---------------------------
# Connect to Gremlin (Cosmos)
# ---------------------------
gremlin_endpoint = f"wss://{gremlin_host}.gremlin.cosmos.azure.com:443/"
cosmos_client = client.Client(
    gremlin_endpoint,
    "g",
    username=f"/dbs/{gremlin_db}/colls/{gremlin_graph}",
    password=gremlin_key,
    message_serializer=serializer.GraphSONSerializersV2d0(),
)

print(f"Connected to Gremlin endpoint: {gremlin_endpoint}")

# ---------------------------
# Query Azure Resource Graph
# ---------------------------
credential = AzureCliCredential()
rg_client = ResourceGraphClient(credential)
sub_client = SubscriptionClient(credential)

# Defining resource map to track resources - GLOBAL
resources_by_id = {}

def get_subscription_name(subscription_id: str) -> str:
    subscription = sub_client.subscriptions.get(subscription_id)
    return subscription.display_name or ""

def get_subscription_resource(subscription_id: str):
    """Get subscription as a resource object"""
    subscription_name = get_subscription_name(subscription_id)
    return {
        "id": f"/subscriptions/{subscription_id}",
        "name": subscription_name,
        "type": "microsoft.resources/subscriptions",
        "location": "",
        "resourceGroup": "",
        "subscriptionId": subscription_id,
        "tags": {},
        "properties": {}
    }

def get_resource_group_resource(subscription_id: str, resource_group_name: str):
    """Get resource group as a resource object"""
    return {
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}",
        "name": resource_group_name,
        "type": "microsoft.resources/resourcegroups", 
        "location": "",
        "resourceGroup": resource_group_name,
        "subscriptionId": subscription_id,
        "tags": {},
        "properties": {}
    }

def extract_nested_resources_from_hierarchy_rules(parent_resource):
    """
    Extract nested resources based on hierarchy rules configuration.
    This replaces the hardcoded VNet -> Subnet extraction with a generic approach.
    """
    hierarchy_rules = relationship_config.get("hierarchy_rules", [])
    parent_type = parent_resource.get("type", "").lower()
    parent_id = parent_resource["id"]
    
    extracted_resources = []
    
    for rule in hierarchy_rules:
        rule_parent_type = rule.get("parent", "").lower()
        rule_child_type = rule.get("child", "").lower()
        
        # Check if this parent resource matches the rule's parent type
        if rule_parent_type != parent_type:
            continue
            
        # Skip wildcard child types (these are for general parent->resource relationships)
        if rule_child_type == "*":
            continue
            
        # Extract the nested resource type and collection name from the child type
        # e.g., "microsoft.network/virtualnetworks/subnets" -> extract "subnets"
        if "/" in rule_child_type:
            type_parts = rule_child_type.split("/")
            if len(type_parts) >= 3:
                collection_name = type_parts[-1]  # e.g., "subnets", "securityrules"
                
                # Look for this collection in the parent's properties
                parent_properties = parent_resource.get("properties", {})
                nested_items = parent_properties.get(collection_name, [])
                
                if nested_items:
                    print(f"Found {len(nested_items)} {collection_name} in {parent_resource.get('name')}")
                    
                    for item in nested_items:
                        item_name = item.get("name")
                        if not item_name:
                            continue
                            
                        # Construct the nested resource ID
                        nested_resource_id = f"{parent_id}/{collection_name}/{item_name}"
                        
                        # Create the nested resource object
                        nested_resource = {
                            "id": nested_resource_id,
                            "name": item_name,
                            "type": rule_child_type,
                            "location": parent_resource.get("location", ""),
                            "resourceGroup": parent_resource.get("resourceGroup", ""),
                            "subscriptionId": parent_resource.get("subscriptionId", ""),
                            "tags": item.get("tags", {}),
                            "properties": item.get("properties", {})
                        }
                        
                        extracted_resources.append(nested_resource)
                        print(f"Extracted {rule_child_type}: {item_name} from {parent_resource.get('name')}")
    
    return extracted_resources

def get_resource_list():
    query = """
    Resources
    | where type != ''
    | extend properties = todynamic(properties)
    | project id, name, type, location, resourceGroup, subscriptionId, tags, properties
    """

    if resource_group:
        query += f"\n| where resourceGroup == '{resource_group}'"

    print("Running Resource Graph query...")
    query_request = QueryRequest(query=query, subscriptions=[subscription_id])
    resources_result = rg_client.resources(query_request)
    resources = list(resources_result.data)

    print(f"Retrieved {len(resources)} resources from Resource Graph.")

    # Extract nested resources from all parent resources based on hierarchy rules
    total_extracted = 0
    for resource in resources:
        nested_resources = extract_nested_resources_from_hierarchy_rules(resource)
        resources.extend(nested_resources)
        total_extracted += len(nested_resources)
    
    if total_extracted > 0:
        print(f"Added {total_extracted} nested resources extracted from parent resources.")

    # Always add subscription
    resources.append(get_subscription_resource(subscription_id))
    
    # Add resource groups - collect unique resource groups from resources
    resource_groups = set()
    for r in resources:
        rg_name = r.get("resourceGroup")
        if rg_name:
            resource_groups.add(rg_name)
    
    # If filtering by specific resource group, ensure it's included
    if resource_group:
        resource_groups.add(resource_group)
    
    # Add all resource groups
    for rg_name in resource_groups:
        resources.append(get_resource_group_resource(subscription_id, rg_name))
    
    return resources

def escape(s: str) -> str:
    if s is None:
        return ""
    return str(s).replace("'", "\\'")

def sanitize_id(resource_id: str) -> str:
    """Sanitize resource id for Gremlin vertex 'id' property (no '/')"""
    return resource_id.replace("/", "|")

def upsert_node(resource):
    """Idempotent upsert for a resource vertex"""
    global resources_by_id
    
    resource_id = resource["id"]
    name = escape(resource.get("name") or resource_id.split("/")[-1])
    label = resource_type_to_label(resource.get("type", "Resource"))
    type = resource.get("type", "Resource")
    rg = escape(resource.get("resourceGroup") or "")
    sub = escape(resource.get("subscriptionId") or subscription_id)

    # Use resourceId to find/create vertex, let Gremlin auto-generate the id
    gremlin = f"""
    g.V().has('resourceId','{resource_id}').fold()
     .coalesce(
       unfold(),
       addV('{label}')
         .property('resourceId','{resource_id}')
         .property('name','{name}')
         .property('type','{type}')
         .property('resourceGroup','{rg}')
         .property('subscriptionId','{sub}')
     )
    """
    try:
        cosmos_client.submit(gremlin)
        # register in map (if not already)
        resources_by_id[resource_id] = resource
        print(f"Node upserted: {name} ({type})")
    except Exception as e:
        print(f"ERROR upserting node {name} ({type}): {e}")

def ensure_vertex_exists(resource_id, display_name=None, resource_type="Resource"):
    """Create a minimal placeholder vertex if target not present."""
    global resources_by_id
    
    if resource_id in resources_by_id:
        return

    safe_name = escape(display_name or resource_id.split("/")[-1])
    label = resource_type_to_label(resource_type)

    # Use resourceId to find/create vertex, let Gremlin auto-generate the id
    gremlin = f"""
    g.V().has('resourceId','{resource_id}').fold()
     .coalesce(
       unfold(),
       addV('{label}')
        .property('resourceId','{resource_id}')
        .property('name','{safe_name}')
        .property('type','{resource_type}')
     )
    """
    try:
        cosmos_client.submit(gremlin)
        resources_by_id[resource_id] = {"id": resource_id, "name": safe_name, "type": resource_type}
        print(f"Placeholder node created: {safe_name} ({resource_type})")
    except Exception as e:
        print(f"ERROR creating placeholder {safe_name} ({resource_type}): {e}")

def get_resource_name(resource_id: str) -> str:
    """Extract the resource name from Azure resource ID."""
    if not resource_id:
        return ""
    
    parts = resource_id.strip("/").split("/")    
    if not parts:
        return ""
    
    # Subscription: /subscriptions/{subscription-id}
    if len(parts) == 2 and parts[0] == "subscriptions":
        return get_subscription_name(parts[1])

    return parts[-1]

def upsert_edge_select(src_id, dst_id, rel):
    """Gremlin-safe upsert of an edge using select() to reference aliases."""
    if not src_id or not dst_id or src_id == dst_id:
        return
    # ensure dst exists
    if dst_id not in resources_by_id:
        ensure_vertex_exists(dst_id)

    src_name = get_resource_name(src_id)
    dst_name = get_resource_name(dst_id)

    gremlin = f"""
    g.V().has('resourceId','{src_id}').as('a')
     .V().has('resourceId','{dst_id}').as('b')
     .coalesce(
       select('a').outE('{escape(rel)}').where(inV().has('resourceId','{dst_id}')),
       select('a').addE('{escape(rel)}').to(select('b'))
     )
    """
    try:
        cosmos_client.submit(gremlin)
        print(f"Edge upserted: {src_name} --({rel})--> {dst_name}")
    except Exception as e:
        print(f"ERROR creating edge {src_name} --({rel})--> {dst_name}: {e}")

# ---------------------------
# Relationship discovery
# ---------------------------

def resource_type_to_label(resource_type: str) -> str:
    """
    Converts Azure resource type (e.g., 'microsoft.network/virtualnetworks')
    into a PascalCase label (e.g., 'VirtualNetwork') for Cosmos Gremlin vertices.
    """
    parts = resource_type.split("/", maxsplit=1)

    if len(parts) == 1:
        resource_name = parts[0]
    else:
        resource_name = parts[1]

    components = resource_name.split("/")

    def normalize(word: str) -> str:
        if word.endswith("s"):      # optional plural removal
            word = word[:-1]
        return word.capitalize()

    return "".join(normalize(c) for c in components)

def is_resource_group(resource_id):
    """Check if the given resource ID represents a resource group."""
    parts = resource_id.strip("/").split("/")
    # Resource group format: /subscriptions/{sub}/resourceGroups/{rg}
    return (len(parts) == 4 and 
            parts[0] == "subscriptions" and 
            parts[2] == "resourceGroups")

def derive_parent_candidate_ids(resource_id):
    """
    Build ONE parent ID from Azure resource path hierarchy.
    STRICT RULE: Each resource has exactly one parent.
    Hierarchy: Subscription -> Resource Group -> Resource -> Subresource -> Subresource
    """
    src_resource_name = get_resource_name(resource_id)

    parts = resource_id.strip("/").split("/")
    
    # Check if this is a resource group
    if is_resource_group(resource_id):
        # For resource groups, subscription is the only parent
        subscription_id_part = parts[1]
        subscription_path = f"/subscriptions/{subscription_id_part}"
        print(f"🏛️  Resource Group {src_resource_name} -> parent: {subscription_path}")
        return [subscription_path]
    
    # For all other resources, find the immediate parent
    
    # Handle provider-based nested resources (like VNet -> Subnet, NSG -> SecurityRules)
    providers_index = -1
    for i, part in enumerate(parts):
        if part == "providers":
            providers_index = i
            break
    
    if providers_index != -1 and len(parts) > providers_index + 4:
        # Has provider structure and enough parts for nesting
        # Remove the last type/name pair to get immediate parent
        parent_parts = parts[:-2]
        if len(parent_parts) > providers_index + 2:  # Still a valid resource after removing type/name
            parent_path = "/" + "/".join(parent_parts)
            parent_resource_name = get_resource_name(parent_path)
            print(f"📦 Nested Resource {src_resource_name} -> parent: {parent_resource_name}")
            return [parent_path]
    
    # Handle basic Azure hierarchy - Resource Group as parent for top-level resources
    if len(parts) >= 4 and parts[0] == "subscriptions" and parts[2] == "resourceGroups":
        subscription_id_part = parts[1]
        resource_group_name = parts[3]
        resource_group_path = f"/subscriptions/{subscription_id_part}/resourceGroups/{resource_group_name}"
        
        # For resources under resource group, resource group is the parent
        if len(parts) > 4:
            print(f"📦 Resource {src_resource_name} -> parent: {resource_group_name}")
            return [resource_group_path]
    
    print(f"⚠️  No parent found for {resource_id}")
    return []

def get_applicable_hierarchy_rules(child_type):
    """Get hierarchy rules that apply to the given child type."""
    hierarchy_rules = relationship_config.get("hierarchy_rules", [])
    applicable_rules = []
    
    for rule in hierarchy_rules:
        child_pattern = rule.get("child", "").lower()
        if child_pattern == "*" or child_pattern == child_type.lower():
            applicable_rules.append(rule)
    
    return applicable_rules

def derive_parent_from_hierarchy_rules(resource):
    """
    Find parent based on hierarchy rules from config.
    ENFORCES: Subscription -> Resource Group -> Resources (never Subscription -> Resources)
    Creates BOTH hierarchical parent AND resource group parent for nested resources.
    """
    resource_type = resource.get("type", "").lower()
    resource_id = resource["id"]
    
    applicable_rules = get_applicable_hierarchy_rules(resource_type)
    
    relationships_created = 0
    
    # For nested resources (e.g., AI Foundry Projects), create hierarchical parent link
    for rule in applicable_rules:
        parent_type = rule.get("parent", "").lower()
        relationship = rule.get("relationship", "HAS")
        
        # Get candidates (already filtered to prevent subscription bypass)
        parent_candidates = derive_parent_candidate_ids(resource_id)
        
        for parent_id in parent_candidates:
            if parent_id in resources_by_id:
                parent_resource = resources_by_id[parent_id]
                parent_resource_type = parent_resource.get("type", "").lower()
                
                # Double-check: NEVER allow subscription as parent for non-resource-groups
                if (parent_resource_type == "microsoft.resources/subscriptions" and 
                    resource_type != "microsoft.resources/resourcegroups"):
                    print(f"❌ FATAL: Blocked subscription parent for {resource_type} - this should not happen!")
                    continue
                
                # Check if this parent matches the rule
                if parent_type == "*" or parent_type == parent_resource_type:
                    print(f"✅ Creating: {parent_resource_type} --({relationship})--> {resource_type}")
                    upsert_edge_select(parent_id, resource_id, relationship)
                    relationships_created += 1
    
    # Additionally, ensure ALL top-level resources link to their resource group
    # (This handles resources that appear in Azure Portal as standalone resources)
    resource_group_name = resource.get("resourceGroup")
    if resource_group_name and resource_type != "microsoft.resources/resourcegroups":
        subscription_id_from_resource = resource.get("subscriptionId") or subscription_id
        resource_group_id = f"/subscriptions/{subscription_id_from_resource}/resourceGroups/{resource_group_name}"
        
        if resource_group_id in resources_by_id:
            # Check if we already created this relationship
            parent_candidates = derive_parent_candidate_ids(resource_id)
            if resource_group_id not in parent_candidates:
                # This is a nested resource that should ALSO link to RG
                print(f"🔗 Additional RG link: rg-{resource_group_name} --(HAS)--> {resource.get('name')}")
                upsert_edge_select(resource_group_id, resource_id, "HAS")
                relationships_created += 1
    
    return relationships_created > 0

def process_hierarchy_rules():
    """Process all resources and create hierarchy relationships based on config rules."""
    print("\n-- Creating hierarchy-based relationships --")
    print("🔒 ENFORCING: Subscription -> Resource Group -> Resources (no subscription bypass)")
    
    total_relationships = 0
    for resource_id, resource in resources_by_id.items():
        if derive_parent_from_hierarchy_rules(resource):
            total_relationships += 1
    
    print(f"Created hierarchy relationships for {total_relationships} resources.")

def process_property_rules(resource):
    """Use jsonpath rules from config to create edges."""
    property_rules = relationship_config.get("property_rules", []) or []
    for rule in property_rules:
        src_type = (rule.get("source_type") or "").lower()
        if src_type != "*" and src_type not in resource.get("type", "").lower():
            continue

        prop_path = rule.get("property_path")
        if not prop_path:
            continue

        try:
            expr = jsonpath_parse(prop_path)
        except Exception as e:
            print(f"Invalid jsonpath '{prop_path}' in config: {e}")
            continue

        matches = [m.value for m in expr.find(resource) if m.value]
        if not matches:
            continue

        for match in matches:
            if match is None:
                continue
            # normalize to list
            dsts = match if isinstance(match, list) else [match]
            for dst in dsts:
                if not dst:
                    continue
                dst_id = dst
                # Create placeholder if missing
                if dst_id not in resources_by_id:
                    ensure_vertex_exists(dst_id)
                upsert_edge_select(resource["id"], dst_id, rule.get("relationship", "ASSOCIATED_WITH"))

# ---------------------------
# Main ingestion flow
# ---------------------------

def main():
    global resources_by_id  # Use the global variable
    
    # 1) Get the list of resources (including subscription and resource groups and nested resources)
    resources = get_resource_list()
    
    print(f"\nTotal resources to process: {len(resources)}")
    
    # 1) Upsert all nodes
    print("\n-- Upserting nodes --")
    for r in resources:
        upsert_node(r)

    # 2) Create hierarchy-based relationships using config rules
    process_hierarchy_rules()

    # 3) Create property-based edges
    print("\n-- Creating property-derived edges --")
    for r in resources:
        process_property_rules(r)

    # 4) Create dependency edges from Resource Graph 'dependencies' if present
    print("\n-- Creating explicit DEPENDS_ON edges from Resource Graph --")
    dep_rel = relationship_config.get("dependency_rules", {}).get("relationship", "DEPENDS_ON")
    for r in resources:
        deps = r.get("dependencies") or []
        # sometimes dependencies are under properties.dependencies
        if not deps:
            deps = (r.get("properties") or {}).get("dependencies") or []

        for d in deps:
            dst = d.get("resourceId") or d.get("id") or None
            if not dst:
                continue
            if dst not in resources_by_id:
                ensure_vertex_exists(dst)
            upsert_edge_select(r["id"], dst, dep_rel)

    # 5) Optional: tag-based rules
    print("\n-- Creating tag-based edges (if config defines) --")
    tag_rules = relationship_config.get("tag_rules", []) or []
    for r in resources:
        tags = r.get("tags") or {}
        for tag_rule in tag_rules:
            tname = tag_rule.get("tag_name")
            rel = tag_rule.get("relationship", "DEPENDS_ON")
            if tname and tname in tags:
                # tag value may contain a resourceId or comma-separated ids
                val = tags.get(tname)
                if not val:
                    continue
                candidates = [v.strip() for v in str(val).split(",") if v.strip()]
                for cand in candidates:
                    if cand not in resources_by_id:
                        ensure_vertex_exists(cand)
                    upsert_edge_select(r["id"], cand, rel)

    print("\n✅ All relationships created successfully.")
    print("🔒 Enforced hierarchy: Subscription -> Resource Group -> Resources")

if __name__ == "__main__":
    try:
        start = time.time()
        main()
        duration = time.time() - start
        print(f"\nCompleted ingestion in {duration:.2f}s")
    finally:
        # gracefully close gremlin client to prevent shutdown race exceptions
        try:
            cosmos_client.close()
            time.sleep(1)
        except Exception:
            pass
