import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';
import { spawn } from 'child_process';
import * as vscode from 'vscode';

type RiskReport = {
  schema_version?: string;
  report_id?: string | null;
  resource?: { label?: string; resource_id?: string };
  score?: {
    risk_model_version?: string;
    risk_score?: number;
    risk_level?: string;
    factors?: Array<{
      factor_id?: string;
      title?: string;
      status?: string;
      points?: number;
      max_points?: number;
      reason?: string;
      evidence?: unknown;
    }>;
  };
  evidence?: unknown;
  evidence_queries?: Array<{
    query_id?: string;
    row_count?: number;
    params?: unknown;
    sample_rows?: unknown;
  }>;
  unknowns?: string[];
};

function findPython(workspaceRoot: string): string {
  const candidates = [
    path.join(workspaceRoot, '.venv', 'bin', 'python'),
    path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  return 'python3';
}

function getWorkspaceRoot(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    throw new Error('No workspace folder is open.');
  }
  return folders[0].uri.fsPath;
}

function loadDotEnvVars(workspaceRoot: string): Record<string, string> {
  const envPath = path.join(workspaceRoot, '.env');
  if (!fs.existsSync(envPath)) {
    return {};
  }

  const out: Record<string, string> = {};
  const text = fs.readFileSync(envPath, { encoding: 'utf8' });

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const idx = line.indexOf('=');
    if (idx <= 0) {
      continue;
    }

    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();

    if (!key) {
      continue;
    }

    // Support simple quoted values: KEY="value" or KEY='value'
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    out[key] = value;
  }

  return out;
}

function getPythonProcessEnv(workspaceRoot: string): NodeJS.ProcessEnv {
  return {
    ...process.env,
    ...loadDotEnvVars(workspaceRoot),
  };
}

async function pickScope(uriFromContext?: vscode.Uri): Promise<{ paths: string[]; label: string }> {
  if (uriFromContext) {
    const stat = await vscode.workspace.fs.stat(uriFromContext);
    if (stat.type === vscode.FileType.Directory) {
      return { paths: [uriFromContext.fsPath], label: 'Folder' };
    }
    return { paths: [uriFromContext.fsPath], label: 'File' };
  }

  const picked = await vscode.window.showQuickPick(
    [
      { label: 'Workspace', description: 'Use all changes in the workspace' },
      { label: 'File', description: 'Use the currently active file' },
      { label: 'Folder', description: 'Pick a folder to scope the diff' },
    ],
    { placeHolder: 'Assess risk scope' }
  );

  if (!picked) {
    throw new Error('Cancelled.');
  }

  if (picked.label === 'Workspace') {
    return { paths: [], label: 'Workspace' };
  }

  if (picked.label === 'File') {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      throw new Error('No active editor to scope to a file.');
    }
    return { paths: [editor.document.uri.fsPath], label: 'File' };
  }

  const selected = await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: 'Select folder to assess',
  });

  if (!selected || selected.length === 0) {
    throw new Error('Cancelled.');
  }

  return { paths: [selected[0].fsPath], label: 'Folder' };
}

async function pickEnvironment(): Promise<string | undefined> {
  const picked = await vscode.window.showQuickPick(
    [
      { label: '(unknown)', description: 'Do not set environment (explicit unknown)' },
      { label: 'prod' },
      { label: 'staging' },
      { label: 'dev' },
      { label: 'test' },
    ],
    { placeHolder: 'Optional: environment for canonical model' }
  );

  if (!picked || picked.label === '(unknown)') {
    return undefined;
  }
  return picked.label;
}

async function runCanonicalization(workspaceRoot: string, baseRef: string, paths: string[], environment?: string): Promise<string> {
  const python = findPython(workspaceRoot);
  const entrypoint = path.join(workspaceRoot, 'approach2-using-existing-graph', 'risk_scoring', 'vscode_entrypoint.py');

  const args: string[] = [entrypoint, '--repo-dir', workspaceRoot, '--base-ref', baseRef];
  for (const p of paths) {
    const rel = path.relative(workspaceRoot, p).replace(/\\/g, '/');
    args.push('--path', rel);
  }
  if (environment) {
    args.push('--environment', environment);
  }

  return await new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: workspaceRoot, env: getPythonProcessEnv(workspaceRoot) });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (d: Buffer) => (stdout += d.toString()));
    child.stderr.on('data', (d: Buffer) => (stderr += d.toString()));

    child.on('error', (err: Error) => reject(err));
    child.on('close', (code: number | null) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(stderr || `Python exited with code ${code}`));
      }
    });
  });
}

