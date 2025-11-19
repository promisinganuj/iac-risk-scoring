import os
from dotenv import load_dotenv
from azure.identity import AzureCliCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from gremlin_python.driver import client, serializer

load_dotenv(dotenv_path="./../.env")

# Access variables
subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
resource_group = os.getenv("RESOURCE_GROUP")
gremlin_host = os.getenv("COSMOS_GREMLIN_HOST")
gremlin_db = os.getenv("COSMOS_GREMLIN_DATABASE")
gremlin_graph = os.getenv("COSMOS_GREMLIN_GRAPH")
gremlin_key = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY")

# Validate required environment variables
if not all([subscription_id, resource_group, gremlin_host, gremlin_db, gremlin_graph, gremlin_key]):
    raise ValueError("Missing required environment variables. Please check your .env file.")

gremlin_endpoint = f"wss://{gremlin_host}.gremlin.cosmos.azure.com:443/"
print(f"Connecting to Gremlin endpoint: {gremlin_endpoint}")

### 1. CONNECT TO COSMOS GREMLIN GRAPH
cosmos_client = client.Client(
    gremlin_endpoint,
    "g",
    username=f"/dbs/{gremlin_db}/colls/{gremlin_graph}",
    password=gremlin_key, # pyright: ignore[reportArgumentType]
    message_serializer=serializer.GraphSONSerializersV2d0()
)

### 2. RUN RESOURCE GRAPH QUERY
credential = AzureCliCredential()
resource_graph_client = ResourceGraphClient(credential)

query = f"""
Resources
| where resourceGroup == '{resource_group}'
| extend dependencies = properties.dependencies
| project id, name, type, location, resourceGroup, subscriptionId, tags, dependencies
"""

print("Fetching Azure resources via Resource Graph...")

query_request = QueryRequest(
    query=query,
    subscriptions=[subscription_id] # pyright: ignore[reportArgumentType]
)

resources = resource_graph_client.resources(query_request)

print(f"✅ Retrieved {len(resources.data)} resources.") # pyright: ignore[reportArgumentType]


### 3. HELPER: UPSERT NODE IN GRAPH
def upsert_node(resource):
    # Use resourceId as the partition key property
    resource_id = resource["id"]
    # Escape single quotes in strings to prevent Gremlin query issues
    resource_name = resource["name"].replace("'", "\\'")
    resource_type = resource["type"].replace("'", "\\'")
    location = resource.get("location", "").replace("'", "\\'")
    resource_group = resource["resourceGroup"].replace("'", "\\'")
    
    query = f"""
        g.V().has('resourceId', '{resource_id}').fold().
        coalesce(unfold(),
                 addV('{resource_type}')
                    .property('resourceId', '{resource_id}')
                    .property('name', '{resource_name}')
                    .property('location', '{location}')
                    .property('resourceGroup', '{resource_group}')
                    .property('subscriptionId', '{resource["subscriptionId"]}')
        )
    """
    try:
        result = cosmos_client.submitAsync(query).result()
        print(f"✅ Upserted node: {resource_name}")
        return result
    except Exception as e:
        print(f"❌ Error upserting node {resource_name}: {e}")
        raise


### 4. HELPER: UPSERT DEPENDENCY EDGE
def upsert_edge(src_id, dst_id):
    query = f"""
        g.V().has('resourceId', '{src_id}').as('a')
         .V().has('resourceId', '{dst_id}').as('b')
         .coalesce(a.outE('dependsOn').where(inV().has('resourceId', '{dst_id}')),
                   a.addE('dependsOn').to(b))
    """
    try:
        result = cosmos_client.submitAsync(query).result()
        print(f"✅ Created dependency: {src_id} -> {dst_id}")
        return result
    except Exception as e:
        print(f"❌ Error creating edge {src_id} -> {dst_id}: {e}")
        # Don't raise here as the dependency target might not exist


### PROCESS RESOURCES
for r in resources.data: # pyright: ignore[reportGeneralTypeIssues]
    upsert_node(r)  # Add node
    deps = r.get("dependencies") or []

    for d in deps:
        print(f"Found dependency: {d.get('resourceId')}")
        dep_id = d.get("resourceId")
        if dep_id:
            upsert_edge(r["resourceId"], dep_id)

print("✅ Graph ingestion complete.")
