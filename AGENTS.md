# Agent Instructions

This project uses **bd** (Beads) for issue tracking. Run `bd onboard` to get started.

You have access to the following MCP servers:

- **beads** (Beads issue tracker)
   - Use the MCP tools with prefix `mcp_beads_*` (e.g., `mcp_beads_ready`, `mcp_beads_show`, `mcp_beads_update`, `mcp_beads_close`).
   - Before any Beads write operation (create/update/close/dep), call:
      - `mcp_beads_context(action='set', workspace_root='/Users/anuj/002-GitHub/iac-risk-scoring')`
  
- **neo4j-database** (Neo4j MCP server for risk advisor)
  - This MCP server allows to extract the graph database scheme to give the agent-LLM to generated Cypher queries to query and update the database.
  - You can use the following MCP Tools: `get-neo4j-schema`, `read-neo4j-cypher`, `write-neo4j-cypher`

- **risk-scoring** (Risk Scoring MCP server)
  - Primary interface for AI agents to assess operational risk for Azure resource changes
  - Tool: `mcp_risk_scoring_assess_resource(resource_id: str, environment: str) -> JSON`
  - Returns deterministic risk score (0-100) with evidence-based factors, blast radius, and recommendations
  - Same engine as CLI and FastAPI interfaces - ensures consistent results
  - **Usage**:
    ```python
    # Agent invokes MCP tool
    result = mcp_risk_scoring_assess_resource(
        resource_id="res-alpha-app",
        environment="prod"  # prod|staging|dev|test
    )
    
    # Returns JSON with risk_score, factors, evidence, recommendations
    # Agent formats JSON as user-friendly markdown
    ```
  - **Agent workflow**: User asks → Agent calls MCP tool → Gets JSON → Formats markdown → User sees report
  - See `.github/agents/risk-assessment.agent.md` for full agent instructions

## User interaction patters

The user will interact in one of the following manners:

1. **Generic queries**: User asks generic queries about the repo/code. You can answer those as a normal conversation.
2. **Planning related**: User wants to brainstorm some ideas and create a plan for the implementation. For this, use the `beads` MCP tools to create/update/delete beads tasks. Ask before implementing anything.
3. **Implementation related**: User wants to implement certain beads tasks. Please feel free to use any tools as required. 

## Working Agreement (Beads-First)

Beads issues are the source of truth. Before implementation starts, the issue should include:

- Goal/context and scope/non-goals
- Acceptance criteria (testable)
- Likely files to touch
- Validation commands to run
- Dependencies (use Beads deps so `bd ready` is accurate)

## Landing the Plane (Session Completion)

**When the user says "let's land the plane"**, follow this clean session-ending protocol:

1. **File beads issues for any remaining work** that needs follow-ups
2. **Ensure all quality gates pass** (only if code change were made) - run tests, linters, builds as applicable. File P0 issues for any failures.
3. **Update Beads issues** - close finished work, update status
4. **Sync the isseu tracker carefully**: Work methodically to ensure both local and remote issues merge safely. This may require pulling, handling conflicts (sometimes accepting remote changes and re-importing), syncing the database, and verifying consistency. Be creative and patient - the goal is clean reconciliation where no issues are lost.
5. **Clean the git state**: - Clear old stashes and prune deap remote branches:

   ```bash
   git stash clear         # Remove old stashes
   git remote prune origin # Clean up deleted remote branches
   ```

6. **Verify clean state**: Ensure all changes are committed and pushed, no untracked files remain.
7. **Choose a follow-up issue for next session**
   - Provide a prompt for the user to give you in the next session.
   - Format: [Continue work on <issue id>: <short description>] [Brief context about what's been done and what's next]"

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