async function runMarkdownRender(workspaceRoot: string, reportJsonText: string): Promise<string> {
  const python = findPython(workspaceRoot);
  const renderer = path.join(workspaceRoot, 'approach2-using-existing-graph', 'risk_scoring', 'vscode_render_report.py');

  const args: string[] = [renderer, '--input', '-'];

  return await new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: workspaceRoot, env: getPythonProcessEnv(workspaceRoot) });

    let stdout = '';
    let stderr = '';

    child.stdin.write(reportJsonText);
    child.stdin.end();

    child.stdout.on('data', (d: Buffer) => (stdout += d.toString()));
    child.stderr.on('data', (d: Buffer) => (stderr += d.toString()));

    child.on('error', (err: Error) => reject(err));
    child.on('close', (code: number | null) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(stderr || `Python exited with code ${code}`));
      }
    });
  });
}

async function runScoring(
  workspaceRoot: string,
  canonicalJsonText: string,
  resourceIdOverride?: string,
  resourceTypeOverride?: string
): Promise<string> {
  const python = findPython(workspaceRoot);
  const scorer = path.join(workspaceRoot, 'approach2-using-existing-graph', 'risk_scoring', 'vscode_score_entrypoint.py');

  const args: string[] = [scorer, '--input', '-'];
  if (resourceIdOverride) {
    args.push('--resource-id', resourceIdOverride);
  }
  if (resourceTypeOverride) {
    args.push('--resource-type', resourceTypeOverride);
  }

  return await new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: workspaceRoot, env: getPythonProcessEnv(workspaceRoot) });

    let stdout = '';
    let stderr = '';

    child.stdin.write(canonicalJsonText);
    child.stdin.end();

    child.stdout.on('data', (d: Buffer) => (stdout += d.toString()));
    child.stderr.on('data', (d: Buffer) => (stderr += d.toString()));

    child.on('error', (err: Error) => reject(err));
    child.on('close', (code: number | null) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(stderr || `Python exited with code ${code}`));
      }
    });
  });
}

function safeJsonStringify(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function stableStringify(value: any): string {
  const normalize = (v: any): any => {
    if (v === null || v === undefined) {
      return v;
    }
    if (Array.isArray(v)) {
      return v.map(normalize);
    }
    if (typeof v === 'object') {
      const out: any = {};
      for (const key of Object.keys(v).sort()) {
        out[key] = normalize(v[key]);
      }
      return out;
    }
    return v;
  };

  return JSON.stringify(normalize(value));
}

function extractResourceIdFromCanonical(canonical: any): string | undefined {
  const ops = canonical?.operations;
  if (!Array.isArray(ops)) {
    return undefined;
  }
  for (const op of ops) {
    const rid = op?.resource_id ?? op?.resourceId;
    if (typeof rid === 'string' && rid.trim()) {
      return rid.trim();
    }
  }
  return undefined;
}

function extractResourceTypeFromCanonical(canonical: any): string | undefined {
  const ops = canonical?.operations;
  if (!Array.isArray(ops)) {
    return undefined;
  }
  for (const op of ops) {
    const rt = op?.resource_type ?? op?.resourceType;
    if (typeof rt === 'string' && rt.trim()) {
      return rt.trim();
    }
  }
  return undefined;
}

function extractChangeIdFromCanonical(canonical: any): string | undefined {
  const cid = canonical?.change_id ?? canonical?.changeId;
  return typeof cid === 'string' && cid.trim() ? cid.trim() : undefined;
}

function sanitizeForFilename(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, '_');
}

function isRiskReportV1(obj: any): obj is RiskReport {
  return obj && typeof obj === 'object' && obj.schema_version === 'risk_report.v1';
}

function getActiveEditorText(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return undefined;
  }
  return editor.document.getText();
}

