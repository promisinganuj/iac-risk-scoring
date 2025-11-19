# Business Requirements Document
# IaC Risk Scoring with Knowledge Graph

**Project:** Azure Infrastructure as Code Risk Analysis using Knowledge Graph  
**Last Updated:** 20 November 2025  
**Branch:** initial-changes

---

## Executive Summary

This project implements a risk scoring system for Infrastructure as Code (IaC) changes by leveraging Azure Cosmos DB Gremlin API (Knowledge Graph) to model Azure resources, their relationships, and identify risks when comparing existing infrastructure with proposed ARM template changes.

---

## Implementation Plan

### Phase 1: Foundation Setup ✅
**Goal:** Establish Knowledge Graph infrastructure and baseline data ingestion

#### 1.1 Provision Knowledge Graph Instance ✅
- **Status:** COMPLETED
- **Script:** `scripts/000_create_base_infra.sh`
- **Description:** Creates Azure Cosmos DB Gremlin API database and graph collection
- **Dependencies:** None
- **GitHub Copilot Compatibility:** ✅ Script-based, no LLM agent needed

#### 1.2 Import Existing Azure Infrastructure ✅
- **Status:** COMPLETED
- **Script:** `scripts/100_ingest_azure_to_graph.py`
- **Description:** Queries Azure Resource Graph and ingests resources into Knowledge Graph with relationships
- **Dependencies:** 1.1
- **GitHub Copilot Compatibility:** ✅ Script-based, no LLM agent needed

---

### Phase 2: ARM Template Ingestion 🔄
**Goal:** Parse and import ARM templates into Knowledge Graph

#### 2.1 ARM Template Parser
- **Status:** NOT STARTED
- **Script:** `scripts/200_parse_arm_template.py`
- **Description:** 
  - Parse ARM template JSON files
  - Extract resources, parameters, variables, and dependencies
  - Normalize resource definitions to match Azure Resource Graph schema
  - Handle ARM template functions (concat, resourceId, reference, etc.)
- **Key Functions:**
  - `parse_arm_template(template_path)` - Main parser
  - `resolve_arm_expressions(template)` - Resolve ARM functions
  - `extract_resources(template)` - Extract resource definitions
  - `extract_dependencies(resource)` - Extract dependsOn relationships
- **Dependencies:** Phase 1
- **GitHub Copilot Compatibility:** ✅ Standard Python development
- **Recommended LLM Agent:** None needed for basic implementation

#### 2.2 ARM Template to Graph Ingestion
- **Status:** NOT STARTED
- **Script:** `scripts/210_ingest_arm_to_graph.py`
- **Description:**
  - Ingest parsed ARM template resources into Knowledge Graph
  - Create vertices with label prefix "PROPOSED_" to distinguish from existing
  - Create edges based on ARM template dependencies
  - Handle parameter substitution and variable resolution
- **Key Functions:**
  - `ingest_arm_resources(parsed_template, graph_client)`
  - `create_proposed_vertex(resource, graph_client)`
  - `create_proposed_edges(resource, dependencies, graph_client)`
- **Dependencies:** 2.1
- **GitHub Copilot Compatibility:** ✅ Similar to existing ingestion script
- **Recommended LLM Agent:** None needed

---

### Phase 3: Comparison and Analysis 🔄
**Goal:** Compare existing infrastructure with proposed changes

#### 3.1 Graph Comparison Engine
- **Status:** NOT STARTED
- **Script:** `scripts/300_compare_graphs.py`
- **Description:**
  - Compare existing vs proposed resources in Knowledge Graph
  - Identify additions, deletions, and modifications
  - Analyze relationship changes (edges added/removed)
  - Generate diff report
- **Key Functions:**
  - `compare_resources(existing_id, proposed_id, graph_client)`
  - `find_additions(graph_client)` - New resources in ARM template
  - `find_deletions(graph_client)` - Resources not in ARM template
  - `find_modifications(graph_client)` - Changed resource properties
  - `find_relationship_changes(graph_client)` - Edge differences
- **Dependencies:** 2.2
- **GitHub Copilot Compatibility:** ✅ Gremlin query development
- **Recommended LLM Agent:** None needed

#### 3.2 Query Interface Development
- **Status:** NOT STARTED
- **Script:** `scripts/310_query_interface.py`
- **Description:**
  - Create Python functions to query Knowledge Graph
  - Support common query patterns (dependencies, blast radius, path finding)
  - Return results in structured format
