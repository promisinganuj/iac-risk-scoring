import os
from dotenv import load_dotenv
import yaml
import jmespath
from jsonpath_ng import parse

from azure.identity import AzureCliCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from gremlin_python.driver import client, serializer

load_dotenv(dotenv_path="./../.env")

subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
resource_group_filter = os.getenv("RESOURCE_GROUP")
gremlin_host = os.getenv("COSMOS_GREMLIN_HOST")
gremlin_db = os.getenv("COSMOS_GREMLIN_DATABASE")
gremlin_graph = os.getenv("COSMOS_GREMLIN_GRAPH")
gremlin_key = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY")

if not all([subscription_id, gremlin_host, gremlin_db, gremlin_graph, gremlin_key]):
    raise ValueError("Missing required .env variables.")

print(f"✅ Loaded configuration from .env")

# Load YAML config-driven relationship mapping
with open("../config/relationship-config.yaml", "r") as f:
    relationship_config = yaml.safe_load(f)

print("✅ Loaded relationship configuration (relationship-config.yaml)")

gremlin_endpoint = f"wss://{gremlin_host}.gremlin.cosmos.azure.com:443/"

cosmos_client = client.Client(
    gremlin_endpoint,
    "g",
    username=f"/dbs/{gremlin_db}/colls/{gremlin_graph}",
    password=gremlin_key,
    message_serializer=serializer.GraphSONSerializersV2d0()
)

print(f"🔌 Connected to Cosmos DB Gremlin")

credential = AzureCliCredential()
rg_client = ResourceGraphClient(credential)

query = f"""
Resources
| where type != "" 
| extend properties = todynamic(properties)
| project id, name, type, location, resourceGroup, subscriptionId, tags, properties
"""

if resource_group_filter:
    query += f"\n| where resourceGroup == '{resource_group_filter}'"

resources = rg_client.resources(QueryRequest(
    subscriptions=[subscription_id],
    query=query
))

print(f"📦 Retrieved {len(resources.data)} Azure resources")

def upsert_node(resource):
    """Create or update a vertex"""
    resource_id = resource["id"]
    resource_type = resource["type"]
    name = resource["name"].replace("'", "\\'")

    query = f"""
        g.V().has('resourceId', '{resource_id}').fold().
        coalesce(
            unfold(),
            addV('{resource_type}')
                .property('resourceId', '{resource_id}')
                .property('name', '{name}')
                .property('resourceType', '{resource_type}')
                .property('resourceGroup', '{resource["resourceGroup"]}')
                .property('subscriptionId', '{resource["subscriptionId"]}')
        )
    """
    cosmos_client.submitAsync(query).result()
    print(f"🟩 Node: {name} ({resource_type})")


def upsert_edge(src_id, dst_id, rel="DEPENDS_ON"):
    query = f"""
        g.V().has('resourceId', '{src_id}').as('a')
         .V().has('resourceId', '{dst_id}').as('b')
         .coalesce(
             select('a').outE('{rel}').where(inV().has('resourceId', '{dst_id}')),
             select('a').addE('{rel}').to(select('b'))
         )
    """
    cosmos_client.submitAsync(query).result()
    print(f"➡️  {rel}: {src_id} -> {dst_id}")


def discover_relationships(resource, resources_by_id):
    edges = []

    # 1. hierarchy (based on ARM id segments)
    for rule in relationship_config["hierarchy_rules"]:
        parent = rule["parent"].lower()
        child = rule["child"].lower()

        if parent in resource["id"].lower():
            continue  # can't match if resource *is* parent

        if child == "*" or child in resource["type"].lower():
            # Detect parent by removing last segment of ResourceId
            parent_id = "/".join(resource["id"].split("/")[0:-2])
            if parent_id in resources_by_id:
                edges.append((parent_id, resource["id"], rule["relationship"]))

    # 2. property relationships (via jsonpath)
    for rule in relationship_config["property_rules"]:
        if rule["source_type"].lower() not in resource["type"].lower():
            continue

        jsonpath_expr = parse(rule["property_path"])
        results = [match.value for match in jsonpath_expr.find(resource) if match.value]

        for dst in results:
            edges.append((resource["id"], dst, rule["relationship"]))

    # 3. dependency relationships from Resource Graph
    deps = resource.get("dependencies") or []
    for d in deps:
        dst_id = d.get("resourceId")
        if dst_id:
            edges.append((resource["id"], dst_id, relationship_config["dependency_rules"]["relationship"]))

    return edges

print("\n🚀 Creating/Upserting nodes...")
for resource in resources.data:
    upsert_node(resource)
print("\n🔍 Establishing relationships...")

resources_by_id = {r["id"]: r for r in resources.data}

for resource in resources.data:
    src_type = resource["type"].lower()

    for src, dst, rel in discover_relationships(resource, resources_by_id):
        upsert_edge(src, dst, rel)

print("\n✅ Graph ingestion complete — all nodes + relationships created!")

cosmos_client.close()