async function readReportJsonText(uri?: vscode.Uri): Promise<string> {
  if (uri) {
    const bytes = await vscode.workspace.fs.readFile(uri);
    return Buffer.from(bytes).toString('utf8');
  }
  const text = getActiveEditorText();
  if (!text) {
    throw new Error('Open a risk report JSON file, or run the command from a JSON file context menu.');
  }
  return text;
}

function renderReportHtml(report: RiskReport, reportJsonPretty: string): string {
  const score = report.score || {};
  const resource = report.resource || {};
  const factors = score.factors || [];
  const unknowns = report.unknowns || [];
  const evidenceQueries = report.evidence_queries || [];

  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const factorRows = factors
    .map((f) => {
      const pts = `${f.points ?? ''} / ${f.max_points ?? ''}`;
      return `
        <tr>
          <td><code>${escapeHtml(String(f.factor_id ?? ''))}</code></td>
          <td>${escapeHtml(String(f.title ?? ''))}</td>
          <td><code>${escapeHtml(String(f.status ?? ''))}</code></td>
          <td>${escapeHtml(pts)}</td>
          <td>${escapeHtml(String(f.reason ?? ''))}</td>
        </tr>
      `;
    })
    .join('');

  const queryBlocks = evidenceQueries
    .map((q) => {
      const qid = String(q.query_id ?? '');
      const rowCount = q.row_count ?? '';
      const params = escapeHtml(safeJsonStringify(q.params ?? {}));
      const sample = escapeHtml(safeJsonStringify(q.sample_rows ?? []));
      return `
        <details>
          <summary><code>${escapeHtml(qid)}</code> — rows: ${escapeHtml(String(rowCount))}</summary>
          <h4>Params</h4>
          <pre><code>${params}</code></pre>
          <h4>Sample Rows</h4>
          <pre><code>${sample}</code></pre>
        </details>
      `;
    })
    .join('');

  const evidenceJson = escapeHtml(safeJsonStringify(report.evidence ?? {}));
  const unknownList = unknowns.length ? unknowns.map((u) => `<li><code>${escapeHtml(u)}</code></li>`).join('') : '<li>(none)</li>';

  return `
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 16px; }
      .summary { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .card { border: 1px solid rgba(127,127,127,0.25); border-radius: 8px; padding: 12px; }
      code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border-bottom: 1px solid rgba(127,127,127,0.25); padding: 6px 8px; vertical-align: top; }
      th { text-align: left; }
      pre { background: rgba(127,127,127,0.12); padding: 8px; border-radius: 6px; overflow: auto; }
      .actions { display: flex; gap: 8px; margin: 12px 0; }
      button { padding: 6px 10px; }
      details { margin: 8px 0; }
    </style>
  </head>
  <body>
    <h2>IaC Risk Report</h2>
    <div class="summary">
      <div class="card">
        <h3>Summary</h3>
        <div><b>schema_version</b>: <code>${escapeHtml(String(report.schema_version ?? ''))}</code></div>
        <div><b>risk_model_version</b>: <code>${escapeHtml(String(score.risk_model_version ?? ''))}</code></div>
        <div><b>risk_score</b>: <code>${escapeHtml(String(score.risk_score ?? ''))}</code></div>
        <div><b>risk_level</b>: <code>${escapeHtml(String(score.risk_level ?? ''))}</code></div>
      </div>
      <div class="card">
        <h3>Resource</h3>
        <div><b>label</b>: <code>${escapeHtml(String(resource.label ?? ''))}</code></div>
        <div><b>resource_id</b>: <code>${escapeHtml(String(resource.resource_id ?? ''))}</code></div>
      </div>
    </div>

    <div class="actions">
      <button onclick="copyJson()">Copy JSON</button>
      <button onclick="exportJson()">Export JSON</button>
      <button onclick="openMarkdown()">Open Markdown</button>
    </div>

    <h3>Factors</h3>
    <table>
      <thead>
        <tr>
          <th>Factor</th>
          <th>Title</th>
          <th>Status</th>
          <th>Points</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        ${factorRows}
      </tbody>
    </table>

    <h3>Evidence</h3>
    <pre><code>${evidenceJson}</code></pre>

    <h3>Evidence Queries</h3>
    ${queryBlocks || '<div>(none)</div>'}

    <h3>Unknowns</h3>
    <ul>${unknownList}</ul>

    <script>
      const vscode = acquireVsCodeApi();
      const reportJson = ${JSON.stringify(reportJsonPretty)};

      function copyJson() {
        vscode.postMessage({ type: 'copyJson', json: reportJson });
      }
      function exportJson() {
        vscode.postMessage({ type: 'exportJson', json: reportJson });
      }
      function openMarkdown() {
        vscode.postMessage({ type: 'openMarkdown', json: reportJson });
      }
    </script>
  </body>
</html>
  `;
}

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand(
    'iacRiskScoring.assessInfrastructureChange',
    async (uri?: vscode.Uri) => {
      try {
        const workspaceRoot = getWorkspaceRoot();
        const { paths, label } = await pickScope(uri);

        const baseRef = (await vscode.window.showInputBox({
          prompt: 'Base ref for diff (default: HEAD)',
          value: 'HEAD',
        })) || 'HEAD';

        const environment = await pickEnvironment();

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: `Risk: canonicalize + score (${label})`,
            cancellable: false,
          },
          async () => {
            const canonicalJsonText = await runCanonicalization(workspaceRoot, baseRef, paths, environment);

            let canonical: any;
            try {
              canonical = JSON.parse(canonicalJsonText);
            } catch {
              throw new Error('Canonicalization output is not valid JSON.');
            }

            const changeId = extractChangeIdFromCanonical(canonical) || 'unknown-change-id';
            const resourceIdInModel = extractResourceIdFromCanonical(canonical);
            const resourceTypeInModel = extractResourceTypeFromCanonical(canonical);

            let resourceIdOverride: string | undefined;
            if (!resourceIdInModel) {
              resourceIdOverride = await vscode.window.showInputBox({
                prompt: 'Resource id to score (required if canonical model lacks resource_id)',
                placeHolder: 'e.g. res-delta-k8s',
              });
              if (!resourceIdOverride) {
                throw new Error('Cancelled.');
              }
            }

            const reportJsonText = await runScoring(
              workspaceRoot,
              canonicalJsonText,
              resourceIdOverride,
              resourceTypeInModel
            );

            let reportObj: any;
            try {
              reportObj = JSON.parse(reportJsonText);
            } catch {
              throw new Error('Scoring output is not valid JSON.');
            }

            if (!isRiskReportV1(reportObj)) {
              throw new Error("Scoring output is not a supported risk report (expected schema_version='risk_report.v1').");
            }

            // Persist report for audit/CI parity.
            const safeId = sanitizeForFilename(changeId);
            const outDir = path.join(workspaceRoot, '.risk-scoring', 'reports');
            await fs.promises.mkdir(outDir, { recursive: true });
            const reportPath = path.join(outDir, `${safeId}.risk_report.json`);
            await fs.promises.writeFile(reportPath, reportJsonText, { encoding: 'utf8' });

            const pretty = JSON.stringify(reportObj, null, 2);
            const panel = vscode.window.createWebviewPanel(
              'iacRiskScoring.report',
              'IaC Risk Report',
              vscode.ViewColumn.Beside,
              { enableScripts: true }
            );

            panel.webview.html = renderReportHtml(reportObj, pretty);

            panel.webview.onDidReceiveMessage(
              async (msg) => {
                if (msg?.type === 'copyJson') {
                  await vscode.env.clipboard.writeText(String(msg.json || ''));
                  vscode.window.showInformationMessage('Risk report JSON copied to clipboard.');
                  return;
                }

                if (msg?.type === 'exportJson') {
                  const uri = await vscode.window.showSaveDialog({
                    filters: { 'JSON': ['json'] },
                    saveLabel: 'Save Risk Report JSON',
                  });
                  if (!uri) {
                    return;
                  }
                  await vscode.workspace.fs.writeFile(uri, Buffer.from(String(msg.json || ''), 'utf8'));
                  vscode.window.showInformationMessage(`Saved: ${uri.fsPath}`);
                  return;
                }

                if (msg?.type === 'openMarkdown') {
                  const md = await runMarkdownRender(workspaceRoot, String(msg.json || ''));
                  const doc = await vscode.workspace.openTextDocument({ language: 'markdown', content: md });
                  await vscode.window.showTextDocument(doc, { preview: false });
                  return;
                }
              },
              undefined,
              context.subscriptions
            );

            const action = await vscode.window.showInformationMessage(
              `Risk report generated (${path.relative(workspaceRoot, reportPath)}).`,
              'Capture Decision',
              'Dismiss'
            );

            if (action === 'Capture Decision') {
              const decisionPicked = await vscode.window.showQuickPick(
                [
                  { label: 'proceed', description: 'Proceed with change' },
                  { label: 'proceed_with_mitigation', description: 'Proceed, but with mitigations' },
                  { label: 'defer', description: 'Defer change' },
                ],
                { placeHolder: 'Decision (audit trail)' }
              );
              if (!decisionPicked) {
                return;
              }

              const record = {
                schema_version: 'risk_decision.v1',
                timestamp: new Date().toISOString(),
                user: {
                  username: os.userInfo().username,
                  machine_id: vscode.env.machineId,
                  session_id: vscode.env.sessionId,
                },
                change_id: changeId,
                report_path: path.relative(workspaceRoot, reportPath).replace(/\\/g, '/'),
                risk: {
                  risk_model_version: reportObj?.score?.risk_model_version,
                  risk_score: reportObj?.score?.risk_score,
                  risk_level: reportObj?.score?.risk_level,
                },
                decision: decisionPicked.label,
              };

              const auditDir = path.join(workspaceRoot, '.risk-scoring');
              await fs.promises.mkdir(auditDir, { recursive: true });
              const auditPath = path.join(auditDir, 'audit.jsonl');
              await fs.promises.appendFile(auditPath, stableStringify(record) + '\n', { encoding: 'utf8' });

              vscode.window.showInformationMessage(`Decision recorded: ${decisionPicked.label}`);
            }
          }
        );
      } catch (e: any) {
        const msg = e?.message || String(e);
        vscode.window.showErrorMessage(`Risk assessment failed: ${msg}`);
      }
    }
  );

  context.subscriptions.push(disposable);

  const renderDisposable = vscode.commands.registerCommand(
    'iacRiskScoring.renderRiskReport',
    async (uri?: vscode.Uri) => {
      try {
        const workspaceRoot = getWorkspaceRoot();
        const jsonText = await readReportJsonText(uri);

        let parsed: any;
        try {
          parsed = JSON.parse(jsonText);
        } catch {
          throw new Error('Selected content is not valid JSON.');
        }

        if (!isRiskReportV1(parsed)) {
          throw new Error("JSON is not a supported risk report (expected schema_version='risk_report.v1').");
        }

        const pretty = JSON.stringify(parsed, null, 2);
        const panel = vscode.window.createWebviewPanel(
          'iacRiskScoring.report',
          'IaC Risk Report',
          vscode.ViewColumn.Beside,
          { enableScripts: true }
        );

        panel.webview.html = renderReportHtml(parsed, pretty);

        panel.webview.onDidReceiveMessage(
          async (msg) => {
            if (msg?.type === 'copyJson') {
              await vscode.env.clipboard.writeText(String(msg.json || ''));
              vscode.window.showInformationMessage('Risk report JSON copied to clipboard.');
              return;
            }

            if (msg?.type === 'exportJson') {
              const uri = await vscode.window.showSaveDialog({
                filters: { 'JSON': ['json'] },
                saveLabel: 'Save Risk Report JSON',
              });
              if (!uri) {
                return;
              }
              await vscode.workspace.fs.writeFile(uri, Buffer.from(String(msg.json || ''), 'utf8'));
              vscode.window.showInformationMessage(`Saved: ${uri.fsPath}`);
              return;
            }

            if (msg?.type === 'openMarkdown') {
              const md = await runMarkdownRender(workspaceRoot, String(msg.json || ''));
              const doc = await vscode.workspace.openTextDocument({ language: 'markdown', content: md });
              await vscode.window.showTextDocument(doc, { preview: false });
              return;
            }
          },
          undefined,
          context.subscriptions
        );
      } catch (e: any) {
        const msg = e?.message || String(e);
        vscode.window.showErrorMessage(`Risk report rendering failed: ${msg}`);
      }
    }
  );

  context.subscriptions.push(renderDisposable);
}

export function deactivate() {}
