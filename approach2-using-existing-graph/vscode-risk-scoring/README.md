# IaC Risk Scoring (Approach 2) — VS Code Extension

This is a minimal VS Code extension that adds a user-triggered command:

- `Risk: Assess Infrastructure Change`

MVP behavior:
- Captures a deterministic `git diff` (scoped to workspace/file/folder)
- Runs deterministic canonicalization
- Opens the resulting canonical change JSON in an editor

## Run locally (Extension Development Host)

From the repo root:

```bash
cd approach2-using-existing-graph/vscode-risk-scoring
npm install
npm run compile
```

Then in VS Code:
- Run the `Run Extension` launch config (F5)
- In the Extension Development Host, open this repo
- Run Command Palette → `Risk: Assess Infrastructure Change`

## Notes

- The extension calls the Python entrypoint at `approach2-using-existing-graph/risk_scoring/vscode_entrypoint.py`.
- It prefers using the repo’s `.venv/bin/python` if present; otherwise falls back to `python3`.
- No background/automatic scoring is performed; everything is user-triggered.
