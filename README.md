# IaC Risk Scoring (Experiments)

This repo contains a few small, independent approaches for scoring Infrastructure-as-Code (IaC) risk.

## What's Inside

### Approach 1: Create a knowledge graph from Azure

Ingests resources from **Azure Resource Graph** into **Azure Cosmos DB Gremlin API** and creates relationships for dependency/risk analysis.

- Folder: `approach1-creating-knowlege-graph/`
- Docs: [Approach 1 README](./approach1-creating-knowlege-graph/README.md)

Quick start:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt --native-tls
cd approach1-creating-knowlege-graph

cp .env.template .env
# edit .env

# optional (creates Cosmos DB Gremlin database/graph)
bash scripts/000_create_base_infra.sh

python scripts/100_ingest_azure_to_graph.py
```

Prereqs: Azure CLI (`az login`), a Cosmos DB Gremlin account, Python 3.8+.

---

### Approach 2: Use an existing graph (Neo4j prototype)

Runs a local **Neo4j** instance using Docker and imports a sample dataset (CSVs) into a graph schema for exploration.

- Folder: `approach2-using-existing-graph/`

Quick start:

```bash
cd approach2-using-existing-graph
export NEO4J_PASSWORD='password'
./scripts/neo4j_up_and_import.sh
```

Then open Neo4j Browser at `http://localhost:7475` (defaults from the script).

---

### Utils: Terraform plan parser + scorer

Parses Terraform plan JSON (optionally uses a Terraform dependency graph) and produces a simple rule-based risk score.

- Folder: `utils/terraform-plan-parser-and-scorer/`

Quick start (using the sample files already in the folder):

```bash
cd utils/terraform-plan-parser-and-scorer
python score_terraform_plan.py terraform_plan.json terraform_graph.dot
```

If you want to score your own plan:

```bash
terraform plan -out tfplan.binary
terraform show -json tfplan.binary > terraform_plan.json
terraform graph > terraform_graph.dot
python score_terraform_plan.py terraform_plan.json terraform_graph.dot
```

## License

See [LICENSE](./LICENSE).