- **Key Functions:**
  - `get_resource_dependencies(resource_id, depth=1)`
  - `get_impacted_resources(resource_id, depth=2)` - Blast radius
  - `find_path_between_resources(source_id, target_id)`
  - `get_resources_by_type(resource_type)`
- **Dependencies:** Phase 1, 2
- **GitHub Copilot Compatibility:** ✅ Standard Python + Gremlin
- **Recommended LLM Agent:** None needed

---

### Phase 4: Risk Identification 🔄
**Goal:** Implement risk scoring and pattern detection

#### 4.1 Risk Scoring Engine
- **Status:** NOT STARTED
- **Script:** `scripts/400_risk_scoring.py`
- **Description:**
  - Define risk scoring rules in YAML configuration
  - Implement risk calculation based on:
    - Resource type criticality (e.g., databases, network security groups)
    - Change type (deletion > modification > addition)
    - Blast radius (number of dependent resources)
    - Security implications (public exposure, access control changes)
- **Configuration:** `config/risk-scoring-rules.yaml`
- **Key Functions:**
  - `calculate_risk_score(change, graph_client)` - Returns 0-100 score
  - `get_blast_radius(resource_id, graph_client)` - Count impacted resources
  - `detect_security_risks(change)` - Flag security-related changes
  - `apply_risk_rules(change, rules)` - Apply configured rules
- **Dependencies:** 3.1, 3.2
- **GitHub Copilot Compatibility:** ✅ Rule-based logic
- **Recommended LLM Agent:** **YES - For risk pattern analysis**
  - Use LLM to analyze complex change patterns
  - Identify subtle security implications
  - Suggest risk descriptions in natural language

#### 4.2 Risky Pattern Detection
- **Status:** NOT STARTED
- **Script:** `scripts/410_pattern_detection.py`
- **Description:**
  - Detect known risky patterns (e.g., NSG rule changes, public IP exposure)
  - Use graph traversal to identify anti-patterns
  - Flag suspicious dependency changes
- **Configuration:** `config/risky-patterns.yaml`
- **Key Functions:**
  - `detect_public_exposure(changes, graph_client)` - Resources becoming public
  - `detect_security_rule_weakening(changes, graph_client)` - NSG changes
  - `detect_critical_dependency_changes(changes, graph_client)`
  - `detect_cross_environment_references(changes, graph_client)`
- **Dependencies:** 4.1
- **GitHub Copilot Compatibility:** ✅ Pattern matching logic
- **Recommended LLM Agent:** **YES - For pattern discovery**
  - Use LLM to identify emerging patterns in historical data
  - Generate pattern descriptions
  - Suggest new patterns based on industry best practices

#### 4.3 Blast Radius Calculation
- **Status:** NOT STARTED
- **Script:** `scripts/420_blast_radius.py`
- **Description:**
  - Calculate impact scope of each change
  - Traverse graph to find all downstream dependencies
  - Categorize impact by resource type and criticality
- **Key Functions:**
  - `calculate_blast_radius(resource_id, change_type, graph_client)`
  - `get_downstream_dependencies(resource_id, max_depth=5)`
  - `categorize_impact(impacted_resources)` - Group by type/env
  - `visualize_blast_radius(resource_id)` - Generate graph visualization
- **Dependencies:** 3.2
- **GitHub Copilot Compatibility:** ✅ Graph traversal
- **Recommended LLM Agent:** None needed

---

### Phase 5: LLM-Powered Analysis 🔄
**Goal:** Enable natural language interaction and intelligent explanations

#### 5.1 LLM Query Interface
- **Status:** NOT STARTED
- **Script:** `scripts/500_llm_query_interface.py`
- **Description:**
  - Integrate LLM (Azure OpenAI or similar) to answer natural language questions
  - Translate user questions to Gremlin queries
  - Format graph results into human-readable responses
- **Key Functions:**
  - `ask_question(question, graph_client, llm_client)`
  - `translate_to_gremlin(question, llm_client)` - NL to Gremlin
  - `format_graph_response(gremlin_results, llm_client)` - Results to NL
  - `suggest_follow_up_questions(context, llm_client)`
- **Dependencies:** 3.2
- **GitHub Copilot Compatibility:** ✅ LLM integration
- **Recommended LLM Agent:** **YES - REQUIRED**
  - Azure OpenAI GPT-4 for query translation
  - Semantic Kernel or LangChain for orchestration
  - Vector embeddings for query understanding

