# Azure Infrastructure Risk Scoring with Graph Database

A repository to perform risk scoring for Infrastructure as Code (IaC) changes by ingesting Azure resources into Azure Cosmos DB for Apache Gremlin database and analyzing their relationships.

## Overview

This project ingests Azure infrastructure resources into Azure Cosmos DB Gremlin API (graph database) to model relationships between resources. The graph structure enables advanced queries for risk analysis, dependency tracking, and impact assessment of infrastructure changes.

### Key Features

- **Automated Resource Discovery**: Queries Azure Resource Graph to discover all resources in a subscription
- **Hierarchical Modeling**: Creates parent-child relationships (Subscription → Resource Group → Resources)
- **Nested Resource Extraction**: Automatically extracts nested resources (e.g., VNet subnets, NSG security rules)
- **Property-Based Relationships**: Discovers relationships by analyzing resource properties (e.g., NIC → Subnet)
- **Dependency Tracking**: Imports explicit dependencies from Azure Resource Graph
- **Tag-Based Associations**: Creates custom relationships based on resource tags
- **Configurable Rules**: Relationship logic defined in YAML configuration file

## Architecture

```
Azure Subscription
    ↓ (Azure Resource Graph API)
Python Ingestion Script
    ↓ (Gremlin/TinkerPop)
Azure Cosmos DB (Gremlin API)
```

## Prerequisites

- **Azure Subscription**: With resources to analyze
- **Azure CLI**: Installed and authenticated (`az login`)
- **Azure Cosmos DB**: Gremlin API account with database and graph collection
- **Python 3.8+**: For running the ingestion script

## Setup

### 1. Create and Activate Virtual Environment

```bash
cd approach1-creating-knowlege-graph
uv venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
uv pip install -r ../requirements.txt --native-tls
```

### 3. Configure Environment Variables

Create a `.env` file by copying [.env.template](./.env.template) and filling in your values:

```bash
cp .env.template .env
```

Then edit `.env` to configure your environment variables:

```bash
# Azure Subscription
export AZURE_SUBSCRIPTION_ID=<your_subscription_id>
# Optional: Filter by specific resource group
export RESOURCE_GROUP=<your_resource_group>
export LOCATION=<your_location>
export COSMOS_GREMLIN_HOST=<your_cosmos_db_account_name>
# wss://${COSMOS_GREMLIN_HOST}.gremlin.cosmos.azure.com:443/
export COSMOS_GREMLIN_ENDPOINT=<your_cosmos_db_gremlin_uri>
export COSMOS_GREMLIN_DATABASE=<your_cosmos_db_database_name>
export COSMOS_GREMLIN_GRAPH=<your_cosmos_db_graph_name>
export COSMOS_GREMLIN_PRIMARY_KEY=<your_cosmos_db_primary_key>
```

### 4. Configure Relationship Rules

Edit [config/relationship-config.yaml](./config/relationship-config.yaml) to customize relationship detection rules. The configuration supports:

- **Hierarchy Rules**: Parent-child relationships based on Azure resource paths
- **Property Rules**: Relationships derived from resource properties (using JSONPath)
- **Dependency Rules**: Explicit dependencies from Azure Resource Graph
- **Tag Rules**: Custom relationships based on resource tags

## Usage

### Run the Ingestion Script

```bash
python scripts/100_ingest_azure_to_graph.py
```

### What It Does

1. **Connects to Azure**: Authenticates using Azure CLI credentials
2. **Queries Resources**: Retrieves all resources from Azure Resource Graph
3. **Extracts Nested Resources**: Discovers subnets, security rules, and other nested resources
4. **Creates Vertices**: Upserts each resource as a graph vertex with properties
5. **Creates Edges**: Establishes relationships based on:
   - Hierarchical structure (subscription → resource group → resource)
   - Property references (e.g., NIC references subnet)
   - Explicit dependencies
   - Custom tag-based associations
6. **Ensures Data Integrity**: Creates placeholder vertices for referenced resources not in the subscription

### Example Output

