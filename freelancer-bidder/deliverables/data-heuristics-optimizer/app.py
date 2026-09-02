"""
Simple web demo for Optimize Data Heuristics.
Run: uvicorn app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from heuristics.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

app = FastAPI(title="Data Heuristics Optimizer Demo")


def _run_and_save(horizon_days: int = 14) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    unified, decisions, metrics = run_pipeline(DATA_DIR, horizon_days=horizon_days, validate=True)
    unified.to_csv(OUT_DIR / "unified_dataset.csv", index=False)
    decisions.to_csv(OUT_DIR / "decisions.csv", index=False)
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return {
        "metrics": metrics,
        "decisions": json.loads(decisions.round(3).to_json(orient="records")),
        "unified_preview": json.loads(unified.head(20).round(3).to_json(orient="records")),
    }


@app.get("/api/run")
def api_run(horizon: int = 14):
    try:
        return _run_and_save(horizon_days=horizon)
    except Exception as exc:  # noqa: BLE001 — surface demo errors to UI
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/metrics")
def api_metrics():
    path = OUT_DIR / "metrics.json"
    if not path.exists():
        return _run_and_save()["metrics"]
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Data Heuristics Optimizer — Demo</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --text: #e7eef8;
      --muted: #8b9bb4;
      --accent: #3d9cfd;
      --ok: #3ecf8e;
      --warn: #f5a524;
      --line: #2a3648;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1b2a44, transparent), var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 28px 20px 60px; }
    h1 { margin: 0 0 6px; font-size: 1.6rem; letter-spacing: -0.02em; }
    .sub { color: var(--muted); margin-bottom: 22px; line-height: 1.45; }
    .row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
    }
    .card .label { color: var(--muted); font-size: 0.8rem; margin-bottom: 6px; }
    .card .value { font-size: 1.35rem; font-weight: 650; }
    .card .value.ok { color: var(--ok); }
    .actions { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
    button {
      background: var(--accent);
      color: #061018;
      border: 0;
      border-radius: 8px;
      padding: 10px 16px;
      font-weight: 650;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .hint { color: var(--muted); font-size: 0.9rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px 8px; text-align: left; white-space: nowrap; }
    th { color: var(--muted); font-weight: 600; }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 650;
      background: #243247;
    }
    .pill.po { background: #3a2612; color: #ffc36a; }
    .pill.tr { background: #123528; color: #6ee7b7; }
    .pill.ok { background: #1c2a3d; color: #9ec1ef; }
    .err { color: #ff8e8e; margin: 10px 0; }
    @media (max-width: 800px) { .row { grid-template-columns: 1fr 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Data Heuristics Optimizer</h1>
    <p class="sub">
      Multi-CSV demo: inventory + demand + costs + constraints → unified frame → PO / transfer recommendations.
      Sample data is included; swap CSVs under <code>data/</code> for real client files.
    </p>

    <div class="actions">
      <button id="runBtn" onclick="runDemo()">Run heuristics demo</button>
      <span class="hint" id="status">Loading…</span>
    </div>
    <div class="err" id="err"></div>

    <div class="row" id="metrics"></div>

    <div class="card">
      <div class="label" style="margin-bottom:10px">Recommended actions</div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>SKU</th><th>WH</th><th>Avail</th><th>Demand 14d</th>
              <th>Cover (d)</th><th>PO qty</th><th>Transfer</th><th>Action</th><th>Priority</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </div>
  </div>
  <script>
    function pct(v) { return (Number(v) * 100).toFixed(2) + '%'; }
    function n(v) { return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
    function pill(action) {
      const cls = action === 'PURCHASE_ORDER' ? 'po' : action === 'TRANSFER_IN' ? 'tr' : 'ok';
      return `<span class="pill ${cls}">${action}</span>`;
    }
    function render(data) {
      const m = data.metrics;
      document.getElementById('metrics').innerHTML = `
        <div class="card"><div class="label">Service level</div><div class="value ok">${pct(m.projected_service_level)}</div></div>
        <div class="card"><div class="label">SKUs / Warehouses</div><div class="value">${m.skus} / ${m.warehouses}</div></div>
        <div class="card"><div class="label">PO units</div><div class="value">${n(m.po_units)}</div></div>
        <div class="card"><div class="label">Expected cost</div><div class="value">${n(m.expected_total_cost)}</div></div>
      `;
      const rows = data.decisions || [];
      document.getElementById('tbody').innerHTML = rows.map(r => `
        <tr>
          <td>${r.sku}</td>
          <td>${r.warehouse}</td>
          <td>${n(r.available)}</td>
          <td>${n(r.local_demand_14d)}</td>
          <td>${n(r.days_of_cover)}</td>
          <td>${n(r.po_qty)}</td>
          <td>${n(r.transfer_in)}${r.transfer_from ? ' ← ' + r.transfer_from : ''}</td>
          <td>${pill(r.action)}</td>
          <td>${r.priority_mode}</td>
        </tr>
      `).join('');
      document.getElementById('status').textContent =
        `OK · ${m.rows} rows · actions: PO ${m.actions.PURCHASE_ORDER || 0}, transfer ${m.actions.TRANSFER_IN || 0}, OK ${m.actions.OK || 0}`;
    }
    async function runDemo() {
      const btn = document.getElementById('runBtn');
      const err = document.getElementById('err');
      err.textContent = '';
      btn.disabled = true;
      document.getElementById('status').textContent = 'Running pipeline…';
      try {
        const res = await fetch('/api/run');
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Run failed');
        render(data);
      } catch (e) {
        err.textContent = e.message || String(e);
        document.getElementById('status').textContent = 'Failed';
      } finally {
        btn.disabled = false;
      }
    }
    runDemo();
  </script>
</body>
</html>
"""