#### 5.2 Risk Explanation Generator
- **Status:** NOT STARTED
- **Script:** `scripts/510_risk_explainer.py`
- **Description:**
  - Generate natural language explanations for identified risks
  - Provide context about why a change is risky
  - Include relevant graph paths and relationships
- **Key Functions:**
  - `explain_risk(risk_item, graph_client, llm_client)`
  - `generate_impact_narrative(blast_radius, llm_client)`
  - `create_visual_explanation(resource_id, changes)` - Mermaid diagrams
- **Dependencies:** 4.1, 5.1
- **GitHub Copilot Compatibility:** ✅ LLM integration
- **Recommended LLM Agent:** **YES - REQUIRED**
  - Use GPT-4 for generating clear explanations
  - Template-based prompts with graph context

#### 5.3 Mitigation Recommendation Engine
- **Status:** NOT STARTED
- **Script:** `scripts/520_mitigation_recommender.py`
- **Description:**
  - Generate recommendations to mitigate identified risks
  - Suggest alternative approaches or safeguards
  - Provide ARM template snippets for fixes
- **Key Functions:**
  - `recommend_mitigations(risk_item, graph_client, llm_client)`
  - `generate_alternative_design(risky_changes, llm_client)`
  - `create_remediation_template(risk_item)` - ARM template fixes
- **Dependencies:** 5.2
- **GitHub Copilot Compatibility:** ✅ LLM integration
- **Recommended LLM Agent:** **YES - REQUIRED**
  - Use GPT-4 with Azure architecture best practices
  - RAG approach with Azure Well-Architected Framework
  - Code generation for ARM template fixes

---

### Phase 6: Reporting and Integration 🔄
**Goal:** Create actionable reports and integrate with CI/CD

#### 6.1 Risk Report Generator
- **Status:** NOT STARTED
- **Script:** `scripts/600_report_generator.py`
- **Description:**
  - Generate comprehensive risk assessment reports
  - Support multiple formats (JSON, HTML, Markdown, PDF)
  - Include visualizations (graphs, charts)
- **Output Formats:**
  - JSON: Machine-readable for CI/CD integration
  - Markdown: For GitHub PR comments
  - HTML: Interactive dashboard
- **Key Functions:**
  - `generate_risk_report(comparison_results, output_format)`
  - `create_summary_dashboard(risks)`
  - `export_to_format(report_data, format)`
- **Dependencies:** 4.1, 4.2, 4.3, 5.2, 5.3
- **GitHub Copilot Compatibility:** ✅ Report generation
- **Recommended LLM Agent:** **OPTIONAL**
  - Use LLM to generate executive summaries
  - Create human-friendly report narratives

#### 6.2 CI/CD Integration
- **Status:** NOT STARTED
- **Script:** `scripts/610_cicd_integration.py`
- **Description:**
  - Create GitHub Actions workflow for automated risk analysis
  - Integrate with PR validation process
  - Post risk assessment as PR comment
- **Files:**
  - `.github/workflows/iac-risk-check.yml` - GitHub Actions workflow
  - `scripts/610_cicd_integration.py` - CLI wrapper
- **Key Functions:**
  - `analyze_pr_changes(pr_number, repo_path)`
  - `post_pr_comment(pr_number, risk_report)`
  - `set_status_check(pr_number, risk_level)` - Pass/fail based on threshold
- **Dependencies:** 6.1
- **GitHub Copilot Compatibility:** ✅ CI/CD development
- **Recommended LLM Agent:** None needed

---

## Configuration Files

### Required Configuration Files

| File | Purpose | Status |
|------|---------|--------|
| `config/relationship-config.yaml` | Resource relationship rules | ✅ EXISTS |
| `config/risk-scoring-rules.yaml` | Risk scoring configuration | 🔄 TO CREATE |
| `config/risky-patterns.yaml` | Known risky patterns | 🔄 TO CREATE |
| `config/llm-config.yaml` | LLM integration settings | 🔄 TO CREATE |
| `.github/workflows/iac-risk-check.yml` | CI/CD workflow | 🔄 TO CREATE |

---

## LLM Agent Requirements

### Required Agents

1. **Risk Analysis Agent** (Phase 4.1, 4.2)
   - **Purpose:** Analyze complex change patterns and identify risks
   - **Model:** Azure OpenAI GPT-4 or GPT-4 Turbo
   - **Integration:** Direct API calls with structured prompts
   - **Context:** Graph query results, change diffs, security best practices