```
Connected to Gremlin endpoint: wss://your-account.gremlin.cosmos.azure.com:443/
Running Resource Graph query...
Retrieved 47 resources from Resource Graph.
Found 3 subnets in vnet-production
Extracted microsoft.network/virtualnetworks/subnets: default from vnet-production
Added 5 nested resources extracted from parent resources.

-- Upserting nodes --
Node upserted: MySubscription (microsoft.resources/subscriptions)
Node upserted: rg-production (microsoft.resources/resourcegroups)
Node upserted: vnet-production (microsoft.network/virtualnetworks)
Node upserted: default (microsoft.network/virtualnetworks/subnets)

-- Creating hierarchy-based relationships --
🔒 ENFORCING: Subscription -> Resource Group -> Resources (no subscription bypass)
✅ Creating: microsoft.resources/subscriptions --(HAS)--> microsoft.resources/resourcegroups
✅ Creating: microsoft.resources/resourcegroups --(HAS)--> microsoft.network/virtualnetworks
📦 Nested Resource default -> parent: vnet-production
✅ Creating: microsoft.network/virtualnetworks --(HAS)--> microsoft.network/virtualnetworks/subnets

-- Creating property-derived edges --
Edge upserted: nic-vm01 --(PLACED_IN)--> default

Completed ingestion in 12.34s
```

## Configuration Reference

### Hierarchy Rules

Define parent-child relationships based on Azure resource types:

```yaml
hierarchy_rules:
  - parent: "microsoft.resources/subscriptions"
    child: "microsoft.resources/resourcegroups"
    relationship: "HAS"
  
  - parent: "microsoft.network/virtualnetworks"
    child: "microsoft.network/virtualnetworks/subnets"
    relationship: "HAS"
```

### Property Rules

Extract relationships from resource properties using JSONPath:

```yaml
property_rules:
  - source_type: "microsoft.network/networkinterfaces"
    property_path: "properties.ipConfigurations[*].properties.subnet.id"
    relationship: "PLACED_IN"
```

### Dependency Rules

Configure how Azure Resource Graph dependencies are imported:

```yaml
dependency_rules:
  relationship: "DEPENDS_ON"
```

### Tag Rules

Create relationships based on resource tags:

```yaml
tag_rules:
  - tag_name: "dependsOn"
    relationship: "DEPENDS_ON"
```

## Graph Schema

### Vertex Properties

Each resource vertex contains:
- `resourceId`: Azure resource ID (unique identifier)
- `name`: Resource name
- `type`: Azure resource type
- `resourceGroup`: Resource group name
- `subscriptionId`: Subscription ID
- `tags`: Resource tags (optional)
- `properties`: Additional properties (optional)

### Edge Relationships

Common relationship types:
- `HAS`: Hierarchical containment (subscription → resource group → resource)
- `PLACED_IN`: Resource placement (NIC → subnet)
- `ASSOCIATED_WITH`: General association (subnet → NSG)
- `DEPENDS_ON`: Explicit dependency
- `USES_PUBLIC_IP`: Service dependency
- `HAS_RULE`: Configuration rules (NSG → security rules)

## Querying the Graph

Once data is ingested, you can query the graph using Gremlin queries. Examples:

### Find all resources in a resource group
```gremlin
g.V().has('resourceGroup', 'rg-production').values('name')
```

### Find dependencies of a resource
```gremlin
g.V().has('name', 'vm-app01').out('DEPENDS_ON').values('name')
```

### Find the path from subscription to a specific resource
```gremlin
g.V().has('type', 'microsoft.resources/subscriptions')
  .repeat(out()).until(has('name', 'vm-app01'))
  .path().by('name')
```

### Find all resources connected to a subnet
```gremlin
g.V().has('name', 'subnet-web').in().values('name')
```

## Troubleshooting

### Authentication Issues
- Ensure you're logged in: `az login`
- Verify subscription access: `az account show`

### Missing Resources
- Check `RESOURCE_GROUP` filter in `.env`
- Verify Azure Resource Graph query permissions

### Connection Errors
- Verify Cosmos DB endpoint and credentials
- Check firewall settings on Cosmos DB account
- Ensure Gremlin API is enabled

### Relationship Issues
- Review `config/relationship-config.yaml` syntax
- Check JSONPath expressions using a validator
- Enable verbose logging by adding print statements

## Project Structure

```
approach1-creating-knowlege-graph/
├── config/
│   └── relationship-config.yaml      # Relationship detection rules
├── scripts/
│   ├── 000_create_base_infra.sh      # Infrastructure setup script
│   └── 100_ingest_azure_to_graph.py  # Main ingestion script
├── .env.template                     # Environment variables template
├── .env                              # Environment variables (local, not committed)
└── README.md
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

See [LICENSE](../LICENSE) file for details.

## Future Enhancements

- [ ] Add risk scoring algorithms based on graph analysis
- [ ] Implement change impact assessment
- [ ] Add support for Azure Policy compliance checking
- [ ] Create visualization layer for graph exploration
- [ ] Add incremental updates instead of full refresh
- [ ] Support for multi-subscription ingestion
- [ ] Integration with CI/CD pipelines for IaC validation