2. **Query Translation Agent** (Phase 5.1)
   - **Purpose:** Convert natural language to Gremlin queries
   - **Model:** Azure OpenAI GPT-4
   - **Integration:** Semantic Kernel or LangChain
   - **Context:** Graph schema, example queries, user intent

3. **Explanation Agent** (Phase 5.2)
   - **Purpose:** Generate human-readable risk explanations
   - **Model:** Azure OpenAI GPT-4
   - **Integration:** Template-based prompts
   - **Context:** Risk data, graph relationships, blast radius

4. **Recommendation Agent** (Phase 5.3)
   - **Purpose:** Suggest mitigations and generate ARM template fixes
   - **Model:** Azure OpenAI GPT-4
   - **Integration:** RAG with Azure Well-Architected Framework
   - **Context:** Risk details, Azure best practices, existing templates

### Optional Agents

5. **Report Narrative Agent** (Phase 6.1)
   - **Purpose:** Generate executive summaries and report narratives
   - **Model:** Azure OpenAI GPT-3.5-Turbo (cost-effective)
   - **Integration:** Simple prompt-based generation
   - **Context:** Aggregated risk data

---

## Development Approach

### GitHub Copilot Vibe Coding Compatibility

All phases are designed for compatibility with GitHub Copilot agent:

✅ **Compatible Tasks:**
- Python script development (Phases 2-6)
- Gremlin query writing (Phase 3)
- Configuration file creation (All phases)
- CI/CD workflow creation (Phase 6.2)
- Unit test generation (All phases)

⚠️ **Requires LLM Integration:**
- Natural language query translation (Phase 5.1)
- Risk explanation generation (Phase 5.2)
- Mitigation recommendations (Phase 5.3)

### Recommended Development Order

1. **Week 1-2:** Phase 2 (ARM Template Ingestion)
2. **Week 3-4:** Phase 3 (Comparison Engine)
3. **Week 5-6:** Phase 4 (Risk Scoring - without LLM)
4. **Week 7-8:** Phase 5 (LLM Integration)
5. **Week 9-10:** Phase 6 (Reporting & CI/CD)

---

## Success Criteria

### Phase Completion Checklist

- [ ] **Phase 1:** ✅ Infrastructure provisioned, Azure resources ingested
- [ ] **Phase 2:** ARM templates parsed and ingested with "PROPOSED_" prefix
- [ ] **Phase 3:** Comparison engine identifies additions/deletions/modifications
- [ ] **Phase 4:** Risk scores calculated with configurable rules
- [ ] **Phase 5:** Natural language queries return accurate results
- [ ] **Phase 6:** Automated reports generated, CI/CD integrated

### Quality Gates

- [ ] Unit tests for all Python modules (>80% coverage)
- [ ] Integration tests for graph operations
- [ ] LLM response validation tests
- [ ] CI/CD pipeline runs successfully on sample ARM templates
- [ ] Documentation complete for all scripts and configurations

---

## Dependencies and Prerequisites

### Technical Dependencies

- **Existing:** ✅
  - Azure subscription with Cosmos DB Gremlin API
  - Python 3.8+ environment
  - Azure CLI authentication
  
- **To Add:** 🔄
  - Azure OpenAI service instance
  - Python libraries: `semantic-kernel`, `langchain`, `openai`
  - ARM template test samples
  - Unit testing framework (pytest)

### Team Skills Required

- Python development ✅
- Graph database concepts (Gremlin) ✅
- ARM template knowledge 🔄
- LLM prompt engineering 🔄
- CI/CD pipeline development 🔄

---

## Risk and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| ARM template parsing complexity | High | Use Azure SDK libraries, extensive testing |
| LLM costs for frequent queries | Medium | Cache results, use GPT-3.5 where possible |
| Graph query performance at scale | High | Implement pagination, optimize Gremlin queries |
| False positives in risk detection | Medium | Tunable thresholds, human review workflow |

---

## Notes for Implementation

- **Ignore Cypher:** All graph queries use Gremlin (Azure Cosmos DB Gremlin API), not Cypher
- **Existing Scripts:** Leverage `100_ingest_azure_to_graph.py` patterns for ARM ingestion
- **Configuration-Driven:** All rules defined in YAML for easy customization
- **Incremental Development:** Each phase builds on previous, can be developed independently
- **Testing Strategy:** Create test ARM templates for each scenario (additions, deletions, modifications)

---
