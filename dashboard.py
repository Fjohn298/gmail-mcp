import os
import csv
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template_string, session, redirect
from gmail_logger import setup_logger
from gmail_auth import api_call_with_retry

_TZ = ZoneInfo('America/El_Salvador')

app = Flask(__name__)

_logger = setup_logger('dashboard')
app.logger.handlers = _logger.handlers
app.logger.setLevel(logging.INFO)
app.logger.propagate = False

_wz = logging.getLogger('werkzeug')
_wz.handlers = _logger.handlers
_wz.propagate = False
app.secret_key = os.environ.get('FLASK_SECRET', 'gmail-dashboard-secret-2026')

DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD', 'jonathan2026').strip()

def get_csv_path():
    with open('config/settings.json') as f:
        return json.load(f)['paths']['financial_csv']

def load_transactions():
    path = get_csv_path()
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def save_transactions(rows):
    path = get_csv_path()
    if not rows:
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

def load_settings():
    with open('config/settings.json') as f:
        return json.load(f)

def load_label_names():
    settings = load_settings()
    rules_path = settings['paths']['label_rules_file']
    if not os.path.exists(rules_path):
        return {}
    with open(rules_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    return {data['_label_id']: cat for cat, data in raw.items()
            if not cat.startswith('_') and '_label_id' in data}

def get_gmail_service():
    try:
        from gmail_auth import get_service, api_call_with_retry
        return get_service(), None
    except Exception as e:
        return None, str(e)

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💰 Finanzas</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2d3e;
    --text: #e2e8f0; --muted: #64748b; --accent: #6366f1;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --bac: #e4002b; --agri: #2b2a28; --cusc: #004b87;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; }
  .header { background: var(--card); border-bottom: 1px solid var(--border);
            padding: 16px; display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 18px; font-weight: 700; }
  .header .badge { background: var(--accent); color: white; padding: 2px 8px;
                   border-radius: 99px; font-size: 11px; }
  .container { padding: 16px; max-width: 900px; margin: 0 auto; }
  .cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
  @media(min-width:600px){ .cards { grid-template-columns: repeat(4, 1fr); } }
  .card { background: var(--card); border: 1px solid var(--border);
          border-radius: 12px; padding: 16px; }
  .card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .card .value { font-size: 22px; font-weight: 700; margin-top: 4px; }
  .card .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .card.bac { border-left: 3px solid var(--bac); }
  .card.agri { border-left: 3px solid var(--green); }
  .card.cusc { border-left: 3px solid #0ea5e9; }
  .card.total { border-left: 3px solid var(--accent); }
  .charts { display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 16px; }
  @media(min-width:600px){ .charts { grid-template-columns: 1fr 1fr; } }
  .chart-card { background: var(--card); border: 1px solid var(--border);
                border-radius: 12px; padding: 16px; }
  .chart-card h3 { font-size: 13px; color: var(--muted); margin-bottom: 12px; }
  .table-card { background: var(--card); border: 1px solid var(--border);
                border-radius: 12px; padding: 16px; }
  .table-card h3 { font-size: 13px; color: var(--muted); margin-bottom: 12px; }
  .search { width: 100%; background: var(--bg); border: 1px solid var(--border);
            border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: 14px;
            margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 8px;
       border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }
  td { padding: 8px; border-bottom: 1px solid var(--border); }
  tr:hover td { background: rgba(99,102,241,0.05); }
  .badge-banco { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
  .badge-bac { background: rgba(228,0,43,0.15); color: #f87171; }
  .badge-agri { background: rgba(34,197,94,0.15); color: #86efac; }
  .badge-cusc { background: rgba(14,165,233,0.15); color: #7dd3fc; }
  .badge-anth { background: rgba(99,102,241,0.15); color: #a5b4fc; }
  .badge-otro { background: rgba(100,116,139,0.15); color: #94a3b8; }
  .monto { font-weight: 600; color: var(--red); }
  .monto.credit { color: var(--green); }
  .btn-edit { background: none; border: 1px solid var(--border); color: var(--muted);
              padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
  .btn-edit:hover { border-color: var(--accent); color: var(--accent); }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
                   z-index: 100; align-items: center; justify-content: center; padding: 16px; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--card); border: 1px solid var(--border); border-radius: 16px;
           padding: 24px; width: 100%; max-width: 400px; }
  .modal h2 { font-size: 16px; margin-bottom: 16px; }
  .field { margin-bottom: 12px; }
  .field label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .field input, .field select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 10px; color: var(--text); font-size: 14px; }
  .modal-actions { display: flex; gap: 8px; margin-top: 16px; }
  .btn-save { flex: 1; background: var(--accent); color: white; border: none;
              border-radius: 8px; padding: 10px; font-size: 14px; font-weight: 600; cursor: pointer; }
  .btn-cancel { flex: 1; background: var(--bg); color: var(--muted); border: 1px solid var(--border);
                border-radius: 8px; padding: 10px; font-size: 14px; cursor: pointer; }
  .filter-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .filter-btn { background: var(--bg); border: 1px solid var(--border); color: var(--muted);
                padding: 4px 10px; border-radius: 99px; font-size: 12px; cursor: pointer; }
  .filter-btn.active { background: var(--accent); border-color: var(--accent); color: white; }
  #no-data { text-align: center; padding: 40px; color: var(--muted); }
  .month-selector { display: flex; gap: 8px; align-items: center; margin-left: auto; }
  .month-selector select { background: var(--bg); border: 1px solid var(--border);
                            color: var(--text); padding: 4px 8px; border-radius: 8px; font-size: 13px; }
  .revisado-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
  .revisado-dot.ok { background: var(--green); }
  .revisado-dot.pending { background: var(--yellow); }
</style>
</head>
<body>
<div class="header">
  <span style="font-size:24px">💰</span>
  <a href="/" style="color:var(--muted);font-size:13px;text-decoration:none;margin-right:4px">← Inicio</a><h1>Finanzas Jonathan</h1>
  <span class="badge" id="total-count">0 registros</span>
  <span style="font-size:11px;color:#64748b;margin-left:4px" id="last-update"></span>
  <div class="month-selector">
    <select id="month-filter" onchange="filterByMonth()">
      <option value="">Todo</option>
    </select>
  </div>
</div>

<div class="container">
  <div class="cards">
    <div class="card total">
      <div class="label">Total mes</div>
      <div class="value" id="card-total">$0</div>
      <div class="sub" id="card-count">0 transacciones</div>
    </div>
    <div class="card bac">
      <div class="label">BAC Credomatic</div>
      <div class="value" id="card-bac">$0</div>
      <div class="sub" id="card-bac-count">MC·6201 / AMEX·3328</div>
    </div>
    <div class="card agri">
      <div class="label">Banco Agrícola</div>
      <div class="value" id="card-agri">$0</div>
      <div class="sub">TC·6114</div>
    </div>
    <div class="card cusc">
      <div class="label">Cuscatlán</div>
      <div class="value" id="card-cusc">$0</div>
      <div class="sub">Cuenta·5261</div>
    </div>
  </div>

  <div id="balance-section" style="display:none;margin-bottom:16px">
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">SALDOS POR TARJETA</div>
    <div id="balance-cards" class="cards"></div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h3>GASTOS POR DÍA</h3>
      <canvas id="chart-days" height="180"></canvas>
    </div>
    <div class="chart-card">
      <h3>POR BANCO</h3>
      <canvas id="chart-banks" height="180"></canvas>
    </div>
  </div>

  <div class="table-card">
    <h3>TRANSACCIONES</h3>
    <input class="search" type="text" placeholder="Buscar comercio, banco, monto..." oninput="filterTable(this.value)">
    <div class="filter-bar">
      <button class="filter-btn active" onclick="setFilter('all',this)">Todos</button>
      <button class="filter-btn" onclick="setFilter('BAC Credomatic',this)">BAC</button>
      <button class="filter-btn" onclick="setFilter('Banco Agrícola',this)">Agrícola</button>
      <button class="filter-btn" onclick="setFilter('Banco Cuscatlán',this)">Cuscatlán</button>
    </div>
    <div id="no-data" style="display:none">Sin transacciones para mostrar</div>
    <table id="txn-table">
      <thead>
        <tr>
          <th>Fecha</th><th>Banco</th><th>Comercio</th>
          <th>Tipo</th><th>Monto</th><th></th>
        </tr>
      </thead>
      <tbody id="txn-body"></tbody>
    </table>
  </div>
</div>

<!-- Modal de corrección -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <h2>✏️ Corregir transacción</h2>
    <input type="hidden" id="edit-id">
    <div class="field"><label>Fecha</label><input type="date" id="edit-fecha"></div>
    <div class="field"><label>Banco</label>
      <select id="edit-banco">
        <option>BAC Credomatic</option><option>Banco Agrícola</option>
        <option>Banco Cuscatlán</option><option>Anthropic</option>
        <option>Netflix</option><option>Desconocido</option>
      </select>
    </div>
    <div class="field"><label>Comercio</label><input type="text" id="edit-comercio"></div>
    <div class="field"><label>Tipo</label>
      <select id="edit-tipo">
        <option>compra</option><option>transferencia</option><option>debito</option>
        <option>credito</option><option>transfer365</option><option>pago_tarjeta</option>
        <option>pago_servicio</option><option>suscripcion</option><option>estado_cuenta</option>
      </select>
    </div>
    <div class="field"><label>Monto (USD)</label><input type="number" step="0.01" id="edit-monto"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal()">Cancelar</button>
      <button class="btn-save" onclick="saveEdit()">Guardar</button>
    </div>
  </div>
</div>

<script>
let allData = [];
let activeFilter = 'all';
let activeMonth = '';
let chartDays = null;
let chartBanks = null;

function bancoBadge(banco) {
  if (!banco) return '<span class="badge-banco badge-otro">?</span>';
  const b = banco.toLowerCase();
  if (b.includes('bac')) return `<span class="badge-banco badge-bac">BAC</span>`;
  if (b.includes('agrícola') || b.includes('agricola')) return `<span class="badge-banco badge-agri">Agrícola</span>`;
  if (b.includes('cuscatlán') || b.includes('cuscatlan')) return `<span class="badge-banco badge-cusc">Cuscatlán</span>`;
  if (b.includes('anthropic')) return `<span class="badge-banco badge-anth">Anthropic</span>`;
  return `<span class="badge-banco badge-otro">${banco.substring(0,8)}</span>`;
}

function fmt(v) {
  const n = parseFloat(v);
  return isNaN(n) ? '' : '$' + n.toFixed(2);
}

function getFiltered() {
  return allData.filter(r => {
    const matchBank = activeFilter === 'all' || r.banco === activeFilter;
    const matchMonth = !activeMonth || (r.fecha_iso || '').startsWith(activeMonth);
    return matchBank && matchMonth;
  });
}

function renderTable(search = '') {
  const data = getFiltered().filter(r => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (r.comercio||'').toLowerCase().includes(s) ||
           (r.banco||'').toLowerCase().includes(s) ||
           (r.monto||'').includes(s) ||
           (r.tipo||'').toLowerCase().includes(s);
  });

  const tbody = document.getElementById('txn-body');
  const noData = document.getElementById('no-data');

  if (!data.length) {
    tbody.innerHTML = '';
    noData.style.display = 'block';
    return;
  }
  noData.style.display = 'none';

  tbody.innerHTML = data.slice(0, 200).map((r, i) => {
    const isIngreso = (r.tipo||'').includes('credito');
    return `
    <tr>
      <td>${r.fecha_iso || '-'}</td>
      <td>${bancoBadge(r.banco)}</td>
      <td>${r.comercio || r.descripcion?.substring(0,30) || '-'}</td>
      <td>
        <span style="color:${isIngreso?'var(--green)':'var(--red)'};font-size:10px;font-weight:600">${isIngreso?'▲ Ingreso':'▼ Egreso'}</span>
        <div style="color:var(--muted);font-size:10px">${r.tipo || '-'}</div>
      </td>
      <td class="monto ${isIngreso ? 'credit' : ''}">${fmt(r.monto)}</td>
      <td><button class="btn-edit" onclick="openEdit(${allData.indexOf(r)})">✏️</button></td>
    </tr>
  `}).join('');
}

function updateCards() {
  const data = getFiltered().filter(r => parseFloat(r.monto) > 0);
  const total = data.reduce((s, r) => s + (parseFloat(r.monto) || 0), 0);
  const bac = data.filter(r => r.banco?.includes('BAC')).reduce((s,r) => s + (parseFloat(r.monto)||0), 0);
  const agri = data.filter(r => r.banco?.includes('grícola')).reduce((s,r) => s + (parseFloat(r.monto)||0), 0);
  const cusc = data.filter(r => r.banco?.includes('uscatlán')).reduce((s,r) => s + (parseFloat(r.monto)||0), 0);

  document.getElementById('card-total').textContent = '$' + total.toFixed(2);
  document.getElementById('card-count').textContent = data.length + ' transacciones';
  document.getElementById('card-bac').textContent = '$' + bac.toFixed(2);
  document.getElementById('card-agri').textContent = '$' + agri.toFixed(2);
  document.getElementById('card-cusc').textContent = '$' + cusc.toFixed(2);
  document.getElementById('total-count').textContent = allData.length + ' registros';
}

function updateCharts() {
  const data = getFiltered().filter(r => parseFloat(r.monto) > 0);

  // Chart días
  const byDay = {};
  data.forEach(r => {
    const d = (r.fecha_iso || '').substring(0, 10);
    if (d) byDay[d] = (byDay[d] || 0) + (parseFloat(r.monto) || 0);
  });
  const days = Object.keys(byDay).sort().slice(-14);
  const dayVals = days.map(d => byDay[d].toFixed(2));

  if (chartDays) chartDays.destroy();
  chartDays = new Chart(document.getElementById('chart-days'), {
    type: 'bar',
    data: {
      labels: days.map(d => d.substring(5)),
      datasets: [{ data: dayVals, backgroundColor: '#6366f1', borderRadius: 4 }]
    },
    options: { plugins: { legend: { display: false } },
               scales: { x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e2130' } },
                         y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e2130' } } } }
  });

  // Chart bancos
  const byBank = {};
  data.forEach(r => { byBank[r.banco || 'Otro'] = (byBank[r.banco || 'Otro'] || 0) + (parseFloat(r.monto) || 0); });
  const banks = Object.keys(byBank);
  const colors = ['#e4002b','#22c55e','#0ea5e9','#6366f1','#f59e0b'];

  if (chartBanks) chartBanks.destroy();
  chartBanks = new Chart(document.getElementById('chart-banks'), {
    type: 'doughnut',
    data: {
      labels: banks,
      datasets: [{ data: banks.map(b => byBank[b].toFixed(2)),
                   backgroundColor: colors.slice(0, banks.length), borderWidth: 0 }]
    },
    options: { plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 } } } } }
  });
}

function populateMonths() {
  const months = [...new Set(allData.map(r => (r.fecha_iso || '').substring(0, 7)))].sort().reverse();
  const sel = document.getElementById('month-filter');
  months.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    sel.appendChild(opt);
  });
  const now = new Date();
  const currentMonth = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
  const defaultMonth = months.includes(currentMonth) ? currentMonth : (months[0] || '');
  if (defaultMonth) { sel.value = defaultMonth; activeMonth = defaultMonth; }
}

function filterByMonth() {
  activeMonth = document.getElementById('month-filter').value;
  refresh();
}

function setFilter(f, btn) {
  activeFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  refresh();
}

function filterTable(q) { renderTable(q); }

function refresh() { updateCards(); updateCharts(); renderTable(); }

function openEdit(idx) {
  const r = allData[idx];
  document.getElementById('edit-id').value = idx;
  document.getElementById('edit-fecha').value = r.fecha_iso || '';
  document.getElementById('edit-banco').value = r.banco || '';
  document.getElementById('edit-comercio').value = r.comercio || '';
  document.getElementById('edit-tipo').value = r.tipo || '';
  document.getElementById('edit-monto').value = r.monto || '';
  document.getElementById('modal').classList.add('open');
}

function closeModal() { document.getElementById('modal').classList.remove('open'); }

async function saveEdit() {
  const idx = parseInt(document.getElementById('edit-id').value);
  const body = {
    idx,
    fecha_iso: document.getElementById('edit-fecha').value,
    banco: document.getElementById('edit-banco').value,
    comercio: document.getElementById('edit-comercio').value,
    tipo: document.getElementById('edit-tipo').value,
    monto: document.getElementById('edit-monto').value,
  };
  const res = await fetch('/api/correct', { method: 'POST',
    headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (res.ok) {
    const updated = await res.json();
    allData = updated;
    closeModal();
    refresh();
  }
}

// Estado del sistema
fetch('/api/status').then(r => r.json()).then(s => {
  let text = '';
  if (s.last_update) text += 'Actualizado: ' + s.last_update;
  if (s.next_update) text += (text ? ' · ' : '') + 'Próxima: ' + s.next_update;
  if (text) document.getElementById('last-update').textContent = text;
});

// Cargar datos
fetch('/api/transactions').then(r => r.json()).then(data => {
  allData = data;
  populateMonths();
  refresh();
});

fetch('/api/balances').then(r => r.json()).then(balances => {
  const entries = Object.values(balances);
  if (!entries.length) return;
  document.getElementById('balance-section').style.display = 'block';
  document.getElementById('balance-cards').innerHTML = entries.map(b => `
    <div class="card" style="border-left:3px solid var(--yellow)">
      <div class="label">${b.banco} *${b.tarjeta_ultimos4 || '????'}</div>
      <div class="value" style="font-size:18px;color:var(--yellow)">$${(b.saldo_calculado ?? b.saldo_estado_cuenta).toFixed(2)}</div>
      <div class="sub">EC: $${b.saldo_estado_cuenta.toFixed(2)} — ${b.fecha}</div>
      <div class="sub" style="margin-top:4px">
        <span style="color:var(--red)">↓ $${(b.gastos_desde_ec||0).toFixed(2)}</span>
        &nbsp;
        <span style="color:var(--green)">↑ $${(b.ingresos_desde_ec||0).toFixed(2)}</span>
      </div>
    </div>
  `).join('');
});
</script>
</body>
</html>
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login — Finanzas</title>
<style>
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 16px;
          padding: 32px; width: 100%; max-width: 360px; }
  h1 { font-size: 22px; margin-bottom: 8px; }
  p { color: #64748b; font-size: 14px; margin-bottom: 24px; }
  input { width: 100%; background: #0f1117; border: 1px solid #2a2d3e; border-radius: 8px;
          padding: 10px 14px; color: #e2e8f0; font-size: 16px; margin-bottom: 12px; }
  button { width: 100%; background: #6366f1; color: white; border: none; border-radius: 8px;
           padding: 12px; font-size: 16px; font-weight: 600; cursor: pointer; }
  .error { color: #ef4444; font-size: 13px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="card">
  <h1>💰 Finanzas</h1>
  <p>Ingresa la contraseña para acceder</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST">
    <input type="password" name="password" placeholder="Contraseña" autofocus>
    <button type="submit">Entrar</button>
  </form>
</div>
</body>
</html>"""


@app.route('/logout')
def logout():
    return redirect('/')


@app.route('/')
def index():
    return render_template_string(MAIN_MENU_HTML)


@app.route('/finanzas')
def finanzas():
    return render_template_string(HTML)


@app.route('/api/status')
def api_status():
    from datetime import timedelta
    path = get_csv_path()
    last_update = None
    count = 0
    if os.path.exists(path):
        last_update = datetime.fromtimestamp(os.path.getmtime(path), tz=_TZ).strftime('%Y-%m-%d %H:%M')
        with open(path, 'r', encoding='utf-8') as f:
            count = sum(1 for _ in f) - 1
    settings = load_settings()
    financial_time = settings['schedule']['financial_extractor_time']
    h, m = map(int, financial_time.split(':'))
    now = datetime.now(tz=_TZ)
    next_run = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    next_update = next_run.strftime('%Y-%m-%d %H:%M')
    return jsonify({'last_update': last_update, 'total_records': count, 'next_update': next_update})


@app.route('/api/transactions')
def api_transactions():
    return jsonify(load_transactions())


@app.route('/api/correct', methods=['POST'])
def api_correct():
    data = request.get_json()
    rows = load_transactions()
    idx = int(data['idx'])
    if 0 <= idx < len(rows):
        rows[idx]['fecha_iso'] = data.get('fecha_iso', rows[idx].get('fecha_iso', ''))
        rows[idx]['banco'] = data.get('banco', rows[idx].get('banco', ''))
        rows[idx]['comercio'] = data.get('comercio', rows[idx].get('comercio', ''))
        rows[idx]['tipo'] = data.get('tipo', rows[idx].get('tipo', ''))
        rows[idx]['monto'] = data.get('monto', rows[idx].get('monto', ''))
        rows[idx]['revisado'] = 'true'
        save_transactions(rows)
    return jsonify(rows)


@app.route('/emails')
def emails():
    return render_template_string(EMAILS_HTML)


@app.route('/plan')
def plan():
    return render_template_string(PLAN_HTML)


@app.route('/deudas')
def deudas():
    return render_template_string(DEUDAS_HTML)


@app.route('/fugas')
def fugas():
    return render_template_string(FUGAS_HTML)


@app.route('/api/plan', methods=['GET'])
def api_plan_get():
    path = 'data/payment_plan.json'
    if not os.path.exists(path):
        return jsonify({'error': 'Sin plan generado. Configura tu salario y guarda.'})
    with open(path, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


@app.route('/api/plan/config', methods=['POST'])
def api_plan_config():
    try:
        data = request.get_json()
        settings = load_settings()
        planner = settings.setdefault('planner', {})

        salary = float(data.get('salary', 0))
        savings_pct = float(data.get('savings_pct', 0.10))
        cards = data.get('cards', [])

        planner['salary_per_period'] = salary
        planner['savings_percentage'] = savings_pct
        # Update only the balances sent; preserve all existing cards and their metadata
        existing = {c['last4']: c for c in planner.get('cards', [])}
        for c in cards:
            if float(c.get('balance', 0)) > 0:
                existing[c['last4']] = {**existing.get(c['last4'], {}),
                                        'name': c['name'], 'last4': c['last4'],
                                        'balance': float(c['balance'])}
        planner['cards'] = list(existing.values())

        with open('config/settings.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        from payment_planner import build_plan, save_plan
        planner['prestamos'] = settings.get('prestamos', [])
        plan = build_plan(planner)
        if plan:
            save_plan(plan)
            return jsonify({'ok': True, 'plan': plan})
        return jsonify({'error': 'Salario inválido'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/send', methods=['POST'])
def api_plan_send():
    try:
        from payment_planner import send_plan_email, _period_label
        path = 'data/payment_plan.json'
        if not os.path.exists(path):
            return jsonify({'error': 'Sin plan guardado'}), 400
        with open(path, 'r', encoding='utf-8') as f:
            plan = json.load(f)
        label = _period_label(datetime.now(tz=_TZ))
        send_plan_email(plan, label)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/summary/send', methods=['POST', 'GET'])
def api_summary_send():
    try:
        from daily_summary import send_daily_summary
        send_daily_summary()
        return jsonify({'ok': True, 'msg': 'Resumen enviado correctamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/fondos', methods=['GET'])
def api_plan_fondos():
    try:
        settings = load_settings()
        fondos = settings.get('fondos_ahorro', [])
        prestamos = settings.get('prestamos', [])
        result_fondos = []
        for f in fondos:
            mensual = round(f['saldo'] * f['tasa_anual'] / 100 / 12, 2)
            anual = round(f['saldo'] * f['tasa_anual'] / 100, 2)
            result_fondos.append({**f, 'ganancia_mensual': mensual, 'ganancia_anual': anual})
        result_prestamos = []
        for p in prestamos:
            por_quincena = round(p['cuota_mensual'] / 2, 2)
            result_prestamos.append({**p, 'cuota_quincenal': por_quincena})
        return jsonify({'fondos': result_fondos, 'prestamos': result_prestamos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/financiamientos', methods=['GET'])
def api_plan_financiamientos():
    try:
        settings = load_settings()
        items = settings.get('intrafinanciamientos', [])
        result = []
        today = datetime.now(tz=_TZ).date()
        for item in items:
            cuotas_restantes = item['cuotas_total'] - item['cuotas_pagadas']
            # Estimate payoff from corte date + cuotas_restantes months
            from datetime import date as _date
            corte = _date.fromisoformat(item['fecha_corte'])
            raw_month = corte.month - 1 + cuotas_restantes
            payoff_year = corte.year + raw_month // 12
            payoff_month = raw_month % 12 + 1
            payoff_label = f"{['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'][payoff_month]} {payoff_year}"
            progress_pct = round(item['cuotas_pagadas'] / item['cuotas_total'] * 100)
            result.append({**item, 'cuotas_restantes': cuotas_restantes,
                           'payoff_label': payoff_label, 'progress_pct': progress_pct})
        total_saldo = round(sum(i['saldo_actual'] for i in result), 2)
        total_cuota = round(sum(i['cuota_mensual'] for i in result), 2)
        return jsonify({'items': result, 'total_saldo': total_saldo, 'total_cuota': total_cuota})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/balances')
def api_balances():
    settings = load_settings()
    data_dir = settings['paths']['data_dir']
    balances_path = os.path.join(data_dir, 'balances.json')
    if not os.path.exists(balances_path):
        return jsonify({})
    with open(balances_path, 'r', encoding='utf-8') as f:
        balances = json.load(f)
    txns = load_transactions()
    for key, bal in balances.items():
        banco = bal['banco']
        fecha_ec = bal['fecha']
        since_ec = [r for r in txns
                    if r.get('banco') == banco
                    and r.get('fecha_iso', '') >= fecha_ec
                    and not r.get('tipo', '').startswith('estado_cuenta')]
        gastos = sum(float(r.get('monto') or 0) for r in since_ec
                     if not r.get('tipo', '').startswith('credito'))
        ingresos = sum(float(r.get('monto') or 0) for r in since_ec
                       if r.get('tipo', '').startswith('credito'))
        bal['gastos_desde_ec'] = round(gastos, 2)
        bal['ingresos_desde_ec'] = round(ingresos, 2)
        bal['saldo_calculado'] = round(bal['saldo_estado_cuenta'] - gastos + ingresos, 2)
    return jsonify(balances)


@app.route('/api/emails/recent')
def api_emails_recent():
    service, err = get_gmail_service()
    if err:
        return jsonify({'error': err}), 500
    label_names = load_label_names()
    SYSTEM = {'INBOX','SENT','DRAFT','SPAM','TRASH','STARRED','IMPORTANT','UNREAD',
              'CATEGORY_PERSONAL','CATEGORY_SOCIAL','CATEGORY_PROMOTIONS',
              'CATEGORY_UPDATES','CATEGORY_FORUMS'}
    result = api_call_with_retry(
        service.users().messages().list(
            userId='me', q='in:inbox newer_than:7d', maxResults=30
        ).execute)
    emails = []
    for msg in result.get('messages', []):
        m = api_call_with_retry(service.users().messages().get(
            userId='me', id=msg['id'], format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']).execute)
        h = {x['name']: x['value'] for x in m['payload']['headers']}
        user_labels = [label_names.get(l, l) for l in m.get('labelIds', []) if l not in SYSTEM]
        emails.append({'id': msg['id'], 'from': h.get('From',''),
                       'subject': h.get('Subject',''), 'date': h.get('Date',''),
                       'labels': user_labels, 'snippet': m.get('snippet','')[:100]})
    return jsonify(emails)


@app.route('/api/emails/unlabeled')
def api_emails_unlabeled():
    service, err = get_gmail_service()
    if err:
        return jsonify({'error': err}), 500
    result = api_call_with_retry(
        service.users().messages().list(
            userId='me', q='in:inbox has:nouserlabels', maxResults=20
        ).execute)
    emails = []
    for msg in result.get('messages', []):
        m = api_call_with_retry(service.users().messages().get(
            userId='me', id=msg['id'], format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']).execute)
        h = {x['name']: x['value'] for x in m['payload']['headers']}
        emails.append({'id': msg['id'], 'from': h.get('From',''),
                       'subject': h.get('Subject',''), 'date': h.get('Date',''),
                       'snippet': m.get('snippet','')[:100]})
    return jsonify(emails)


@app.route('/api/emails/financial')
def api_emails_financial():
    txns = load_transactions()
    financial_types = {'compra','transferencia','transfer365','debito','credito',
                       'pago_tarjeta','pago_servicio','suscripcion',
                       'estado_cuenta','estado_cuenta_pago_minimo'}
    result = [r for r in txns if r.get('tipo') in financial_types]
    result.sort(key=lambda r: r.get('fecha_iso',''), reverse=True)
    return jsonify(result[:200])


@app.route('/api/emails/label-stats')
def api_emails_label_stats():
    service, err = get_gmail_service()
    if err:
        return jsonify({'error': err}), 500
    label_names = load_label_names()
    result = api_call_with_retry(service.users().labels().list(userId='me').execute)
    stats = [
        {'id': l['id'], 'name': label_names.get(l['id'], l['name']),
         'messages_total': l.get('messagesTotal', 0),
         'messages_unread': l.get('messagesUnread', 0)}
        for l in result.get('labels', []) if l['type'] == 'user'
    ]
    return jsonify(sorted(stats, key=lambda x: x['messages_total'], reverse=True))


@app.route('/logs')
def logs():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        return render_template_string(LOGS_HTML, files=[], content='Sin logs todavía.', current='')
    files = sorted(os.listdir(log_dir), reverse=True)
    selected = request.args.get('f', files[0] if files else '')
    content = ''
    if selected and os.path.exists(os.path.join(log_dir, selected)):
        with open(os.path.join(log_dir, selected), 'r', encoding='utf-8') as f:
            content = f.read()
    return render_template_string(LOGS_HTML, files=files, content=content, current=selected)


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})


@app.route('/api/plan/activity', methods=['GET'])
def api_plan_activity():
    """Recent classified transactions queried directly from Gmail (not from ephemeral CSV)."""
    try:
        from financial_extractor import detect_and_parse, get_body_and_attachments, FINANCIAL_LABEL_IDS
        from transaction_classifier import classify
        from email.utils import parsedate_to_datetime
        from datetime import date

        service, err = get_gmail_service()
        if err:
            return jsonify({'error': err}), 500

        settings = load_settings()
        days = int(request.args.get('days', 30))

        seen = set()
        records = []

        for label_id in FINANCIAL_LABEL_IDS:
            result = api_call_with_retry(
                service.users().messages().list(
                    userId='me', labelIds=[label_id],
                    q=f'newer_than:{days}d', maxResults=50
                ).execute
            )
            for msg in result.get('messages', []):
                if msg['id'] in seen:
                    continue
                seen.add(msg['id'])

                m = api_call_with_retry(
                    service.users().messages().get(
                        userId='me', id=msg['id'], format='full'
                    ).execute
                )
                headers = {h['name']: h['value'] for h in m['payload']['headers']}
                from_header = headers.get('From', '')
                subject = headers.get('Subject', '')
                date_header = headers.get('Date', '')

                body, _ = get_body_and_attachments(m['payload'])
                if not body:
                    body = m.get('snippet', '')

                parsed = detect_and_parse(from_header, subject, body)
                if parsed.get('tipo') == 'login':
                    continue

                parsed['message_id'] = msg['id']
                parsed['descripcion'] = m.get('snippet', '')[:200]

                if not parsed.get('fecha_iso'):
                    try:
                        dt = parsedate_to_datetime(date_header)
                        parsed['fecha_iso'] = dt.date().isoformat()
                    except Exception:
                        parsed['fecha_iso'] = date.today().isoformat()

                classification = classify(parsed, settings)
                parsed.update(classification)
                records.append(parsed)

        records.sort(key=lambda r: r.get('fecha_iso', ''), reverse=True)
        return jsonify(records)
    except Exception as e:
        _logger.error(f'Error in activity: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/cuenta', methods=['GET'])
def api_cuenta():
    """Return cuenta_corriente balance, movements, and monthly cash flow breakdown."""
    try:
        settings = load_settings()
        cuenta = settings.get('cuenta_corriente', {})
        saldo = cuenta.get('saldo', 0)
        planner = settings.get('planner', {})
        cards = planner.get('cards', [])
        fi = settings.get('intrafinanciamientos', [])
        prestamos = settings.get('prestamos', [])
        extras = planner.get('obligaciones_extra', [])
        fondos = settings.get('fondos_ahorro', [])

        salary_per_period = planner.get('salary_per_period', 0)
        ingreso_mensual = round(salary_per_period * 2, 2)

        oblig_tarjetas = round(sum(c.get('min_pago', 0) for c in cards), 2)
        oblig_fi = round(sum(i.get('cuota_mensual', 0) for i in fi), 2)
        oblig_prestamos = round(sum(p.get('cuota_mensual', 0) for p in prestamos), 2)
        oblig_extra = round(sum(e.get('monto_mensual', 0) for e in extras), 2)
        obligaciones_mes = round(oblig_tarjetas + oblig_fi + oblig_prestamos + oblig_extra, 2)

        multimoney_mes = round(sum(
            f.get('deposito_quincena', 0) * 2 for f in fondos if f.get('deposito_quincena')
        ), 2)
        remanente_mes = round(ingreso_mensual - obligaciones_mes - multimoney_mes, 2)

        return jsonify({
            'saldo': saldo,
            'banco': cuenta.get('banco', ''),
            'movimientos': list(reversed(cuenta.get('movimientos', []))),
            'salary_per_period': salary_per_period,
            'ingreso_mensual': ingreso_mensual,
            'obligaciones_mes': obligaciones_mes,
            'oblig_tarjetas': oblig_tarjetas,
            'oblig_fi': oblig_fi,
            'oblig_prestamos': oblig_prestamos,
            'oblig_extra': oblig_extra,
            'multimoney_mes': multimoney_mes,
            'remanente_mes': remanente_mes,
            'proyectado': round(saldo + ingreso_mensual - obligaciones_mes, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/calendario_pagos', methods=['GET'])
def api_calendario_pagos():
    """Return all monthly payment obligations sorted by day."""
    try:
        from datetime import date as _date
        settings = load_settings()
        today = datetime.now(tz=_TZ).date()
        planner = settings.get('planner', {})
        cards = planner.get('cards', [])
        fi_list = settings.get('intrafinanciamientos', [])
        prestamos = settings.get('prestamos', [])
        extras = planner.get('obligaciones_extra', [])
        fondos = settings.get('fondos_ahorro', [])
        MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

        def next_occurrence(dia):
            if today.day <= dia:
                try:
                    return today.replace(day=dia)
                except ValueError:
                    pass
            m, y = today.month + 1, today.year
            if m > 12: m, y = 1, y + 1
            return _date(y, m, dia)

        events = []

        for c in cards:
            if c.get('min_pago', 0) <= 0:
                continue
            dia = c['fecha_pago_dia']
            nxt = next_occurrence(dia)
            events.append({
                'dia': dia,
                'descripcion': f"{c['name']} ****{c['last4']}",
                'monto': c['min_pago'],
                'tipo': 'pago',
                'subtipo': 'tarjeta',
                'passed': (nxt - today).days < 0,
                'next_label': f"{MESES[nxt.month]} {nxt.day}",
                'days_away': (nxt - today).days,
            })

        for i in fi_list:
            dia = i.get('fecha_pago_dia', 0)
            if not dia:
                continue
            nxt = next_occurrence(dia)
            events.append({
                'dia': dia,
                'descripcion': i['descripcion'],
                'monto': i['cuota_mensual'],
                'tipo': 'pago',
                'subtipo': 'intrafinanciamiento',
                'passed': (nxt - today).days < 0,
                'next_label': f"{MESES[nxt.month]} {nxt.day}",
                'days_away': (nxt - today).days,
            })

        for p in prestamos:
            dia = p.get('fecha_pago_dia', 0)
            nxt = next_occurrence(dia)
            events.append({
                'dia': dia,
                'descripcion': p['nombre'],
                'monto': p['cuota_mensual'],
                'tipo': 'pago',
                'subtipo': 'prestamo',
                'passed': (nxt - today).days < 0,
                'next_label': f"{MESES[nxt.month]} {nxt.day}",
                'days_away': (nxt - today).days,
            })

        for e in extras:
            dia = e.get('fecha_pago_dia', 1)
            monto = e.get('monto_matricula', e['monto_mensual']) \
                if today.month in e.get('meses_matricula', []) \
                else e['monto_mensual']
            nxt = next_occurrence(dia)
            events.append({
                'dia': dia,
                'descripcion': e['descripcion'],
                'monto': monto,
                'tipo': 'pago',
                'subtipo': 'extra',
                'passed': (nxt - today).days < 0,
                'next_label': f"{MESES[nxt.month]} {nxt.day}",
                'days_away': (nxt - today).days,
                'notas': e.get('notas', ''),
            })

        for f in fondos:
            for dia in f.get('dias_deposito', []):
                nxt = next_occurrence(dia)
                events.append({
                    'dia': dia,
                    'descripcion': f"Depósito {f['nombre']}",
                    'monto': f.get('deposito_quincena', 0),
                    'tipo': 'deposito',
                    'subtipo': 'ahorro',
                    'passed': (nxt - today).days < 0,
                    'next_label': f"{MESES[nxt.month]} {nxt.day}",
                    'days_away': (nxt - today).days,
                })

        events.sort(key=lambda x: x['dia'])
        total_egresos = round(sum(e['monto'] for e in events if e['tipo'] == 'pago'), 2)
        total_ahorro = round(sum(e['monto'] for e in events if e['tipo'] == 'deposito'), 2)

        return jsonify({
            'events': events,
            'today_day': today.day,
            'total_egresos': total_egresos,
            'total_ahorro': total_ahorro,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tarjetas/calendario', methods=['GET'])
def api_tarjetas_calendario():
    """Return best card to use based on billing cycle and cut dates."""
    from datetime import date as _date
    try:
        settings = load_settings()
        today = datetime.now(tz=_TZ).date()
        cards = settings.get('planner', {}).get('cards', [])
        MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

        def next_day_on_or_after(ref, day):
            if ref.day <= day:
                try:
                    return ref.replace(day=day)
                except ValueError:
                    pass
            m, y = ref.month + 1, ref.year
            if m > 12: m, y = 1, y + 1
            return _date(y, m, day)

        def add_month(d):
            m, y = d.month + 1, d.year
            if m > 12: m, y = 1, y + 1
            return d.replace(year=y, month=m)

        result = []
        for c in cards:
            corte_dia = c.get('fecha_corte_dia', c['fecha_pago_dia'] + 5)
            pago_dia = c['fecha_pago_dia']
            next_cut = next_day_on_or_after(today, corte_dia)
            pay_month = add_month(next_cut)
            next_payment = pay_month.replace(day=pago_dia)
            days_until_cut = (next_cut - today).days
            days_until_payment = (next_payment - today).days
            has_balance = c['balance'] > 0
            result.append({
                'name': c['name'], 'last4': c['last4'],
                'balance': c['balance'], 'has_balance': has_balance,
                'corte_dia': corte_dia, 'pago_dia': pago_dia,
                'next_cut_label': f"{MESES[next_cut.month]} {next_cut.day}",
                'next_payment_label': f"{MESES[next_payment.month]} {next_payment.day}",
                'days_until_cut': days_until_cut,
                'days_until_payment': days_until_payment,
                'safe_to_use': not has_balance,
            })
        result.sort(key=lambda x: (x['has_balance'], -x['days_until_payment']))
        return jsonify({'cards': result, 'today': today.isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/snapshot', methods=['GET'])
def api_plan_snapshot():
    """Return all debt balances with payoff estimates from settings.json."""
    try:
        import math
        settings = load_settings()
        today = datetime.now(tz=_TZ).date()
        cards_cfg = settings.get('planner', {}).get('cards', [])
        MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

        def payoff_info(balance, tasa_anual, min_pago):
            if balance <= 0:
                return {'label': 'Pagado ✓', 'never': False, 'paid': True}
            r = tasa_anual / 100 / 12
            if min_pago <= 0:
                return {'label': '—', 'never': True, 'paid': False}
            if r > 0 and min_pago <= balance * r:
                return {'label': f'Interés/mes ${balance*r:.2f} > pago mínimo', 'never': True, 'paid': False}
            if r == 0:
                months = math.ceil(balance / min_pago)
            else:
                months = math.ceil(-math.log(1 - balance * r / min_pago) / math.log(1 + r))
            raw = today.month - 1 + months
            py = today.year + raw // 12
            pm = raw % 12 + 1
            return {'label': f'{MESES[pm]} {py} ({months}m)', 'never': False, 'paid': False}

        cards = []
        for c in cards_cfg:
            cards.append({**c, 'payoff': payoff_info(c['balance'], c['tasa_anual'], c['min_pago'])})

        total_balance = round(sum(c['balance'] for c in cards_cfg), 2)
        total_min = round(sum(c['min_pago'] for c in cards_cfg), 2)
        return jsonify({'cards': cards, 'total_balance': total_balance, 'total_min': total_min})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/activity/confirm', methods=['POST'])
def api_plan_activity_confirm():
    """Confirm a transaction against a card, adjusting its balance in settings.json.

    POST body: {last4: '3328', delta: -60.87}
      delta < 0 → payment received (reduces balance)
      delta > 0 → new purchase (increases balance)
    """
    try:
        data = request.get_json()
        card_last4 = data.get('last4', '')
        delta = float(data.get('delta', 0))

        if not card_last4:
            return jsonify({'error': 'last4 requerido'}), 400
        if delta == 0:
            return jsonify({'error': 'delta no puede ser 0'}), 400

        settings = load_settings()
        cards = settings.get('planner', {}).get('cards', [])
        card = next((c for c in cards if c.get('last4') == card_last4), None)
        if not card:
            return jsonify({'error': 'Tarjeta no encontrada'}), 404

        card['balance'] = max(0, round(card['balance'] + delta, 2))
        with open('config/settings.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return jsonify({'ok': True, 'name': card['name'], 'new_balance': card['balance']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/quincenal', methods=['GET'])
def api_plan_quincenal():
    try:
        settings = load_settings()
        return jsonify(settings.get('plan_quincenal', {}))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/fondos_esporadicos', methods=['GET', 'POST'])
def api_plan_fondos_esporadicos():
    try:
        settings = load_settings()
        if request.method == 'POST':
            data = request.get_json()
            fondos = settings.get('fondos_esporadicos', [])
            for f in fondos:
                if f['nombre'] == data.get('nombre'):
                    f['saldo'] = round(float(data.get('saldo', 0)), 2)
                    break
            settings['fondos_esporadicos'] = fondos
            with open('config/settings.json', 'w', encoding='utf-8') as fh:
                json.dump(settings, fh, ensure_ascii=False, indent=2)
            return jsonify({'ok': True})
        fondos = settings.get('fondos_esporadicos', [])
        total_q = round(sum(f['quincenal'] for f in fondos), 2)
        total_saldo = round(sum(f['saldo'] for f in fondos), 2)
        return jsonify({'fondos': fondos, 'total_quincenal': total_q, 'total_saldo': total_saldo})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plan/gastos_fijos_amex', methods=['GET'])
def api_plan_gastos_fijos_amex():
    try:
        settings = load_settings()
        gastos = settings.get('gastos_fijos_amex', [])
        total = round(sum(g['monto_mensual'] for g in gastos if not g.get('cancelar')), 2)
        total_bruto = round(sum(g['monto_mensual'] for g in gastos), 2)
        return jsonify({'gastos': gastos, 'total': total, 'total_bruto': total_bruto})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amex/historial')
def api_amex_historial():
    s = load_settings()
    return jsonify({
        'historial': s.get('amex_historial', []),
        'estado_actual': s.get('amex_estado_actual', {})
    })


NOTAS_FILE = 'data/notas.txt'
RECOMENDACIONES_FILE = 'data/recomendaciones.json'

@app.route('/api/recomendaciones', methods=['GET'])
def api_recomendaciones_get():
    try:
        if os.path.exists(RECOMENDACIONES_FILE):
            with open(RECOMENDACIONES_FILE, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/otras_cuentas', methods=['GET'])
def api_otras_cuentas():
    try:
        settings = load_settings()
        return jsonify(settings.get('otras_cuentas', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deudas/estrategias', methods=['GET'])
def api_deudas_estrategias():
    import math, copy
    try:
        settings = load_settings()
        today = datetime.now(tz=_TZ).date()
        MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        planner = settings.get('planner', {})
        salary_per_period = planner.get('salary_per_period', 0)
        ingreso_mensual = salary_per_period * 2

        debts = []
        for c in planner.get('cards', []):
            if c['balance'] > 0:
                tasa_m = c['tasa_anual'] / 100 / 12
                debts.append({
                    'id': f"card_{c['last4']}",
                    'nombre': f"{c['name']} ····{c['last4']}",
                    'tipo': 'tarjeta',
                    'saldo': c['balance'],
                    'tasa_mensual': round(tasa_m, 6),
                    'tasa_anual': c['tasa_anual'],
                    'pago_minimo': max(c.get('min_pago', 0), round(c['balance'] * tasa_m + 1, 2)),
                })
        for p in settings.get('prestamos', []):
            if p.get('saldo', 0) > 0:
                debts.append({
                    'id': f"prestamo_{p.get('numero', p['nombre'])}",
                    'nombre': p['nombre'],
                    'tipo': 'prestamo',
                    'saldo': p['saldo'],
                    'tasa_mensual': round(p['tasa_anual'] / 100 / 12, 6),
                    'tasa_anual': p['tasa_anual'],
                    'pago_minimo': p['cuota_mensual'],
                })
        for fi in settings.get('intrafinanciamientos', []):
            if fi.get('saldo_actual', 0) > 0 and fi.get('tasa_mensual', 0) > 0:
                debts.append({
                    'id': f"fi_{fi['ref']}",
                    'nombre': fi['descripcion'][:40],
                    'tipo': 'financiamiento',
                    'saldo': fi['saldo_actual'],
                    'tasa_mensual': fi['tasa_mensual'] / 100,
                    'tasa_anual': round(fi['tasa_mensual'] * 12, 2),
                    'pago_minimo': fi['cuota_mensual'],
                })

        total_min = round(sum(d['pago_minimo'] for d in debts), 2)
        fondos = settings.get('fondos_ahorro', [])
        multimoney_mes = round(sum(f.get('deposito_quincena', 0) * 2 for f in fondos
                                   if f.get('deposito_quincena')), 2)
        extras = planner.get('obligaciones_extra', [])
        oblig_extra = round(sum(e.get('monto_mensual', 0) for e in extras), 2)
        fi_zero = round(sum(fi.get('cuota_mensual', 0)
                            for fi in settings.get('intrafinanciamientos', [])
                            if fi.get('saldo_actual', 0) > 0 and fi.get('tasa_mensual', 0) == 0), 2)
        remanente = round(ingreso_mensual - total_min - multimoney_mes - oblig_extra - fi_zero, 2)
        extra_budget = max(0, remanente)
        budget_total = round(total_min + extra_budget, 2)

        def simulate(debts_ordered, budget):
            ds = copy.deepcopy(debts_ordered)
            month = 0
            total_interest = 0.0
            payoff_months = {}
            while any(d['saldo'] > 0.01 for d in ds) and month < 360:
                month += 1
                for d in ds:
                    if d['saldo'] > 0.01:
                        interest = d['saldo'] * d['tasa_mensual']
                        d['saldo'] = round(d['saldo'] + interest, 4)
                        total_interest += interest
                remaining = budget
                for d in ds:
                    if d['saldo'] > 0.01:
                        pay = min(d['pago_minimo'], d['saldo'], remaining)
                        d['saldo'] = max(0, round(d['saldo'] - pay, 4))
                        remaining = round(remaining - pay, 4)
                        if d['saldo'] <= 0.01:
                            d['saldo'] = 0
                            payoff_months.setdefault(d['id'], month)
                for d in ds:
                    if d['saldo'] > 0.01 and remaining > 0.01:
                        pay = min(remaining, d['saldo'])
                        d['saldo'] = max(0, round(d['saldo'] - pay, 4))
                        if d['saldo'] <= 0.01:
                            d['saldo'] = 0
                            payoff_months.setdefault(d['id'], month)
                        break
            return month, round(total_interest, 2), payoff_months

        def month_label(m):
            raw = today.month - 1 + m
            return f"{MESES[raw % 12 + 1]} {today.year + raw // 12}"

        def strategy_obj(label, ordered, meses, interes, poffs):
            return {
                'label': label,
                'orden': [{
                    'id': d['id'], 'nombre': d['nombre'],
                    'saldo': d['saldo'], 'tasa_anual': d['tasa_anual'],
                    'liquidacion_label': month_label(poffs.get(d['id'], meses)),
                    'mes': poffs.get(d['id'], meses),
                } for d in ordered],
                'meses': meses,
                'liquidacion_label': month_label(meses),
                'interes_total': interes,
            }

        avalancha = sorted(debts, key=lambda d: -d['tasa_anual'])
        bola_nieve = sorted(debts, key=lambda d: d['saldo'])
        small = sorted([d for d in debts if d['saldo'] < 500], key=lambda d: d['saldo'])
        large = sorted([d for d in debts if d['saldo'] >= 500], key=lambda d: -d['tasa_anual'])
        hibrida = small + large

        ma, ia, pa = simulate(avalancha, budget_total)
        mb, ib, pb = simulate(bola_nieve, budget_total)
        mh, ih, ph = simulate(hibrida, budget_total)

        recomendada = min([('avalancha', ia), ('bola_de_nieve', ib), ('hibrida', ih)],
                          key=lambda x: x[1])[0]

        return jsonify({
            'debts': debts,
            'budget_total': budget_total,
            'total_min': total_min,
            'extra_budget': extra_budget,
            'ingreso_mensual': ingreso_mensual,
            'recomendada': recomendada,
            'estrategias': {
                'avalancha': strategy_obj('Avalancha', avalancha, ma, ia, pa),
                'bola_de_nieve': strategy_obj('Bola de nieve', bola_nieve, mb, ib, pb),
                'hibrida': strategy_obj('Híbrida', hibrida, mh, ih, ph),
            },
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fugas', methods=['GET'])
def api_fugas():
    try:
        settings = load_settings()
        historial = settings.get('amex_historial', [])
        all_periods = [m['periodo'] for m in historial]

        monthly_cats = {}
        for mes in historial:
            cats = {}
            for tx in mes.get('transacciones', []):
                cat = tx.get('categoria', 'Otros')
                cats[cat] = round(cats.get(cat, 0) + tx['monto'], 2)
            monthly_cats[mes['periodo']] = cats

        all_cats = set()
        for cats in monthly_cats.values():
            all_cats.update(cats.keys())

        n = len(all_periods)

        trends = []
        if n >= 3:
            recent = all_periods[max(0, n-3):]
            earlier = all_periods[:max(1, n-3)]
            for cat in all_cats:
                r_avg = sum(monthly_cats[p].get(cat, 0) for p in recent) / len(recent)
                e_avg = sum(monthly_cats[p].get(cat, 0) for p in earlier) / len(earlier) if earlier else 0
                if e_avg > 0 and r_avg > 10:
                    var = round((r_avg - e_avg) / e_avg * 100, 1)
                    if var > 25:
                        trends.append({
                            'categoria': cat,
                            'promedio_anterior': round(e_avg, 2),
                            'promedio_reciente': round(r_avg, 2),
                            'variacion_pct': var,
                        })
        trends.sort(key=lambda x: -x['variacion_pct'])

        recent_periods = all_periods[-3:] if n >= 3 else all_periods
        subs = {}
        for mes in historial:
            if mes['periodo'] in recent_periods:
                for tx in mes.get('transacciones', []):
                    if tx.get('tipo') == 'fijo':
                        desc = tx['descripcion']
                        if desc not in subs:
                            subs[desc] = {
                                'descripcion': desc,
                                'meses_activos': 0,
                                'ultimo_monto': 0,
                                'cancelar': False,
                                'categoria': tx.get('categoria', 'Otros'),
                            }
                        subs[desc]['meses_activos'] += 1
                        subs[desc]['ultimo_monto'] = tx['monto']
                        if tx.get('cancelar'):
                            subs[desc]['cancelar'] = True
        subs_list = sorted(subs.values(), key=lambda x: (-int(x['cancelar']), -x['ultimo_monto']))

        over_avg = []
        if n >= 2:
            last_p = all_periods[-1]
            last = monthly_cats[last_p]
            for cat, amt in last.items():
                hist_avg = (sum(monthly_cats[p].get(cat, 0) for p in all_periods[:-1])
                            / (n - 1))
                if amt > hist_avg * 1.3 and amt > 15 and hist_avg > 0:
                    over_avg.append({
                        'categoria': cat,
                        'mes_actual': amt,
                        'mes_actual_label': last_p,
                        'promedio_historico': round(hist_avg, 2),
                        'variacion_pct': round((amt - hist_avg) / hist_avg * 100, 1),
                    })
            over_avg.sort(key=lambda x: -x['variacion_pct'])

        return jsonify({
            'periodos': all_periods,
            'suscripciones': subs_list,
            'tendencias_al_alza': trends,
            'sobre_historico': over_avg,
            'monthly_cats': monthly_cats,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notas', methods=['GET'])
def api_notas_get():
    try:
        if os.path.exists(NOTAS_FILE):
            with open(NOTAS_FILE, 'r', encoding='utf-8') as f:
                return jsonify({'texto': f.read()})
        return jsonify({'texto': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notas', methods=['POST'])
def api_notas_post():
    try:
        data = request.get_json()
        texto = data.get('texto', '').strip()
        os.makedirs('data', exist_ok=True)
        with open(NOTAS_FILE, 'w', encoding='utf-8') as f:
            f.write(texto)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/efectivo', methods=['GET'])
def api_efectivo():
    settings = load_settings()
    ef = settings.get('efectivo_en_mano', {})
    return jsonify({
        'saldo': ef.get('saldo', 0),
        'movimientos': list(reversed(ef.get('movimientos', [])))
    })


@app.route('/api/presupuesto_bac', methods=['GET'])
def api_presupuesto_bac():
    from datetime import date
    settings = load_settings()
    bac = next((c for c in settings.get('otras_cuentas', []) if c.get('nombre') == 'Débito BAC'), None)
    if not bac or 'presupuesto' not in bac:
        return jsonify({'error': 'no presupuesto'})
    p = bac['presupuesto']
    today = date.today()
    fecha_inicio = date.fromisoformat(p['fecha_inicio'])
    fecha_fin = date.fromisoformat(p['fecha_fin'])
    saldo_inicio = p['saldo_inicio']
    dias_total = p['dias_total']
    presupuesto_diario = round(saldo_inicio / dias_total, 2)
    dias_transcurridos = max(0, (today - fecha_inicio).days)
    dias_restantes = max(0, (fecha_fin - today).days)
    movimientos = bac.get('movimientos', [])
    gasto_periodo = round(sum(m['monto'] for m in movimientos
                              if m['tipo'] == 'egreso' and m['fecha'] >= p['fecha_inicio']), 2)
    presupuesto_consumido = round(presupuesto_diario * dias_transcurridos, 2)
    remanente = round(presupuesto_consumido - gasto_periodo, 2)
    saldo_actual = bac.get('saldo', 0)
    proyeccion_diaria = round(saldo_actual / dias_restantes, 2) if dias_restantes > 0 else 0
    return jsonify({
        'saldo_inicio': saldo_inicio,
        'saldo_actual': saldo_actual,
        'fecha_inicio': p['fecha_inicio'],
        'fecha_fin': p['fecha_fin'],
        'dias_total': dias_total,
        'dias_transcurridos': dias_transcurridos,
        'dias_restantes': dias_restantes,
        'presupuesto_diario': presupuesto_diario,
        'gasto_periodo': gasto_periodo,
        'presupuesto_consumido': presupuesto_consumido,
        'remanente': remanente,
        'proyeccion_diaria': proyeccion_diaria,
        'movimientos': list(reversed(movimientos))
    })


@app.route('/memory', methods=['GET'])
def memory():
    import os
    from flask import Response
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'claude_memory.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = '# claude_memory.md no encontrado'
    resp = Response(content, mimetype='text/plain; charset=utf-8')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


MAIN_MENU_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Panel de Control</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; min-height: 100vh; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 18px 20px; }
  .header h1 { font-size: 19px; font-weight: 700; }
  .header .sub { color: #64748b; font-size: 12px; margin-top: 3px; }
  .status-bar { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  @media(min-width: 480px) { .status-bar { flex-direction: row; gap: 20px; } }
  .status-item { font-size: 12px; color: #64748b; }
  .status-item .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%;
                      background: #22c55e; margin-right: 5px; vertical-align: middle; }
  .status-item .dot.next { background: #6366f1; }
  .status-item strong { color: #e2e8f0; font-weight: 500; }
  .container { padding: 16px; max-width: 720px; margin: 0 auto; }
  .menu-grid { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 4px; }
  @media(min-width: 480px) { .menu-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; } }
  @media(min-width: 700px) { .menu-grid { grid-template-columns: repeat(4, 1fr); } }
  .menu-card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 14px;
               padding: 16px 18px; text-decoration: none; color: inherit;
               display: flex; align-items: center; gap: 14px;
               transition: border-color .15s, background .15s; }
  @media(min-width: 480px) {
    .menu-card { flex-direction: column; align-items: flex-start; gap: 10px; padding: 20px; }
  }
  .menu-card:hover { border-color: #6366f1; background: #1e2235; }
  .menu-card:active { background: #232640; }
  .menu-card .icon { font-size: 26px; flex-shrink: 0; }
  @media(min-width: 480px) { .menu-card .icon { font-size: 30px; } }
  .menu-card h2 { font-size: 15px; font-weight: 700; margin-bottom: 2px; }
  .menu-card p { font-size: 12px; color: #64748b; line-height: 1.5; }
  @media(max-width: 479px) { .menu-card p { display: none; } }
</style>
</head>
<body>
<div class="header">
  <h1>📊 Panel de Control</h1>
  <div class="sub">Gmail MCP — Automatización financiera y de correos</div>
  <div class="status-bar" id="status-bar" style="display:none">
    <div class="status-item">
      <span class="dot"></span>Última actualización: <strong id="last-update">—</strong>
    </div>
    <div class="status-item">
      <span class="dot next"></span>Próxima actualización: <strong id="next-update">—</strong>
    </div>
  </div>
</div>
<div class="container">
  <div class="menu-grid">
    <a href="/finanzas" class="menu-card">
      <span class="icon">💰</span>
      <div><h2>Finanzas</h2><p>Transacciones, gastos por banco, saldos de tarjetas y estados de cuenta</p></div>
    </a>
    <a href="/emails" class="menu-card">
      <span class="icon">📧</span>
      <div><h2>Correos</h2><p>Correos recientes, etiquetados, sin etiquetar y estadísticas por etiqueta</p></div>
    </a>
    <a href="/logs" class="menu-card">
      <span class="icon">📋</span>
      <div><h2>Logs</h2><p>Logs del orchestrator, cleanup, labeler y financial extractor</p></div>
    </a>
    <a href="/plan" class="menu-card">
      <span class="icon">🗓️</span>
      <div><h2>Plan</h2><p>Plan de pagos y ahorro para cada quincena, con notificación automática</p></div>
    </a>
    <a href="/deudas" class="menu-card">
      <span class="icon">🎯</span>
      <div><h2>Destructor de deudas</h2><p>Avalancha, bola de nieve e híbrida con fechas y total de interés por estrategia</p></div>
    </a>
    <a href="/fugas" class="menu-card">
      <span class="icon">🔍</span>
      <div><h2>Detector de fugas</h2><p>Gastos sobre el promedio, suscripciones activas y categorías en alza</p></div>
    </a>
    <div class="menu-card" onclick="sendSummary()" style="cursor:pointer">
      <span class="icon">📨</span>
      <div><h2>Reenviar resumen</h2><p>Envía el correo de presupuesto del día al instante</p></div>
    </div>
  </div>
</div>
<script>
function sendSummary() {
  fetch('/api/summary/send', {method:'POST'})
    .then(r => r.json())
    .then(d => alert(d.ok ? '✅ Resumen enviado a tu correo' : '❌ Error: ' + d.error))
    .catch(() => alert('❌ Error al conectar'));
}
fetch('/api/status').then(r => r.json()).then(s => {
  if (s.last_update || s.next_update) {
    document.getElementById('status-bar').style.display = 'flex';
    if (s.last_update) document.getElementById('last-update').textContent = s.last_update;
    if (s.next_update) document.getElementById('next-update').textContent = s.next_update;
  }
}).catch(() => {});
</script>
</body>
</html>"""

PLAN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🗓️ Estado de Deuda</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 16px 20px;
            display: flex; align-items: center; gap: 12px; }
  .header a { color: #6366f1; text-decoration: none; font-size: 13px; flex-shrink: 0; }
  .header h1 { font-size: 17px; font-weight: 700; }
  .container { padding: 14px; max-width: 720px; margin: 0 auto; }
  .section { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px;
             padding: 18px; margin-bottom: 12px; }
  .section h2 { font-size: 13px; color: #64748b; text-transform: uppercase;
                letter-spacing: .06em; margin-bottom: 14px; }
  /* Liquidez */
  .liq-hero { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
  .liq-saldo { font-size: 36px; font-weight: 700; color: #e2e8f0; }
  .liq-banco { font-size: 12px; color: #64748b; }
  .liq-proyectado { font-size: 13px; color: #94a3b8; margin-bottom: 14px; }
  .liq-proyectado strong { color: #f59e0b; }
  .mov-list { display: flex; flex-direction: column; gap: 4px; }
  .mov-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
             background: #0f1117; border-radius: 8px; font-size: 12px; }
  .mov-date { color: #64748b; min-width: 80px; flex-shrink: 0; }
  .mov-desc { flex: 1; color: #e2e8f0; }
  .mov-monto { font-weight: 700; min-width: 80px; text-align: right; flex-shrink: 0; }
  .mov-monto.ingreso { color: #22c55e; }
  .mov-monto.egreso { color: #ef4444; }
  /* Calendario de tarjetas */
  .cal-grid { display: grid; gap: 10px; margin-bottom: 12px; }
  @media(min-width:500px){ .cal-grid { grid-template-columns: repeat(2,1fr); } }
  .cal-card { background: #0f1117; border: 1px solid #2a2d3e; border-radius: 10px; padding: 14px;
              position: relative; }
  .cal-card.best { border-color: #22c55e; box-shadow: 0 0 0 1px rgba(34,197,94,.3); }
  .cal-card.has-balance { border-color: #ef444466; }
  .cal-best-badge { position: absolute; top: 10px; right: 10px; background: #22c55e;
                    color: #0f1117; font-size: 10px; font-weight: 700; padding: 2px 7px;
                    border-radius: 99px; text-transform: uppercase; letter-spacing: .04em; }
  .cal-name { font-size: 12px; font-weight: 700; margin-bottom: 2px; }
  .cal-last4 { font-size: 11px; color: #64748b; }
  .cal-balance { font-size: 18px; font-weight: 700; margin: 6px 0 8px; }
  .cal-dates { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }
  .cal-date-box { background: #1a1d27; border-radius: 7px; padding: 8px 10px; }
  .cal-date-lbl { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 3px; }
  .cal-date-val { font-size: 13px; font-weight: 700; }
  .cal-days { font-size: 11px; color: #94a3b8; margin-top: 2px; }
  .cal-grace-bar { height: 4px; background: #2a2d3e; border-radius: 99px; margin: 8px 0 4px; overflow: hidden; }
  .cal-grace-fill { height: 100%; border-radius: 99px; }
  .cal-warning { font-size: 11px; padding: 6px 8px; border-radius: 6px;
                 background: rgba(239,68,68,.12); color: #fca5a5; margin-top: 6px; }
  .cal-tip { font-size: 11px; padding: 6px 8px; border-radius: 6px;
             background: rgba(34,197,94,.1); color: #86efac; margin-top: 6px; }
  /* Tarjetas de crédito */
  .tc-grid { display: grid; gap: 10px; margin-bottom: 12px; }
  @media(min-width:500px){ .tc-grid { grid-template-columns: repeat(2,1fr); } }
  .tc-card { background: #0f1117; border: 1px solid #2a2d3e; border-radius: 10px; padding: 14px; }
  .tc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .tc-name { font-size: 12px; font-weight: 700; }
  .tc-last4 { font-size: 11px; color: #64748b; }
  .tc-balance { font-size: 26px; font-weight: 700; margin: 4px 0 6px; }
  .tc-meta { font-size: 11px; color: #64748b; margin-bottom: 8px; }
  .tc-payoff { font-size: 12px; font-weight: 600; padding: 4px 8px; border-radius: 6px;
               background: rgba(255,255,255,.04); display: inline-block; }
  /* Intrafinanciamientos */
  .fi-grid { display: grid; gap: 10px; }
  @media(min-width:540px){ .fi-grid { grid-template-columns: repeat(3,1fr); } }
  .fi-card { background: #0f1117; border: 1px solid #2a2d3e; border-radius: 10px; padding: 14px; }
  .fi-card.urgent { border-color: #ef4444; }
  .fi-ref { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; }
  .fi-desc { font-size: 12px; color: #a5b4fc; font-weight: 600; margin: 4px 0 8px; }
  .fi-cuota { font-size: 18px; font-weight: 700; color: #e2e8f0; }
  .fi-cuota span { font-size: 11px; color: #64748b; font-weight: 400; }
  .fi-progress { height: 6px; background: #2a2d3e; border-radius: 99px; margin: 10px 0 4px; overflow: hidden; }
  .fi-progress-bar { height: 100%; border-radius: 99px; background: #0ea5e9; }
  .fi-progress-bar.near { background: #ef4444; }
  .fi-meta { display: flex; justify-content: space-between; font-size: 10px; color: #64748b; margin-top: 6px; }
  .fi-saldo { font-size: 12px; color: #94a3b8; margin-top: 6px; }
  .fi-saldo strong { color: #e2e8f0; }
  .fi-total { margin-top: 12px; padding: 10px 12px; background: #1a1d27; border: 1px solid #2a2d3e;
              border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }
  .fi-total .fi-total-label { font-size: 12px; color: #64748b; }
  .fi-total .fi-total-val { font-size: 15px; font-weight: 700; color: #0ea5e9; }
  /* Préstamos */
  .prestamo-row { display: flex; justify-content: space-between; align-items: center;
                  padding: 10px 0; border-bottom: 1px solid #1e2130; }
  .prestamo-row:last-child { border-bottom: none; }
  .prestamo-name { font-size: 13px; color: #e2e8f0; font-weight: 600; }
  .prestamo-meta { font-size: 11px; color: #64748b; margin-top: 2px; }
  .prestamo-cuota { text-align: right; }
  .prestamo-cuota .amount { font-size: 16px; font-weight: 700; color: #f59e0b; }
  .prestamo-cuota .per { font-size: 10px; color: #64748b; }
  /* Fondo */
  .fondo-card { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.2);
                border-radius: 10px; padding: 14px; display: flex; justify-content: space-between;
                align-items: center; }
  .fondo-balance { font-size: 24px; font-weight: 700; color: #22c55e; }
  .fondo-label { font-size: 11px; color: #64748b; margin-bottom: 4px; }
  .fondo-meta { font-size: 12px; color: #86efac; margin-top: 4px; }
  .fondo-right { text-align: right; }
  .fondo-tasa { font-size: 20px; font-weight: 700; color: #22c55e; }
  .fondo-intocable { display: inline-block; background: rgba(34,197,94,.15); color: #86efac;
                     font-size: 10px; padding: 2px 7px; border-radius: 99px; margin-top: 6px; }
  /* Totales */
  .tot-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .tot-table td { padding: 8px 4px; border-bottom: 1px solid #1e2130; }
  .tot-table tr:last-child td { border-bottom: none; font-weight: 700; font-size: 15px; padding-top: 12px; }
  .tot-table .tot-val { text-align: right; font-weight: 600; color: #ef4444; }
  .tot-table tr:last-child .tot-val { color: #f59e0b; font-size: 17px; }
  .tot-section-title { font-size: 11px; color: #64748b; text-transform: uppercase;
                       letter-spacing: .05em; margin: 14px 0 6px; }
  .toast { position: fixed; bottom: 20px; right: 20px; background: #22c55e; color: white;
           padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 600;
           display: none; z-index: 999; box-shadow: 0 4px 12px rgba(0,0,0,.4); }
  .toast.error { background: #ef4444; }
  .loading-msg { color: #64748b; font-size: 12px; padding: 8px 0; }
  /* Flujo mensual */
  .flujo-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 8px; margin: 10px 0; }
  @media(min-width:480px){ .flujo-grid { grid-template-columns: repeat(4,1fr); } }
  .flujo-item { background: #0f1117; border-radius: 8px; padding: 10px 12px; }
  .flujo-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing:.04em; }
  .flujo-val { font-size: 15px; font-weight: 700; margin-top: 3px; }
  /* Calendario de pagos */
  .cal-pago-list { display: flex; flex-direction: column; gap: 6px; }
  .cal-pago-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px;
                  background: #0f1117; border-radius: 8px; border-left: 3px solid #2a2d3e;
                  transition: opacity .2s; }
  .cal-pago-row.passed { opacity: .45; }
  .cal-pago-row.done { opacity: .4; }
  .cal-pago-row.done .cal-pago-desc { text-decoration: line-through; color: #64748b; }
  .cal-pago-row.done .cal-pago-monto { text-decoration: line-through; color: #64748b !important; }
  .cal-pago-row.today { border-left-color: #f59e0b; }
  .cal-pago-row.soon { border-left-color: #ef4444; }
  .cal-pago-row.ahorro { border-left-color: #22c55e; }
  .cal-pago-row.done { border-left-color: #22c55e !important; }
  .cal-dia-badge { min-width: 30px; height: 30px; border-radius: 6px; background: #1a1d27;
                   display: flex; align-items: center; justify-content: center;
                   font-size: 13px; font-weight: 700; color: #e2e8f0; flex-shrink: 0; }
  .cal-pago-row.passed .cal-dia-badge { background: #111318; color: #64748b; }
  .cal-pago-desc { flex: 1; font-size: 12px; color: #e2e8f0; }
  .cal-pago-desc .cal-sub { font-size: 10px; color: #64748b; }
  .cal-pago-monto { font-size: 13px; font-weight: 700; text-align: right; flex-shrink: 0; }
  .cal-pago-next { font-size: 10px; color: #64748b; text-align: right; margin-top: 1px; }
  .cal-check { width: 18px; height: 18px; border-radius: 5px; border: 2px solid #2a2d3e;
               background: transparent; cursor: pointer; appearance: none; flex-shrink: 0;
               transition: background .15s, border-color .15s; }
  .cal-check:checked { background: #22c55e; border-color: #22c55e; }
  .cal-check:checked::after { content: '✓'; display: block; text-align: center;
                               font-size: 11px; line-height: 14px; color: #000; font-weight: 700; }
  /* Recomendaciones */
  .rec-card { background: #0f1117; border: 1px solid #2a2d3e; border-left: 3px solid #64748b;
              border-radius: 10px; padding: 14px; margin-bottom: 8px; }
  .rec-card.alta { border-left-color: #ef4444; }
  .rec-card.media { border-left-color: #f59e0b; }
  .rec-card.baja { border-left-color: #22c55e; }
  .rec-header { display: flex; justify-content: space-between; align-items: flex-start;
                gap: 8px; margin-bottom: 4px; }
  .rec-titulo { font-size: 13px; font-weight: 700; color: #e2e8f0; flex: 1; }
  .rec-badges { display: flex; gap: 4px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
  .rec-badge { font-size: 10px; padding: 2px 6px; border-radius: 99px; font-weight: 600;
               white-space: nowrap; }
  .rec-fecha { font-size: 10px; color: #64748b; margin-bottom: 6px; }
  .rec-texto { font-size: 12px; color: #94a3b8; line-height: 1.6; }
  /* Presupuesto BAC */
  .ppto-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 8px; margin-bottom: 12px; }
  @media(min-width:480px){ .ppto-grid { grid-template-columns: repeat(4,1fr); } }
  .ppto-item { background: #0f1117; border-radius: 8px; padding: 10px 12px; }
  .ppto-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing:.04em; }
  .ppto-val { font-size: 15px; font-weight: 700; margin-top: 3px; }
  .ppto-bar-wrap { background: #1a1d27; border-radius: 99px; height: 8px; margin: 10px 0 4px; overflow: hidden; }
  .ppto-bar { height: 100%; border-radius: 99px; transition: width .4s; }
  .ppto-bar-label { display: flex; justify-content: space-between; font-size: 10px; color: #64748b; }
  .ppto-veredicto { padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
                    display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .ppto-veredicto.ok { background: #052e16; color: #22c55e; border: 1px solid #166534; }
  .ppto-veredicto.over { background: #450a0a; color: #ef4444; border: 1px solid #991b1b; }
  /* Efectivo en mano */
  .efectivo-saldo { font-size: 28px; font-weight: 800; color: #22c55e; margin-bottom: 12px; }
  .efectivo-mov { display: flex; flex-direction: column; gap: 4px; }
  .efectivo-row { display: flex; justify-content: space-between; align-items: center;
                  padding: 6px 10px; background: #0f1117; border-radius: 7px;
                  font-size: 12px; }
  .efectivo-row .ef-desc { color: #e2e8f0; flex: 1; }
  .efectivo-row .ef-fecha { color: #64748b; font-size: 10px; margin: 0 10px; }
  .efectivo-row .ef-monto { font-weight: 700; flex-shrink: 0; }
  /* Notas para Claude */
  .notas-area { width: 100%; background: #0f1117; border: 1px solid #2a2d3e; border-radius: 8px;
                color: #e2e8f0; font-family: -apple-system, sans-serif; font-size: 13px;
                padding: 10px 12px; resize: vertical; min-height: 90px; line-height: 1.6;
                outline: none; transition: border-color .15s; }
  .notas-area:focus { border-color: #6366f1; }
  .notas-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
  .notas-hint { font-size: 11px; color: #64748b; }
  .notas-btn { background: #6366f1; color: white; border: none; border-radius: 7px;
               padding: 7px 18px; font-size: 13px; font-weight: 600; cursor: pointer;
               transition: background .15s; }
  .notas-btn:hover { background: #4f46e5; }
  .notas-btn:disabled { background: #2a2d3e; color: #64748b; cursor: default; }
  .notas-saved { font-size: 11px; color: #22c55e; display: none; }
  /* Plan Quincenal */
  .pq-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .pq-table th { text-align: left; color: #64748b; font-weight: 500; padding: 6px 8px;
                 border-bottom: 1px solid #2a2d3e; font-size: 11px; text-transform: uppercase; }
  .pq-table td { padding: 8px 6px; border-bottom: 1px solid #1e2130; font-size: 13px; }
  .pq-table tr.total-row td { border-bottom: none; font-weight: 700; background: rgba(99,102,241,.06);
                               border-radius: 6px; padding: 10px 6px; }
  .pq-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; vertical-align: middle; }
  /* Fondos Esporádicos */
  .fe-grid { display: grid; gap: 10px; }
  @media(min-width:500px){ .fe-grid { grid-template-columns: repeat(2,1fr); } }
  .fe-card { background: #0f1117; border: 1px solid #2a2d3e; border-radius: 10px; padding: 14px; }
  .fe-nombre { font-size: 12px; font-weight: 700; color: #e2e8f0; margin-bottom: 2px; }
  .fe-saldo { font-size: 26px; font-weight: 700; color: #22c55e; margin: 4px 0; }
  .fe-bar-wrap { background: #2a2d3e; border-radius: 99px; height: 5px; margin: 8px 0 4px; overflow: hidden; }
  .fe-bar { height: 100%; border-radius: 99px; background: #22c55e; transition: width .4s; }
  .fe-meta { font-size: 10px; color: #64748b; }
  /* Gastos Fijos AMEX */
  .gf-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
            background: #0f1117; border-radius: 8px; margin-bottom: 4px; }
  .gf-desc { flex: 1; font-size: 12px; color: #e2e8f0; }
  .gf-cancelar-badge { font-size: 10px; color: #ef4444; background: rgba(239,68,68,.1);
                       padding: 1px 6px; border-radius: 99px; white-space: nowrap; }
  .gf-monto { font-weight: 700; font-size: 13px; color: #ef4444; flex-shrink: 0; }
  .gf-monto.tachado { text-decoration: line-through; color: #64748b; }
  /* AMEX payoff */
  .amex-payoff { background: rgba(228,0,43,.06); border: 1px solid rgba(228,0,43,.2);
                 border-radius: 10px; padding: 14px; }
  .amex-payoff-saldo { font-size: 28px; font-weight: 700; color: #e4002b; }
  .amex-payoff-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; line-height: 1.6; }
  /* AMEX History */
  .amex-hist-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;}
  .amex-status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;margin-bottom:1.5rem;}
  .amex-stat{background:#1a1d27;border:1px solid #2a2d3e;border-radius:8px;padding:.75rem 1rem;}
  .amex-stat-label{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;}
  .amex-stat-value{font-size:1.25rem;font-weight:700;margin-top:.2rem;}
  .amex-accordion{display:flex;flex-direction:column;gap:.5rem;}
  .amex-acc-item{border:1px solid #2a2d3e;border-radius:8px;overflow:hidden;}
  .amex-acc-trigger{width:100%;display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;background:#1a1d27;cursor:pointer;border:none;color:inherit;font-size:.9rem;text-align:left;}
  .amex-acc-trigger:hover{background:rgba(255,255,255,.04);}
  .amex-acc-body{display:none;padding:1rem;border-top:1px solid #2a2d3e;background:#0f1117;}
  .amex-acc-body.open{display:block;}
  .amex-acc-meta{display:flex;gap:1.5rem;font-size:.8rem;color:#64748b;margin-bottom:.75rem;}
  .amex-tx-table{width:100%;border-collapse:collapse;font-size:.82rem;}
  .amex-tx-table th{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #2a2d3e;color:#64748b;font-weight:600;}
  .amex-tx-table td{padding:.35rem .5rem;border-bottom:1px solid #2a2d3e;}
  .amex-tx-fijo{color:#64748b;}
  .amex-tx-cancelar{color:#e53e3e;font-size:.72rem;margin-left:.25rem;}
  .amex-cat-badge{display:inline-block;padding:.1rem .4rem;border-radius:4px;font-size:.7rem;background:rgba(99,102,241,.12);color:#6366f1;}
  .amex-period-totals{display:flex;gap:1rem;margin-top:.75rem;font-size:.82rem;}
  .amex-proj-table{width:100%;border-collapse:collapse;font-size:.85rem;margin-top:.5rem;}
  .amex-proj-table th{text-align:left;padding:.5rem;border-bottom:2px solid #2a2d3e;color:#64748b;}
  .amex-proj-table td{padding:.5rem;border-bottom:1px solid #2a2d3e;}
  .amex-proj-liquidada{color:#22c55e;font-weight:700;}
  .amex-proj-bar-wrap{height:6px;background:#2a2d3e;border-radius:3px;overflow:hidden;width:80px;display:inline-block;vertical-align:middle;margin-left:.5rem;}
  .amex-proj-bar-fill{height:100%;background:#6366f1;border-radius:3px;transition:width .4s;}
</style>
</head>
<body>
<div class="header">
  <a href="/">← Menú</a>
  <h1>🗓️ Estado de Deuda</h1>
</div>
<div class="container">

  <!-- AMEX History -->
  <div class="section" id="amex-hist-section" style="margin-bottom:2rem">
    <div class="amex-hist-header">
      <h2 style="margin:0">&#x1F4B3; AMEX BAC ****3328 &mdash; Historial</h2>
      <span id="amex-saldo-badge" style="font-size:1.1rem;font-weight:700;color:#e53e3e"></span>
    </div>
    <div class="amex-status-grid" id="amex-status-grid"></div>
    <h3 style="margin:.5rem 0 .75rem;font-size:.95rem;color:#64748b">Proyecci&oacute;n de liquidaci&oacute;n ($250/mes)</h3>
    <div style="overflow-x:auto;margin-bottom:1.5rem">
      <table class="amex-proj-table" id="amex-proj-table">
        <thead><tr><th>Mes</th><th>Saldo inicio</th><th>Fijos est.</th><th>Pago</th><th>Saldo fin</th><th>Progreso</th></tr></thead>
        <tbody id="amex-proj-body"></tbody>
      </table>
    </div>
    <h3 style="margin:.5rem 0 .75rem;font-size:.95rem;color:#64748b">Estados de cuenta</h3>
    <div class="amex-accordion" id="amex-accordion"></div>
  </div>

  <!-- Plan Quincenal -->
  <div class="section" id="pq-section">
    <h2>📋 Plan quincenal <span style="font-size:10px;color:#22c55e;background:rgba(34,197,94,.1);padding:2px 8px;border-radius:99px;vertical-align:middle">activo desde 13-Jul</span></h2>
    <div id="pq-wrap"><div class="loading-msg">Cargando...</div></div>
  </div>

  <!-- Liquidez -->
  <div class="section" id="liquidez-section">
    <h2>💵 Liquidez</h2>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px">
      <div class="liq-saldo" id="liq-total">—</div>
      <div style="font-size:11px;color:#64748b">total disponible</div>
    </div>
    <div id="liq-breakdown" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px"></div>
    <div class="liq-hero">
      <div class="liq-saldo" id="liq-saldo" style="font-size:20px">—</div>
      <div class="liq-banco" id="liq-banco"></div>
    </div>
    <div class="flujo-grid" id="flujo-grid" style="display:none">
      <div class="flujo-item">
        <div class="flujo-label">Ingresos/mes</div>
        <div class="flujo-val" style="color:#22c55e" id="flujo-ing">—</div>
      </div>
      <div class="flujo-item">
        <div class="flujo-label">Obligaciones</div>
        <div class="flujo-val" style="color:#ef4444" id="flujo-oblig">—</div>
      </div>
      <div class="flujo-item">
        <div class="flujo-label">MultiMoney</div>
        <div class="flujo-val" style="color:#0ea5e9" id="flujo-mm">—</div>
      </div>
      <div class="flujo-item">
        <div class="flujo-label">Remanente</div>
        <div class="flujo-val" id="flujo-rem">—</div>
      </div>
    </div>
    <div class="mov-list" id="mov-list"></div>
    <div id="otras-cuentas-wrap" style="display:none;margin-top:10px"></div>
  </div>

  <!-- Calendario de pagos -->
  <div class="section">
    <h2>📆 Calendario de pagos mensual</h2>
    <div class="cal-pago-list" id="cal-pago-list"><div class="loading-msg">Cargando...</div></div>
    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
      <div class="fi-total" style="flex:1;margin-top:0">
        <span class="fi-total-label">Total egresos/mes</span>
        <span class="fi-total-val" style="color:#ef4444" id="cal-total-egresos">—</span>
      </div>
      <div class="fi-total" style="flex:1;margin-top:0">
        <span class="fi-total-label">Total ahorro/mes</span>
        <span class="fi-total-val" style="color:#22c55e" id="cal-total-ahorro">—</span>
      </div>
    </div>
  </div>

  <!-- Tarjetas de crédito -->
  <div class="section">
    <h2>💳 Tarjetas de crédito</h2>
    <div class="tc-grid" id="tc-grid"><div class="loading-msg">Cargando...</div></div>
    <div class="fi-total">
      <span class="fi-total-label">Total saldo tarjetas</span>
      <span class="fi-total-val" id="tc-total">—</span>
    </div>
    <div class="fi-total" style="margin-top:6px">
      <span class="fi-total-label">Pagos mínimos / mes</span>
      <span class="fi-total-val" id="tc-min-total">—</span>
    </div>
  </div>

  <!-- Calendario — mejor tarjeta para usar -->
  <div class="section" id="cal-section">
    <h2>📅 Mejor tarjeta para usar hoy</h2>
    <div class="cal-grid" id="cal-grid"><div class="loading-msg">Cargando...</div></div>
  </div>

  <!-- Compras a plazos / Extrafinanciamientos -->
  <div class="section" id="fi-section" style="display:none">
    <h2>🏦 Compras a plazos <span style="font-size:10px;color:#0ea5e9;background:rgba(14,165,233,.1);padding:2px 8px;border-radius:99px;vertical-align:middle">cuotas activas</span></h2>
    <div class="fi-grid" id="fi-grid"></div>
    <div class="fi-total">
      <span class="fi-total-label">Deuda total financiamientos</span>
      <span class="fi-total-val" id="fi-total-saldo">—</span>
    </div>
    <div class="fi-total" style="margin-top:6px">
      <span class="fi-total-label">Cuota mensual combinada</span>
      <span class="fi-total-val" id="fi-total-cuota">—</span>
    </div>
  </div>

  <!-- Préstamos fijos -->
  <div class="section" id="prestamos-section" style="display:none">
    <h2>🏛️ Préstamos fijos</h2>
    <div id="prestamos-list"></div>
  </div>

  <!-- Fondo de emergencia -->
  <div class="section" id="fondo-section" style="display:none">
    <h2>🛡️ Fondo de emergencia <span style="font-size:10px;color:#22c55e;background:rgba(34,197,94,.1);padding:2px 8px;border-radius:99px;vertical-align:middle">intocable</span></h2>
    <div id="fondo-list"></div>
  </div>

  <!-- Fondos Esporádicos -->
  <div class="section" id="fe-section">
    <h2>🎯 Fondos esporádicos <span style="font-size:10px;color:#a5b4fc;background:rgba(99,102,241,.1);padding:2px 8px;border-radius:99px;vertical-align:middle">acumulan en MultiMoney · $40/quincena</span></h2>
    <div class="fe-grid" id="fe-grid"><div class="loading-msg">Cargando...</div></div>
    <div class="fi-total" style="margin-top:10px">
      <span class="fi-total-label">Total fondos acumulados</span>
      <span class="fi-total-val" style="color:#a5b4fc" id="fe-total-saldo">—</span>
    </div>
    <div class="fi-total" style="margin-top:6px">
      <span class="fi-total-label">Aportación por quincena</span>
      <span class="fi-total-val" style="color:#64748b;font-size:13px" id="fe-total-q">—</span>
    </div>
  </div>

  <!-- Gastos Fijos AMEX -->
  <div class="section" id="gf-section">
    <h2>💳 Gastos fijos en AMEX <span style="font-size:10px;color:#e4002b;background:rgba(228,0,43,.1);padding:2px 8px;border-radius:99px;vertical-align:middle">····3328</span></h2>
    <div id="gf-wrap"><div class="loading-msg">Cargando...</div></div>
    <div class="amex-payoff" style="margin-top:12px">
      <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Objetivo AMEX</div>
      <div class="amex-payoff-saldo" id="amex-saldo-actual">—</div>
      <div class="amex-payoff-meta">
        Pagando <strong style="color:#f59e0b">$125/quincena</strong> ($250/mes) → liquidar saldo revolving en ~5 meses (Nov 2026)<br>
        Interés mensual: ~$14/mes al 3.59%/mes · A partir de May 2027 baja carga en ~$36/mes (Laptop + Curacao terminan)
      </div>
    </div>
  </div>

  <!-- Recomendaciones financieras -->
  <div class="section" id="rec-section">
    <h2>💡 Recomendaciones financieras</h2>
    <div id="rec-list"><div class="loading-msg">Cargando...</div></div>
  </div>

  <!-- Presupuesto BAC diario -->
  <div class="section">
    <h2>📊 Presupuesto BAC — hasta el 13-Jul</h2>
    <div id="presupuesto-wrap"><div class="loading-msg">Cargando...</div></div>
  </div>

  <!-- Efectivo en mano -->
  <div class="section">
    <h2>💵 Efectivo en mano</h2>
    <div id="efectivo-wrap">
      <div class="loading-msg">Cargando...</div>
    </div>
  </div>

  <!-- Notas para Claude -->
  <div class="section">
    <h2>✏️ Notas para Claude</h2>
    <p style="font-size:12px;color:#64748b;margin-bottom:10px">
      Escribe correcciones o movimientos nuevos. Cuando me avises, leo esto y aplico los cambios.
    </p>
    <textarea class="notas-area" id="notas-text" placeholder="Ej: Pagué $60.87 a VISA Agrícola hoy&#10;Ej: Nuevo ingreso $200 freelance&#10;Ej: Cuota Curacao subió a $22.00"></textarea>
    <div class="notas-footer">
      <span class="notas-hint">Ctrl+Enter para guardar</span>
      <div style="display:flex;align-items:center;gap:10px">
        <span class="notas-saved" id="notas-saved">✓ Guardado</span>
        <button class="notas-btn" id="notas-btn" onclick="guardarNotas()">Guardar</button>
      </div>
    </div>
  </div>

  <!-- Resumen total -->
  <div class="section" id="totals-section">
    <h2>📊 Resumen total</h2>
    <div class="tot-section-title">Deuda</div>
    <table class="tot-table">
      <tr><td>Tarjetas de crédito</td><td class="tot-val" id="tot-cards">—</td></tr>
      <tr><td>Compras a plazos</td><td class="tot-val" id="tot-fi">—</td></tr>
      <tr><td>Préstamos</td><td class="tot-val" id="tot-prestamos">—</td></tr>
      <tr><td>TOTAL DEUDA</td><td class="tot-val" id="tot-total">—</td></tr>
    </table>
    <div class="tot-section-title">Obligaciones mensuales fijas</div>
    <table class="tot-table">
      <tr><td>Tarjetas (mínimos)</td><td class="tot-val" id="tot-min">—</td></tr>
      <tr><td>Compras a plazos</td><td class="tot-val" id="tot-cuota-fi">—</td></tr>
      <tr><td>Préstamos</td><td class="tot-val" id="tot-cuota-p">—</td></tr>
      <tr><td>TOTAL MENSUAL</td><td class="tot-val" id="tot-mensual">—</td></tr>
    </table>
  </div>

</div>

<div class="toast" id="toast"></div>

<script>
function fmt(n) { return '$' + parseFloat(n).toFixed(2); }

let _totCards = 0, _totFi = 0, _totPrestamos = 0;
let _minCards = 0, _cuotaFi = 0, _cuotaP = 0;

function updateTotals() {
  const gran = _totCards + _totFi + _totPrestamos;
  const mensual = _minCards + _cuotaFi + _cuotaP;
  document.getElementById('tot-cards').textContent = fmt(_totCards);
  document.getElementById('tot-fi').textContent = fmt(_totFi);
  document.getElementById('tot-prestamos').textContent = fmt(_totPrestamos);
  document.getElementById('tot-total').textContent = fmt(gran);
  document.getElementById('tot-min').textContent = fmt(_minCards);
  document.getElementById('tot-cuota-fi').textContent = fmt(_cuotaFi);
  document.getElementById('tot-cuota-p').textContent = fmt(_cuotaP);
  document.getElementById('tot-mensual').textContent = fmt(mensual);
}

function renderCards(data) {
  if (!data || data.error) {
    document.getElementById('tc-grid').innerHTML = '<div class="loading-msg">Error al cargar tarjetas</div>';
    return;
  }
  _totCards = data.total_balance;
  _minCards = data.total_min;

  const COLORS = { 'BAC': '#e4002b', 'Agrícola': '#22c55e', 'Cuscatlán': '#0ea5e9' };
  function cardColor(name) {
    for (const [k, v] of Object.entries(COLORS)) if (name.includes(k)) return v;
    return '#64748b';
  }

  const grid = document.getElementById('tc-grid');
  grid.innerHTML = data.cards.map(c => {
    const color = cardColor(c.name);
    const isPaid = c.balance === 0;
    const isNever = c.payoff.never;
    const payoffColor = isPaid ? '#22c55e' : isNever ? '#ef4444' : '#f59e0b';
    const payoffIcon = isPaid ? '✓' : isNever ? '⚠️' : '→';
    return `<div class="tc-card" style="border-left:3px solid ${color}">
      <div class="tc-header">
        <span class="tc-name" style="color:${color}">${c.name}</span>
        <span class="tc-last4">····${c.last4}</span>
      </div>
      <div class="tc-balance" style="color:${isPaid?'#22c55e':'#e2e8f0'}">${fmt(c.balance)}</div>
      <div class="tc-meta">${c.tasa_anual}% anual · mín ${fmt(c.min_pago)}/mes</div>
      <div class="tc-payoff" style="color:${payoffColor}">${payoffIcon} ${c.payoff.label}</div>
    </div>`;
  }).join('');

  document.getElementById('tc-total').textContent = fmt(data.total_balance);
  document.getElementById('tc-min-total').textContent = fmt(data.total_min) + '/mes';
  updateTotals();
}

function renderFinanciamientos(data) {
  if (!data || !data.items || !data.items.length) return;
  _totFi = data.total_saldo;
  _cuotaFi = data.total_cuota;
  const section = document.getElementById('fi-section');
  section.style.display = 'block';
  document.getElementById('fi-total-saldo').textContent = fmt(data.total_saldo);
  document.getElementById('fi-total-cuota').textContent = fmt(data.total_cuota) + '/mes';
  const grid = document.getElementById('fi-grid');
  const bancoColor = { 'BAC': '#e4002b', 'Cuscatlán': '#004b87', 'Agrícola': '#2b7a3c', 'Curacao': '#a855f7' };
  grid.innerHTML = data.items.map(fi => {
    const isNear = fi.cuotas_restantes <= 3;
    const banco = fi.banco || 'Otro';
    const color = bancoColor[banco] || '#64748b';
    const cardChip = fi.tarjeta_last4
      ? `<span style="font-size:10px;color:${color};background:${color}22;padding:1px 6px;border-radius:99px;margin-left:4px">···${fi.tarjeta_last4}</span>`
      : '';
    const tasaText = fi.tasa_mensual > 0 ? `· ${fi.tasa_mensual}%/mes` : '· 0% interés';
    return `<div class="fi-card${isNear?' urgent':''}" style="border-left:3px solid ${color}">
      <div class="fi-ref" style="display:flex;align-items:center;gap:4px">
        <span style="font-size:10px;color:${color};font-weight:700">${banco}</span>${cardChip}
        <span style="margin-left:auto;font-size:10px;color:#64748b">Ref ${fi.ref}</span>
      </div>
      <div class="fi-desc">${fi.descripcion}</div>
      <div class="fi-cuota">${fmt(fi.cuota_mensual)} <span>/mes</span></div>
      <div class="fi-progress">
        <div class="fi-progress-bar${isNear?' near':''}" style="width:${fi.progress_pct}%"></div>
      </div>
      <div class="fi-meta">
        <span>${fi.cuotas_pagadas}/${fi.cuotas_total} cuotas</span>
        <span>${fi.cuotas_restantes} restantes → ${fi.payoff_label}</span>
      </div>
      <div class="fi-saldo">Saldo: <strong>${fmt(fi.saldo_actual)}</strong>
        <span style="color:#64748b;font-size:10px"> ${tasaText}</span>
      </div>
    </div>`;
  }).join('');
  updateTotals();
}

function renderFondos(data) {
  if (!data) return;
  const { fondos = [], prestamos = [] } = data;
  if (prestamos.length) {
    _totPrestamos = prestamos.reduce((s, p) => s + p.saldo, 0);
    _cuotaP = prestamos.reduce((s, p) => s + p.cuota_mensual, 0);
    document.getElementById('prestamos-section').style.display = 'block';
    document.getElementById('prestamos-list').innerHTML = prestamos.map(p => `
      <div class="prestamo-row">
        <div>
          <div class="prestamo-name">${p.nombre}</div>
          <div class="prestamo-meta">Saldo: ${fmt(p.saldo)} · ${p.tasa_anual}% anual · vence día ${p.fecha_pago_dia}</div>
          <div class="prestamo-meta">~${p.cuotas_restantes} cuotas restantes (${Math.round(p.cuotas_restantes/12*10)/10} años)</div>
        </div>
        <div class="prestamo-cuota">
          <div class="amount">${fmt(p.cuota_quincenal)}</div>
          <div class="per">/quincena</div>
          <div class="per" style="color:#94a3b8">${fmt(p.cuota_mensual)}/mes</div>
        </div>
      </div>`).join('');
    updateTotals();
  }
  if (fondos.length) {
    document.getElementById('fondo-section').style.display = 'block';
    document.getElementById('fondo-list').innerHTML = fondos.map(f => `
      <div class="fondo-card">
        <div>
          <div class="fondo-label">${f.nombre} · ${f.banco}</div>
          <div class="fondo-balance">${fmt(f.saldo)}</div>
          <div class="fondo-meta">+${fmt(f.ganancia_mensual)}/mes · +${fmt(f.ganancia_anual)}/año</div>
          ${f.intocable ? '<span class="fondo-intocable">🔒 colchón intocable</span>' : ''}
        </div>
        <div class="fondo-right">
          <div class="fondo-tasa">${f.tasa_anual}%</div>
          <div style="font-size:10px;color:#64748b">anual</div>
        </div>
      </div>`).join('');
  }
}

function renderCalendario(data) {
  if (!data || data.error) {
    document.getElementById('cal-grid').innerHTML = '<div class="loading-msg">Error al cargar</div>';
    return;
  }
  const COLORS = { 'BAC': '#e4002b', 'Agrícola': '#22c55e', 'Cuscatlán': '#0ea5e9' };
  function cardColor(name) {
    for (const [k, v] of Object.entries(COLORS)) if (name.includes(k)) return v;
    return '#64748b';
  }
  const cards = data.cards;
  const maxDays = Math.max(...cards.map(c => c.days_until_payment));
  const grid = document.getElementById('cal-grid');
  grid.innerHTML = cards.map((c, i) => {
    const color = cardColor(c.name);
    const isBest = i === 0 && c.safe_to_use;
    const pct = maxDays > 0 ? Math.round(c.days_until_payment / maxDays * 100) : 0;
    const barColor = c.has_balance ? '#ef4444' : (c.days_until_payment > 45 ? '#22c55e' : '#f59e0b');
    return `<div class="cal-card${isBest?' best':''}${c.has_balance?' has-balance':''}" style="border-left:3px solid ${color}">
      ${isBest ? '<span class="cal-best-badge">✓ Recomendada</span>' : ''}
      <div class="cal-name" style="color:${color}">${c.name}</div>
      <div class="cal-last4">····${c.last4}</div>
      <div class="cal-balance" style="color:${c.has_balance?'#ef4444':'#22c55e'}">${fmt(c.balance)}</div>
      <div class="cal-dates">
        <div class="cal-date-box">
          <div class="cal-date-lbl">Fecha de corte</div>
          <div class="cal-date-val">${c.next_cut_label}</div>
          <div class="cal-days">en ${c.days_until_cut}d</div>
        </div>
        <div class="cal-date-box">
          <div class="cal-date-lbl">Fecha de pago</div>
          <div class="cal-date-val">${c.next_payment_label}</div>
          <div class="cal-days">en ${c.days_until_payment}d</div>
        </div>
      </div>
      <div class="cal-grace-bar">
        <div class="cal-grace-fill" style="width:${pct}%;background:${barColor}"></div>
      </div>
      ${c.has_balance
        ? `<div class="cal-warning">⚠️ Saldo pendiente — compras nuevas generan interés de inmediato</div>`
        : `<div class="cal-tip">✓ Sin saldo — gracia completa hasta ${c.next_payment_label} (${c.days_until_payment} días)</div>`
      }
    </div>`;
  }).join('');
}

const _liq = {};
function _recalcLiqTotal() {
  const total = Object.values(_liq).reduce((s, v) => s + v.saldo, 0);
  const el = document.getElementById('liq-total');
  if (el) el.textContent = fmt(total);
  const bd = document.getElementById('liq-breakdown');
  if (bd) bd.innerHTML = Object.values(_liq).map(v =>
    `<span style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:6px;
                  padding:3px 8px;font-size:11px;color:#94a3b8">
      <span style="color:#e2e8f0;font-weight:700">${v.label}</span>
      <span style="color:${v.saldo>0?'#22c55e':'#64748b'};margin-left:4px">$${v.saldo.toFixed(2)}</span>
    </span>`
  ).join('');
}

function renderCuenta(data) {
  if (!data || data.error) return;
  _liq['cc'] = { label: data.banco, saldo: data.saldo };
  _recalcLiqTotal();
  document.getElementById('liq-saldo').textContent = fmt(data.saldo);
  document.getElementById('liq-banco').textContent = 'Agrícola CC';

  // Cash flow breakdown
  const fg = document.getElementById('flujo-grid');
  fg.style.display = 'grid';
  document.getElementById('flujo-ing').textContent = fmt(data.ingreso_mensual);
  document.getElementById('flujo-oblig').textContent = fmt(data.obligaciones_mes);
  document.getElementById('flujo-mm').textContent = fmt(data.multimoney_mes || 0);
  const rem = data.remanente_mes || 0;
  const remEl = document.getElementById('flujo-rem');
  remEl.textContent = fmt(rem);
  remEl.style.color = rem >= 0 ? '#22c55e' : '#ef4444';

  const movs = data.movimientos || [];
  if (!movs.length) {
    document.getElementById('mov-list').innerHTML = '<div style="color:#64748b;font-size:12px;padding:6px 0">Sin movimientos registrados</div>';
    return;
  }
  document.getElementById('mov-list').innerHTML = movs.map(m => {
    const isIng = m.tipo === 'ingreso';
    return `<div class="mov-row">
      <span class="mov-date">${m.fecha}</span>
      <span class="mov-desc">${m.descripcion}</span>
      <span class="mov-monto ${m.tipo}">${isIng ? '+' : '−'}${fmt(m.monto)}</span>
    </div>`;
  }).join('');
}

function pagoKey(e) {
  return 'pago_' + e.dia + '_' + e.descripcion.replace(/\s+/g,'_');
}
function pagoChecks() {
  const k = 'pagos_check_' + new Date().toISOString().slice(0,7);
  try { return JSON.parse(localStorage.getItem(k) || '{}'); } catch { return {}; }
}
function savePagoCheck(key, val) {
  const k = 'pagos_check_' + new Date().toISOString().slice(0,7);
  const checks = pagoChecks();
  if (val) checks[key] = true; else delete checks[key];
  localStorage.setItem(k, JSON.stringify(checks));
}
function togglePago(key) {
  const checks = pagoChecks();
  const nowDone = !checks[key];
  savePagoCheck(key, nowDone);
  const row = document.querySelector(`[data-pago-key="${key}"]`);
  if (!row) return;
  const cb = row.querySelector('.cal-check');
  if (nowDone) { row.classList.add('done'); if(cb) cb.checked = true; }
  else { row.classList.remove('done'); if(cb) cb.checked = false; }
}

function renderCalendarioPagos(data) {
  if (!data || data.error) {
    document.getElementById('cal-pago-list').innerHTML = '<div class="loading-msg">Error al cargar.</div>';
    return;
  }
  const today = data.today_day;
  const checks = pagoChecks();
  const SUBTIPO_COLOR = { tarjeta: '#e4002b', intrafinanciamiento: '#0ea5e9', prestamo: '#f59e0b', extra: '#a855f7', ahorro: '#22c55e' };
  const SUBTIPO_ICON = { tarjeta: '💳', intrafinanciamiento: '🏦', prestamo: '🏛️', extra: '📚', ahorro: '💰' };

  document.getElementById('cal-pago-list').innerHTML = data.events.map(e => {
    const color = SUBTIPO_COLOR[e.subtipo] || '#64748b';
    const icon = SUBTIPO_ICON[e.subtipo] || '•';
    const isAhorro = e.tipo === 'deposito';
    const isPassed = e.passed;
    const isToday = e.dia === today;
    const isSoon = !isPassed && e.days_away <= 3;
    const key = pagoKey(e);
    const isDone = !!checks[key];
    let rowClass = isDone ? 'done' : isPassed ? 'passed' : isAhorro ? 'ahorro' : isToday ? 'today' : isSoon ? 'soon' : '';
    const montoColor = isAhorro ? '#22c55e' : '#ef4444';
    const prefix = isAhorro ? '+' : '−';
    return `<div class="cal-pago-row ${rowClass}" data-pago-key="${key}" onclick="togglePago('${key}')" style="cursor:pointer">
      <input type="checkbox" class="cal-check" ${isDone?'checked':''} onclick="event.stopPropagation();togglePago('${key}')">
      <div class="cal-dia-badge" style="${!isPassed&&!isDone?'background:'+color+'22;color:'+color:''}">${e.dia}</div>
      <div class="cal-pago-desc">
        <span>${icon} ${e.descripcion}</span>
        ${e.notas ? `<div class="cal-sub">${e.notas}</div>` : ''}
      </div>
      <div>
        <div class="cal-pago-monto" style="color:${isPassed||isDone?'#64748b':montoColor}">${prefix}${fmt(e.monto)}</div>
        <div class="cal-pago-next">${isDone ? '✓ hecho' : isPassed ? '✓ pasado' : e.next_label + ' ('+e.days_away+'d)'}</div>
      </div>
    </div>`;
  }).join('');

  document.getElementById('cal-total-egresos').textContent = fmt(data.total_egresos) + '/mes';
  document.getElementById('cal-total-ahorro').textContent = fmt(data.total_ahorro) + '/mes';
}

fetch('/api/plan/quincenal').then(r => r.json()).then(renderPlanQuincenal).catch(() => {});
fetch('/api/plan/fondos_esporadicos').then(r => r.json()).then(renderFondosEsporadicos).catch(() => {});
fetch('/api/plan/gastos_fijos_amex').then(r => r.json()).then(renderGastosFijosAmex).catch(() => {});
fetch('/api/amex/historial').then(r=>r.json()).then(renderAmexHistorial).catch(console.error);
fetch('/api/cuenta').then(r => r.json()).then(renderCuenta).catch(() => {});
fetch('/api/otras_cuentas').then(r => r.json()).then(data => {
  if (!Array.isArray(data) || !data.length) return;
  data.forEach(c => { _liq['oc_'+c.nombre] = { label: c.nombre, saldo: parseFloat(c.saldo) }; });
  _recalcLiqTotal();
  const wrap = document.getElementById('otras-cuentas-wrap');
  wrap.style.display = 'block';
  wrap.innerHTML = data.map(c => `
    <div style="display:flex;justify-content:space-between;align-items:center;
                background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;
                padding:10px 12px;font-size:12px">
      <div>
        <span style="font-weight:700;color:#a5b4fc">${c.nombre}</span>
        <span style="color:#64748b;margin-left:6px">${c.tipo}</span>
        ${c.notas ? `<div style="color:#64748b;font-size:10px;margin-top:2px">${c.notas}</div>` : ''}
      </div>
      <span style="font-size:16px;font-weight:700;color:#e2e8f0">$${parseFloat(c.saldo).toFixed(2)}</span>
    </div>`).join('');
}).catch(() => {});
fetch('/api/calendario_pagos').then(r => r.json()).then(renderCalendarioPagos).catch(() => {});
fetch('/api/plan/snapshot').then(r => r.json()).then(renderCards).catch(() => {});
fetch('/api/tarjetas/calendario').then(r => r.json()).then(renderCalendario).catch(() => {});
fetch('/api/plan/financiamientos').then(r => r.json()).then(renderFinanciamientos).catch(() => {});
fetch('/api/plan/fondos').then(r => r.json()).then(renderFondos).catch(() => {});

// Recomendaciones
fetch('/api/recomendaciones').then(r => r.json()).then(data => {
  if (!Array.isArray(data) || !data.length) {
    document.getElementById('rec-list').innerHTML = '<div class="loading-msg">Sin recomendaciones registradas.</div>';
    return;
  }
  const TIPO_ICON = { accion: '⚡', estrategia: '📈', ahorro: '💰', deuda: '💳', alerta: '⚠️', recordatorio: '📌' };
  const TIPO_COLOR = { accion: '#a5b4fc', estrategia: '#34d399', ahorro: '#22c55e', deuda: '#f59e0b', alerta: '#fca5a5', recordatorio: '#94a3b8' };
  const PRIO_COLOR = { alta: '#ef444433', media: '#f59e0b33', baja: '#22c55e33' };
  const PRIO_TEXT = { alta: '#fca5a5', media: '#fcd34d', baja: '#86efac' };
  document.getElementById('rec-list').innerHTML = data.map(r => {
    const icon = TIPO_ICON[r.tipo] || '•';
    const tc = TIPO_COLOR[r.tipo] || '#64748b';
    const pc = PRIO_COLOR[r.prioridad] || '';
    const pt = PRIO_TEXT[r.prioridad] || '#94a3b8';
    return `<div class="rec-card ${r.prioridad}">
      <div class="rec-header">
        <span class="rec-titulo">${icon} ${r.titulo}</span>
        <div class="rec-badges">
          <span class="rec-badge" style="background:${tc}22;color:${tc}">${r.tipo}</span>
          <span class="rec-badge" style="background:${pc};color:${pt}">${r.prioridad}</span>
        </div>
      </div>
      <div class="rec-fecha">${r.fecha}</div>
      <div class="rec-texto">${r.texto}</div>
    </div>`;
  }).join('');
}).catch(() => {
  document.getElementById('rec-list').innerHTML = '<div class="loading-msg">Error al cargar.</div>';
});

// Notas
fetch('/api/presupuesto_bac').then(r => r.json()).then(p => {
  const wrap = document.getElementById('presupuesto-wrap');
  if (!wrap || p.error) return;
  const pct = Math.min(100, Math.round((p.dias_transcurridos / p.dias_total) * 100));
  const gastoPct = Math.min(100, Math.round((p.gasto_periodo / p.saldo_inicio) * 100));
  const bajo = p.remanente >= 0;
  const verdColor = bajo ? '#22c55e' : '#ef4444';
  const movRows = (p.movimientos || []).map(m => {
    const isIng = m.tipo === 'ingreso';
    return `<div class="efectivo-row">
      <span class="ef-desc">${isIng?'↑':'↓'} ${m.descripcion}</span>
      <span class="ef-fecha">${m.fecha}</span>
      <span class="ef-monto" style="color:${isIng?'#22c55e':'#ef4444'}">${isIng?'+':'−'}$${m.monto.toFixed(2)}</span>
    </div>`;
  }).join('');
  wrap.innerHTML = `
    <div class="ppto-veredicto ${bajo?'ok':'over'}">
      <span>${bajo?'✓':'⚠'}</span>
      <span>Ayer: gastaste $${p.gasto_periodo.toFixed(2)} vs presupuesto $${p.presupuesto_diario.toFixed(2)}/día —
        ${bajo ? 'bajo presupuesto, remanente $'+p.remanente.toFixed(2) : 'excediste $'+Math.abs(p.remanente).toFixed(2)}</span>
    </div>
    <div class="ppto-grid">
      <div class="ppto-item">
        <div class="ppto-label">Presupuesto/día</div>
        <div class="ppto-val" style="color:#e2e8f0">$${p.presupuesto_diario.toFixed(2)}</div>
      </div>
      <div class="ppto-item">
        <div class="ppto-label">Saldo actual BAC</div>
        <div class="ppto-val" style="color:#22c55e">$${p.saldo_actual.toFixed(2)}</div>
      </div>
      <div class="ppto-item">
        <div class="ppto-label">Días restantes</div>
        <div class="ppto-val" style="color:#a5b4fc">${p.dias_restantes}d</div>
      </div>
      <div class="ppto-item">
        <div class="ppto-label">Proyección/día</div>
        <div class="ppto-val" style="color:${p.proyeccion_diaria<=p.presupuesto_diario?'#22c55e':'#f59e0b'}">$${p.proyeccion_diaria.toFixed(2)}</div>
      </div>
    </div>
    <div class="ppto-bar-wrap">
      <div class="ppto-bar" style="width:${gastoPct}%;background:${bajo?'#22c55e':'#ef4444'}"></div>
    </div>
    <div class="ppto-bar-label">
      <span>Gasto: $${p.gasto_periodo.toFixed(2)} de $${p.saldo_inicio.toFixed(2)}</span>
      <span>Días: ${p.dias_transcurridos}/${p.dias_total}</span>
    </div>
    ${movRows ? '<div class="efectivo-mov" style="margin-top:10px">'+movRows+'</div>' : ''}
    <div style="font-size:10px;color:#64748b;margin-top:8px">
      Remanente acumulado: <strong style="color:${verdColor}">$${p.remanente.toFixed(2)}</strong>
      ${bajo ? '→ disponible para ahorros o pago de tarjetas' : '→ reajustar los días restantes'}
    </div>`;
}).catch(() => {});

fetch('/api/efectivo').then(r => r.json()).then(data => {
  const wrap = document.getElementById('efectivo-wrap');
  if (!wrap) return;
  const saldo = data.saldo || 0;
  _liq['efectivo'] = { label: 'Efectivo', saldo };
  _recalcLiqTotal();
  const movs = data.movimientos || [];
  wrap.innerHTML = `
    <div class="efectivo-saldo">$${saldo.toFixed(2)}</div>
    <div class="efectivo-mov">${movs.map(m => {
      const isIngreso = m.tipo === 'ingreso';
      return `<div class="efectivo-row">
        <span class="ef-desc">${isIngreso ? '↑' : '↓'} ${m.descripcion}</span>
        <span class="ef-fecha">${m.fecha}</span>
        <span class="ef-monto" style="color:${isIngreso?'#22c55e':'#ef4444'}">${isIngreso?'+':'−'}$${m.monto.toFixed(2)}</span>
      </div>`;
    }).join('')}</div>`;
}).catch(() => {});

// Plan Quincenal
function renderPlanQuincenal(data) {
  const wrap = document.getElementById('pq-wrap');
  if (!wrap || data.error || !data.distribucion) { if(wrap) wrap.innerHTML='<div class="loading-msg">Sin plan configurado</div>'; return; }
  const TIPO_COLOR = {obligacion:'#ef4444',deuda:'#f59e0b',ahorro:'#22c55e',operativo:'#0ea5e9',colchon:'#a855f7'};
  const dist = data.distribucion;
  const totalQ = dist.reduce((s,d)=>s+d.quincenal,0);
  const totalM = dist.reduce((s,d)=>s+d.mensual,0);
  wrap.innerHTML = `
    <div style="font-size:12px;color:#64748b;margin-bottom:10px">
      Salario quincena: <strong style="color:#22c55e">$${(data.salario_quincena||0).toFixed(2)}</strong>
      &nbsp;·&nbsp;vigente desde <strong style="color:#a5b4fc">${data.fecha_inicio||'—'}</strong>
    </div>
    <table class="pq-table">
      <thead><tr><th>Destino</th><th style="text-align:right">Quincenal</th><th style="text-align:right">Mensual</th></tr></thead>
      <tbody>
        ${dist.map(d=>`<tr>
          <td><span class="pq-dot" style="background:${TIPO_COLOR[d.tipo]||'#64748b'}"></span>${d.destino}</td>
          <td style="text-align:right;font-weight:600">$${d.quincenal.toFixed(2)}</td>
          <td style="text-align:right;color:#64748b">$${d.mensual.toFixed(2)}</td>
        </tr>`).join('')}
        <tr class="total-row">
          <td>TOTAL</td>
          <td style="text-align:right;color:#a5b4fc">$${totalQ.toFixed(2)}</td>
          <td style="text-align:right;color:#a5b4fc">$${totalM.toFixed(2)}</td>
        </tr>
      </tbody>
    </table>`;
}

// Fondos Esporádicos
function renderFondosEsporadicos(data) {
  const grid = document.getElementById('fe-grid');
  const totalSaldoEl = document.getElementById('fe-total-saldo');
  const totalQEl = document.getElementById('fe-total-q');
  if (!grid || !data.fondos) return;
  if (totalSaldoEl) totalSaldoEl.textContent = '$' + (data.total_saldo||0).toFixed(2);
  if (totalQEl) totalQEl.textContent = '$' + (data.total_quincenal||0).toFixed(2) + '/quincena';
  grid.innerHTML = data.fondos.map(f => {
    const pct = f.quincenal > 0 ? Math.min(100, Math.round((f.saldo/f.quincenal)*100)) : 0;
    return `<div class="fe-card">
      <div class="fe-nombre">${f.nombre}</div>
      <div class="fe-saldo">$${f.saldo.toFixed(2)}</div>
      <div class="fe-bar-wrap"><div class="fe-bar" style="width:${pct}%"></div></div>
      <div class="fe-meta">Meta quincena: $${f.quincenal.toFixed(2)} · Mensual: $${f.mensual.toFixed(2)}</div>
    </div>`;
  }).join('');
}

// Gastos Fijos AMEX
function renderGastosFijosAmex(data) {
  const wrap = document.getElementById('gf-wrap');
  if (!wrap || !data.gastos) return;
  wrap.innerHTML = data.gastos.map(g => `
    <div class="gf-row">
      <span class="gf-desc">
        ${g.descripcion}
        ${g.variable ? '<span style="font-size:10px;color:#64748b"> (variable)</span>' : ''}
        ${g.cancelar ? '<span class="gf-cancelar-badge">⚠ cancelar</span>' : ''}
        ${g.notas&&g.cancelar ? '<span style="font-size:10px;color:#64748b"> — '+g.notas+'</span>' : ''}
      </span>
      <span class="gf-monto ${g.cancelar?'tachado':''}">$${g.monto_mensual.toFixed(2)}</span>
    </div>`).join('') +
    `<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
      <div class="fi-total" style="flex:1;margin-top:0">
        <span class="fi-total-label">Total activo/mes</span>
        <span class="fi-total-val" style="color:#e4002b">$${(data.total||0).toFixed(2)}</span>
      </div>
      <div class="fi-total" style="flex:1;margin-top:0">
        <span class="fi-total-label">Ahorro al cancelar Google</span>
        <span class="fi-total-val" style="color:#22c55e">$${((data.total_bruto||0)-(data.total||0)).toFixed(2)}/mes</span>
      </div>
    </div>`;
  // Update AMEX saldo display
  fetch('/api/plan/snapshot').then(r=>r.json()).then(snap => {
    const amex = (snap.cards||[]).find(c=>c.last4==='3328');
    const el = document.getElementById('amex-saldo-actual');
    if (el && amex) el.textContent = '$' + amex.balance.toFixed(2);
  }).catch(()=>{});
}

// AMEX Historial
function renderAmexHistorial(data) {
  const estado = data.estado_actual || {};
  const hist = data.historial || [];

  // Status badge
  const badge = document.getElementById('amex-saldo-badge');
  if (badge) badge.textContent = '$' + (estado.saldo || 0).toFixed(2);

  // Status grid
  const grid = document.getElementById('amex-status-grid');
  if (grid && estado.saldo !== undefined) {
    const ep = estado.estrategia_pago || {};
    grid.innerHTML = [
      {label: 'Saldo actual', value: '$' + estado.saldo.toFixed(2), color: '#e53e3e'},
      {label: 'Próximo corte', value: estado.fecha_corte_proximo || '—'},
      {label: 'Próximo pago', value: estado.fecha_pago_proximo || '—'},
      {label: 'Pago mensual', value: '$' + (ep.pago_mensual || 250).toFixed(2), color: '#22c55e'},
      {label: 'Fijos estimados', value: '$' + (ep.fijos_estimados_mes || 0).toFixed(2)},
    ].map(s => `<div class="amex-stat">
      <div class="amex-stat-label">${s.label}</div>
      <div class="amex-stat-value" style="${s.color ? 'color:' + s.color : ''}">${s.value}</div>
    </div>`).join('');
  }

  // Projection table
  const tbody = document.getElementById('amex-proj-body');
  if (tbody && estado.proyeccion_liquidacion) {
    const maxSaldo = (estado.proyeccion_liquidacion[0] && estado.proyeccion_liquidacion[0].saldo_inicio) || 1;
    tbody.innerHTML = estado.proyeccion_liquidacion.map(p => {
      const pct = Math.max(0, Math.min(100, (p.saldo_fin / maxSaldo) * 100));
      if (p.liquidada) {
        return `<tr><td>${p.mes}</td><td colspan="4"></td><td class="amex-proj-liquidada">✅ LIQUIDADA</td></tr>`;
      }
      return `<tr>
        <td>${p.mes}</td>
        <td>$${p.saldo_inicio.toFixed(2)}</td>
        <td>$${p.fijos_est.toFixed(2)}</td>
        <td style="color:#22c55e">-$${p.pago.toFixed(2)}</td>
        <td style="color:${p.saldo_fin < 100 ? '#22c55e' : '#e53e3e'}">$${p.saldo_fin.toFixed(2)}</td>
        <td><span class="amex-proj-bar-wrap"><span class="amex-proj-bar-fill" style="width:${pct}%"></span></span></td>
      </tr>`;
    }).join('');
  }

  // Accordion
  const acc = document.getElementById('amex-accordion');
  if (!acc) return;
  acc.innerHTML = [...hist].reverse().map((mes) => {
    const totalFijo = mes.transacciones.filter(t => t.tipo === 'fijo').reduce((s, t) => s + t.monto, 0);
    const totalVar = mes.transacciones.filter(t => t.tipo === 'variable').reduce((s, t) => s + t.monto, 0);
    const rows = mes.transacciones.map(t => `<tr class="${t.tipo === 'fijo' ? 'amex-tx-fijo' : ''}">
      <td>${t.descripcion}${t.cancelar ? '<span class="amex-tx-cancelar">⚠ cancelar</span>' : ''}</td>
      <td><span class="amex-cat-badge">${t.categoria}</span></td>
      <td>${t.tipo === 'fijo' ? 'Fijo' : 'Variable'}</td>
      <td style="text-align:right">$${t.monto.toFixed(2)}</td>
    </tr>`).join('');
    return `<div class="amex-acc-item">
      <button class="amex-acc-trigger" onclick="this.nextElementSibling.classList.toggle('open')">
        <span><strong>${mes.periodo}</strong> &nbsp; corte: ${mes.fecha_corte}</span>
        <span>Saldo al corte: <strong>$${mes.saldo_corte.toFixed(2)}</strong> &nbsp; ▾</span>
      </button>
      <div class="amex-acc-body">
        <div class="amex-acc-meta">
          <span>Saldo anterior: $${mes.saldo_anterior.toFixed(2)}</span>
          <span>Interés: $${mes.interes.toFixed(2)}</span>
          <span>Pago: ${mes.fecha_pago}</span>
        </div>
        <table class="amex-tx-table">
          <thead><tr><th>Descripción</th><th>Categoría</th><th>Tipo</th><th style="text-align:right">Monto</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="amex-period-totals">
          <span>Fijos: <strong>$${totalFijo.toFixed(2)}</strong></span>
          <span>Variables: <strong>$${totalVar.toFixed(2)}</strong></span>
          <span>Total: <strong>$${(totalFijo + totalVar + mes.interes).toFixed(2)}</strong></span>
        </div>
      </div>
    </div>`;
  }).join('');
}

const _NOTAS_KEY = 'finanzas_notas_v1';
fetch('/api/notas').then(r => r.json()).then(d => {
  const local = localStorage.getItem(_NOTAS_KEY) || '';
  const server = d.texto || '';
  const texto = server || local;
  if (texto) document.getElementById('notas-text').value = texto;
  if (!server && local) _postNotas(local);
}).catch(() => {
  const local = localStorage.getItem(_NOTAS_KEY) || '';
  if (local) document.getElementById('notas-text').value = local;
});

document.getElementById('notas-text').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) guardarNotas();
});

async function _postNotas(texto) {
  try {
    await fetch('/api/notas', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texto})
    });
  } catch(e) {}
}

async function guardarNotas() {
  const btn = document.getElementById('notas-btn');
  const saved = document.getElementById('notas-saved');
  const texto = document.getElementById('notas-text').value;
  btn.disabled = true;
  localStorage.setItem(_NOTAS_KEY, texto);
  try {
    const r = await fetch('/api/notas', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texto})
    });
    const d = await r.json();
    if (d.ok) {
      saved.style.display = 'inline';
      setTimeout(() => { saved.style.display = 'none'; }, 2500);
    }
  } catch(e) {
    saved.style.display = 'inline';
    setTimeout(() => { saved.style.display = 'none'; }, 2500);
  }
  btn.disabled = false;
}
</script>
</body>
</html>"""

EMAILS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📧 Correos</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 16px 20px;
            display: flex; align-items: center; gap: 12px; }
  .header a { color: #6366f1; text-decoration: none; font-size: 13px; }
  .header h1 { font-size: 17px; font-weight: 700; }
  .container { padding: 12px; max-width: 960px; margin: 0 auto; }
  .tabs { display: flex; gap: 0; margin-bottom: 12px; border-bottom: 1px solid #2a2d3e; overflow-x: auto; }
  .tab { background: none; border: none; color: #64748b; padding: 9px 11px; font-size: 12px;
         cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px;
         white-space: nowrap; flex-shrink: 0; }
  @media(min-width:480px){ .tab { padding: 10px 16px; font-size: 13px; } }
  .tab.active { color: #6366f1; border-bottom-color: #6366f1; font-weight: 600; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px;
          padding: 0; margin-bottom: 12px; overflow: hidden; }
  .card-inner { padding: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
  th { text-align: left; color: #64748b; font-weight: 500; padding: 8px 10px;
       border-bottom: 1px solid #2a2d3e; font-size: 11px; text-transform: uppercase;
       white-space: nowrap; }
  td { padding: 8px 10px; border-bottom: 1px solid #1e2130; vertical-align: middle;
       overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
  tr:hover td { background: rgba(99,102,241,0.04); }
  .col-fecha { width: 80px; }
  .col-de { width: 28%; }
  .col-asunto { width: 100%; }
  .col-extra { width: 120px; }
  @media(max-width:479px){ .col-extra { display: none; } }
  .badge { padding: 2px 7px; border-radius: 99px; font-size: 10px; font-weight: 600;
           background: rgba(99,102,241,0.15); color: #a5b4fc; white-space: nowrap; }
  .badge.green { background: rgba(34,197,94,0.15); color: #86efac; }
  .badge.red { background: rgba(239,68,68,0.15); color: #fca5a5; }
  .stat-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; }
  @media(min-width:600px){ .stat-grid { grid-template-columns: repeat(4,1fr); } }
  .stat-card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 10px; padding: 14px; }
  .stat-card .name { font-size: 11px; color: #64748b; margin-bottom: 4px; text-transform: uppercase; }
  .stat-card .count { font-size: 24px; font-weight: 700; color: #6366f1; }
  .stat-card .unread { font-size: 11px; color: #f59e0b; margin-top: 2px; }
  .loading { color: #64748b; font-size: 13px; padding: 24px; text-align: center; }
  .monto { font-weight: 600; color: #ef4444; }
  .monto.credit { color: #22c55e; }
</style>
</head>
<body>
<div class="header">
  <a href="/">← Inicio</a>
  <h1>📧 Correos</h1>
</div>
<div class="container">
  <div class="tabs">
    <button class="tab active" onclick="showTab('recientes',this)">Recientes</button>
    <button class="tab" onclick="showTab('sin-etiquetar',this)">Sin etiquetar</button>
    <button class="tab" onclick="showTab('financieros',this)">Financieros</button>
    <button class="tab" onclick="showTab('estadisticas',this)">Estadísticas</button>
  </div>

  <div id="tab-recientes" class="tab-content active">
    <div class="loading" id="load-recientes">Cargando...</div>
    <div class="card" style="display:none" id="table-recientes">
      <table>
        <thead><tr><th class="col-fecha">Fecha</th><th class="col-de">De</th><th class="col-asunto">Asunto</th><th class="col-extra">Etiqueta</th></tr></thead>
        <tbody id="body-recientes"></tbody>
      </table>
    </div>
  </div>

  <div id="tab-sin-etiquetar" class="tab-content">
    <div class="loading" id="load-sin-etiquetar">Cargando...</div>
    <div class="card" style="display:none" id="table-sin-etiquetar">
      <table>
        <thead><tr><th class="col-fecha">Fecha</th><th class="col-de">De</th><th class="col-asunto">Asunto</th><th class="col-extra">Snippet</th></tr></thead>
        <tbody id="body-sin-etiquetar"></tbody>
      </table>
    </div>
  </div>

  <div id="tab-financieros" class="tab-content">
    <div class="loading" id="load-financieros">Cargando...</div>
    <div class="card" style="display:none" id="table-financieros">
      <table>
        <thead><tr><th class="col-fecha">Fecha</th><th class="col-de">Banco</th><th class="col-asunto">Comercio</th><th class="col-extra">Tipo</th><th style="width:80px">Monto</th></tr></thead>
        <tbody id="body-financieros"></tbody>
      </table>
    </div>
  </div>

  <div id="tab-estadisticas" class="tab-content">
    <div class="loading" id="load-estadisticas">Cargando...</div>
    <div id="stats-content" style="display:none"></div>
  </div>
</div>

<script>
const loaded = {};

function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (!loaded[name]) { loadTab(name); loaded[name] = true; }
}

function shortDate(str) {
  if (!str) return '-';
  const m = str.match(/(\\d{1,2}\\s+\\w+\\s+\\d{4})/);
  return m ? m[1] : str.substring(0, 16);
}

function labelBadge(label) {
  return `<span class="badge">${label}</span>`;
}

async function loadTab(name) {
  try {
    if (name === 'recientes') {
      const data = await fetch('/api/emails/recent').then(r => r.json());
      if (data.error) { document.getElementById('load-recientes').textContent = 'Error: ' + data.error; return; }
      document.getElementById('load-recientes').style.display = 'none';
      document.getElementById('table-recientes').style.display = 'block';
      document.getElementById('body-recientes').innerHTML = data.map(e => `
        <tr>
          <td class="col-fecha">${shortDate(e.date)}</td>
          <td class="col-de" title="${e.from}">${e.from.replace(/<[^>]+>/g,'').substring(0,28)}</td>
          <td class="col-asunto" title="${e.subject}">${e.subject.substring(0,60)}</td>
          <td class="col-extra">${e.labels.length ? e.labels.map(l => labelBadge(l)).join(' ') : '<span style="color:#64748b;font-size:11px">—</span>'}</td>
        </tr>`).join('');
    }
    else if (name === 'sin-etiquetar') {
      const data = await fetch('/api/emails/unlabeled').then(r => r.json());
      if (data.error) { document.getElementById('load-sin-etiquetar').textContent = 'Error: ' + data.error; return; }
      document.getElementById('load-sin-etiquetar').style.display = 'none';
      document.getElementById('table-sin-etiquetar').style.display = 'block';
      document.getElementById('body-sin-etiquetar').innerHTML = data.length ? data.map(e => `
        <tr>
          <td class="col-fecha">${shortDate(e.date)}</td>
          <td class="col-de" title="${e.from}">${e.from.replace(/<[^>]+>/g,'').substring(0,28)}</td>
          <td class="col-asunto" title="${e.subject}">${e.subject.substring(0,60)}</td>
          <td class="col-extra" style="color:#64748b;font-size:11px">${e.snippet}</td>
        </tr>`).join('') : '<tr><td colspan="4" style="color:#64748b;padding:20px;text-align:center">Sin correos sin etiquetar</td></tr>';
    }
    else if (name === 'financieros') {
      const data = await fetch('/api/emails/financial').then(r => r.json());
      document.getElementById('load-financieros').style.display = 'none';
      document.getElementById('table-financieros').style.display = 'block';
      document.getElementById('body-financieros').innerHTML = data.slice(0,100).map(r => {
        const isIngreso = (r.tipo||'').includes('credito');
        return `<tr>
          <td class="col-fecha">${r.fecha_iso||'-'}</td>
          <td class="col-de"><span style="font-size:11px">${(r.banco||'').replace('Banco ','').substring(0,10)}</span></td>
          <td class="col-asunto">${r.comercio||r.descripcion?.substring(0,30)||'-'}</td>
          <td class="col-extra"><span style="color:${isIngreso?'#22c55e':'#ef4444'};font-size:10px;font-weight:600">${isIngreso?'▲':'▼'}</span> <span style="color:#64748b;font-size:10px">${r.tipo||'-'}</span></td>
          <td class="monto ${isIngreso?'credit':''}">$${parseFloat(r.monto||0).toFixed(2)}</td>
        </tr>`;
      }).join('');
    }
    else if (name === 'estadisticas') {
      const data = await fetch('/api/emails/label-stats').then(r => r.json());
      if (data.error) { document.getElementById('load-estadisticas').textContent = 'Error: ' + data.error; return; }
      document.getElementById('load-estadisticas').style.display = 'none';
      const cont = document.getElementById('stats-content');
      cont.style.display = 'block';
      cont.innerHTML = '<div class="stat-grid">' + data.map(s => `
        <div class="stat-card">
          <div class="name">${s.name}</div>
          <div class="count">${s.messages_total}</div>
          ${s.messages_unread ? `<div class="unread">${s.messages_unread} no leídos</div>` : ''}
        </div>`).join('') + '</div>';
    }
  } catch(e) {
    console.error(name, e);
  }
}

// Load first tab immediately
loaded['recientes'] = true;
loadTab('recientes');
</script>
</body>
</html>"""

DEUDAS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎯 Destructor de deudas</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 16px 20px;
            display: flex; align-items: center; gap: 12px; }
  .header a { color: #6366f1; text-decoration: none; font-size: 13px; flex-shrink: 0; }
  .header h1 { font-size: 17px; font-weight: 700; }
  .container { padding: 14px; max-width: 760px; margin: 0 auto; }
  .section { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px;
             padding: 18px; margin-bottom: 12px; }
  .section h2 { font-size: 13px; color: #64748b; text-transform: uppercase;
                letter-spacing: .06em; margin-bottom: 14px; }
  .loading { color: #64748b; font-size: 12px; }
  /* Budget summary */
  .budget-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 4px; }
  @media(min-width:480px) { .budget-grid { grid-template-columns: repeat(4, 1fr); } }
  .budget-item { background: #0f1117; border-radius: 8px; padding: 10px 12px; }
  .budget-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing:.04em; }
  .budget-val { font-size: 16px; font-weight: 700; margin-top: 3px; }
  /* Strategy cards */
  .strategy-grid { display: grid; gap: 10px; }
  @media(min-width:520px) { .strategy-grid { grid-template-columns: repeat(3, 1fr); } }
  .strategy-card { background: #0f1117; border: 1px solid #2a2d3e; border-radius: 10px;
                   padding: 14px; position: relative; transition: border-color .15s; }
  .strategy-card.recommended { border-color: #22c55e; box-shadow: 0 0 0 1px rgba(34,197,94,.25); }
  .strategy-badge { position: absolute; top: 10px; right: 10px; font-size: 10px; font-weight: 700;
                    padding: 2px 8px; border-radius: 99px; background: #22c55e; color: #0f1117;
                    text-transform: uppercase; letter-spacing: .04em; }
  .strategy-name { font-size: 13px; font-weight: 700; margin-bottom: 2px; }
  .strategy-desc { font-size: 10px; color: #64748b; margin-bottom: 10px; }
  .strategy-fecha { font-size: 20px; font-weight: 700; color: #e2e8f0; margin-bottom: 2px; }
  .strategy-meses { font-size: 11px; color: #64748b; margin-bottom: 8px; }
  .strategy-interes { font-size: 13px; font-weight: 700; }
  .strategy-interes span { font-size: 10px; color: #64748b; font-weight: 400; }
  /* Debt order list */
  .order-list { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
  .order-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
                background: #1a1d27; border-radius: 7px; font-size: 11px; }
  .order-num { width: 20px; height: 20px; border-radius: 50%; background: #2a2d3e;
               display: flex; align-items: center; justify-content: center; font-size: 10px;
               font-weight: 700; flex-shrink: 0; }
  .order-nombre { flex: 1; color: #e2e8f0; }
  .order-saldo { color: #ef4444; font-weight: 700; flex-shrink: 0; }
  .order-tasa { color: #64748b; flex-shrink: 0; }
  .order-liq { color: #f59e0b; font-size: 10px; flex-shrink: 0; text-align: right; }
  /* Detailed recommended */
  .debt-row { display: grid; grid-template-columns: 1fr auto auto auto;
              gap: 8px; align-items: center; padding: 10px 0;
              border-bottom: 1px solid #1e2130; font-size: 12px; }
  .debt-row:last-child { border-bottom: none; }
  .debt-nombre { font-weight: 600; }
  .debt-tipo { font-size: 10px; color: #64748b; margin-top: 1px; }
  .debt-saldo { font-weight: 700; color: #ef4444; text-align: right; }
  .debt-tasa { color: #f59e0b; font-size: 11px; text-align: right; }
  .debt-liq { font-size: 10px; color: #94a3b8; text-align: right; }
  /* Savings banner */
  .savings-banner { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.2);
                    border-radius: 10px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; }
  .savings-val { font-size: 22px; font-weight: 800; color: #22c55e; }
  .savings-text { font-size: 12px; color: #86efac; line-height: 1.5; }
</style>
</head>
<body>
<div class="header">
  <a href="/">← Inicio</a>
  <h1>🎯 Motor de destrucción de deudas</h1>
</div>
<div class="container">

  <div class="section">
    <h2>💰 Presupuesto mensual de pago</h2>
    <div class="budget-grid" id="budget-grid"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section">
    <h2>📊 Comparación de estrategias</h2>
    <div class="strategy-grid" id="strategy-grid"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section" id="rec-section" style="display:none">
    <h2 id="rec-title">✅ Estrategia recomendada — detalle por deuda</h2>
    <div id="rec-detail"></div>
  </div>

  <div class="section" id="savings-section" style="display:none">
    <h2>💡 Ahorro vs. pago mínimo</h2>
    <div id="savings-content"></div>
  </div>

</div>
<script>
function fmt(n) { return '$' + parseFloat(n||0).toFixed(2); }

const NOMBRES = {
  avalancha: 'Avalancha',
  bola_de_nieve: 'Bola de nieve',
  hibrida: 'Híbrida',
};
const DESCS = {
  avalancha: 'Mayor tasa de interés primero — minimiza el costo total',
  bola_de_nieve: 'Menor saldo primero — victorias rápidas y motivación',
  hibrida: 'Saldos pequeños primero, luego por tasa — balance práctico',
};
const COLORS = { avalancha: '#6366f1', bola_de_nieve: '#0ea5e9', hibrida: '#f59e0b' };

fetch('/api/deudas/estrategias').then(r => r.json()).then(d => {
  if (d.error) {
    document.getElementById('budget-grid').innerHTML = '<div class="loading">Error: ' + d.error + '</div>';
    return;
  }

  // Budget
  const totalDeuda = d.debts.reduce((s, x) => s + x.saldo, 0);
  document.getElementById('budget-grid').innerHTML = [
    ['Deuda total', fmt(totalDeuda), '#ef4444'],
    ['Ingreso mensual', fmt(d.ingreso_mensual), '#22c55e'],
    ['Pagos mínimos', fmt(d.total_min), '#f59e0b'],
    ['Presupuesto total', fmt(d.budget_total), '#6366f1'],
  ].map(([label, val, color]) =>
    '<div class="budget-item">' +
    '<div class="budget-label">' + label + '</div>' +
    '<div class="budget-val" style="color:' + color + '">' + val + '</div>' +
    '</div>'
  ).join('');

  // Strategy cards
  const keys = ['avalancha', 'bola_de_nieve', 'hibrida'];
  const interests = keys.map(k => d.estrategias[k].interes_total);
  const minInt = Math.min(...interests);

  document.getElementById('strategy-grid').innerHTML = keys.map(k => {
    const s = d.estrategias[k];
    const isRec = k === d.recomendada;
    const color = COLORS[k];
    const isCheapest = s.interes_total === minInt;
    const interestColor = isCheapest ? '#22c55e' : '#ef4444';
    const orderHtml = s.orden.map((item, i) =>
      '<div class="order-item">' +
      '<div class="order-num" style="background:' + color + '22;color:' + color + '">' + (i+1) + '</div>' +
      '<div class="order-nombre">' + item.nombre + '</div>' +
      '<div class="order-liq">' + item.liquidacion_label + '</div>' +
      '</div>'
    ).join('');
    return '<div class="strategy-card' + (isRec ? ' recommended' : '') + '">' +
      (isRec ? '<span class="strategy-badge">Recomendada</span>' : '') +
      '<div class="strategy-name" style="color:' + color + '">' + NOMBRES[k] + '</div>' +
      '<div class="strategy-desc">' + DESCS[k] + '</div>' +
      '<div class="strategy-fecha">' + s.liquidacion_label + '</div>' +
      '<div class="strategy-meses">' + s.meses + ' meses</div>' +
      '<div class="strategy-interes" style="color:' + interestColor + '">' + fmt(s.interes_total) +
        ' <span>en intereses</span></div>' +
      '<div class="order-list">' + orderHtml + '</div>' +
      '</div>';
  }).join('');

  // Recommended detail
  const rec = d.estrategias[d.recomendada];
  document.getElementById('rec-title').textContent =
    '✅ ' + NOMBRES[d.recomendada] + ' — orden de liquidación';
  document.getElementById('rec-section').style.display = 'block';
  document.getElementById('rec-detail').innerHTML = rec.orden.map((item, i) =>
    '<div class="debt-row">' +
    '<div><div class="debt-nombre">' + (i+1) + '. ' + item.nombre + '</div>' +
    '<div class="debt-tipo">Tasa: ' + item.tasa_anual + '% anual</div></div>' +
    '<div class="debt-saldo">' + fmt(item.saldo) + '</div>' +
    '<div class="debt-liq">Liquidación<br>' + item.liquidacion_label + '</div>' +
    '</div>'
  ).join('');

  // Savings vs min only (estimate: budget = total_min only)
  const maxInt = Math.max(...interests);
  const minInt2 = Math.min(...interests);
  const saving = round2(maxInt - minInt2);
  document.getElementById('savings-section').style.display = 'block';
  document.getElementById('savings-content').innerHTML =
    '<div class="savings-banner">' +
    '<div class="savings-val">' + fmt(saving) + '</div>' +
    '<div class="savings-text">Diferencia en intereses entre la peor y la mejor estrategia.<br>' +
    'Elige bien y ahorras ese dinero extra.</div>' +
    '</div>';
}).catch(e => {
  document.getElementById('budget-grid').innerHTML = '<div class="loading">Error de conexión</div>';
});

function round2(n) { return Math.round(n * 100) / 100; }
</script>
</body>
</html>"""


FUGAS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔍 Detector de fugas</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 16px 20px;
            display: flex; align-items: center; gap: 12px; }
  .header a { color: #6366f1; text-decoration: none; font-size: 13px; flex-shrink: 0; }
  .header h1 { font-size: 17px; font-weight: 700; }
  .container { padding: 14px; max-width: 760px; margin: 0 auto; }
  .section { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px;
             padding: 18px; margin-bottom: 12px; }
  .section h2 { font-size: 13px; color: #64748b; text-transform: uppercase;
                letter-spacing: .06em; margin-bottom: 14px; }
  .loading { color: #64748b; font-size: 12px; }
  /* Alert cards */
  .alert-card { background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
                border-radius: 10px; padding: 12px 14px; margin-bottom: 8px;
                display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .alert-icon { font-size: 20px; flex-shrink: 0; }
  .alert-info { flex: 1; }
  .alert-desc { font-size: 13px; font-weight: 700; color: #fca5a5; }
  .alert-meta { font-size: 11px; color: #94a3b8; margin-top: 2px; }
  .alert-monto { font-size: 18px; font-weight: 800; color: #ef4444; flex-shrink: 0; }
  .alert-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 99px;
                 background: #ef4444; color: white; text-transform: uppercase; letter-spacing: .04em; }
  /* Trend rows */
  .trend-row { display: flex; align-items: center; gap: 10px; padding: 10px 0;
               border-bottom: 1px solid #1e2130; }
  .trend-row:last-child { border-bottom: none; }
  .trend-cat { flex: 1; font-size: 13px; font-weight: 600; }
  .trend-prev { font-size: 11px; color: #64748b; flex-shrink: 0; }
  .trend-arrow { font-size: 11px; color: #64748b; flex-shrink: 0; }
  .trend-now { font-size: 13px; font-weight: 700; color: #f59e0b; flex-shrink: 0; }
  .trend-pct { font-size: 12px; font-weight: 700; color: #ef4444; flex-shrink: 0; min-width: 50px; text-align: right; }
  /* Bar chart */
  .bar-wrap { margin-top: 4px; }
  .bar-bg { background: #2a2d3e; border-radius: 99px; height: 4px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 99px; background: #f59e0b; }
  /* Subscriptions table */
  .sub-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px;
             border-radius: 8px; margin-bottom: 4px; background: #0f1117; }
  .sub-row.cancelar { background: rgba(239,68,68,.06); border: 1px solid rgba(239,68,68,.2); }
  .sub-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .sub-desc { flex: 1; font-size: 12px; font-weight: 600; }
  .sub-cat { font-size: 10px; color: #64748b; }
  .sub-meses { font-size: 10px; color: #64748b; flex-shrink: 0; }
  .sub-monto { font-size: 13px; font-weight: 700; color: #e2e8f0; flex-shrink: 0; }
  .sub-badge { font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 99px;
               background: #ef4444; color: white; flex-shrink: 0; }
  /* Category heatmap */
  .cat-table { width: 100%; border-collapse: collapse; font-size: 11px; overflow-x: auto; display: block; }
  .cat-table th { text-align: right; color: #64748b; padding: 4px 6px; white-space: nowrap;
                  border-bottom: 1px solid #2a2d3e; }
  .cat-table th:first-child { text-align: left; }
  .cat-table td { padding: 5px 6px; border-bottom: 1px solid #1a1d27; text-align: right; white-space: nowrap; }
  .cat-table td:first-child { text-align: left; color: #e2e8f0; font-weight: 500; min-width: 120px; }
  .cell-val { display: inline-block; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
  .empty { color: #2a2d3e; }
  .no-alerts { color: #64748b; font-size: 12px; padding: 8px 0; }
</style>
</head>
<body>
<div class="header">
  <a href="/">← Inicio</a>
  <h1>🔍 Detector de fugas de gastos</h1>
</div>
<div class="container">

  <div class="section" id="alertas-section">
    <h2>🚨 Alertas — suscripciones a cancelar</h2>
    <div id="alertas-wrap"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section" id="tendencias-section">
    <h2>📈 Categorías en alza (últimos 3 meses vs anteriores)</h2>
    <div id="tendencias-wrap"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section" id="sobre-section">
    <h2>⚠️ Gasto sobre el promedio histórico (último mes)</h2>
    <div id="sobre-wrap"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section" id="subs-section">
    <h2>🔄 Suscripciones activas (últimos 3 meses)</h2>
    <div id="subs-wrap"><div class="loading">Cargando...</div></div>
  </div>

  <div class="section" id="heatmap-section">
    <h2>📅 Gasto por categoría y mes (AMEX)</h2>
    <div id="heatmap-wrap" style="overflow-x:auto"><div class="loading">Cargando...</div></div>
  </div>

</div>
<script>
function fmt(n) { return '$' + parseFloat(n||0).toFixed(2); }

function heatColor(val, max) {
  if (!val || val === 0) return 'transparent';
  const pct = Math.min(val / max, 1);
  const r = Math.round(239 * pct);
  const g = Math.round(68 * pct);
  const b = Math.round(68 * pct);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + (0.12 + pct * 0.5) + ')';
}

fetch('/api/fugas').then(r => r.json()).then(d => {
  if (d.error) {
    document.getElementById('alertas-wrap').innerHTML = 'Error: ' + d.error;
    return;
  }

  // Alertas: suscripciones con cancelar:true
  const alertas = d.suscripciones.filter(s => s.cancelar);
  const alertasHtml = alertas.length
    ? alertas.map(s =>
        '<div class="alert-card">' +
        '<div class="alert-icon">⛔</div>' +
        '<div class="alert-info">' +
        '<div class="alert-desc">' + s.descripcion + '</div>' +
        '<div class="alert-meta">' + s.categoria + ' · activo ' + s.meses_activos + ' mes(es) recientes</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">' +
        '<div class="alert-monto">' + fmt(s.ultimo_monto) + '/mes</div>' +
        '<span class="alert-badge">CANCELAR</span>' +
        '</div>' +
        '</div>'
      ).join('')
    : '<div class="no-alerts">✅ No hay suscripciones marcadas para cancelar</div>';
  document.getElementById('alertas-wrap').innerHTML = alertasHtml;

  // Tendencias al alza
  const tendHtml = d.tendencias_al_alza.length
    ? d.tendencias_al_alza.map(t => {
        const maxAvg = Math.max(t.promedio_reciente, t.promedio_anterior);
        const fillPct = Math.round(t.promedio_reciente / maxAvg * 100);
        return '<div class="trend-row">' +
          '<div><div class="trend-cat">' + t.categoria + '</div>' +
          '<div class="bar-wrap"><div class="bar-bg"><div class="bar-fill" style="width:' + fillPct + '%"></div></div></div></div>' +
          '<div class="trend-prev">' + fmt(t.promedio_anterior) + '</div>' +
          '<div class="trend-arrow">→</div>' +
          '<div class="trend-now">' + fmt(t.promedio_reciente) + '</div>' +
          '<div class="trend-pct">+' + t.variacion_pct + '%</div>' +
          '</div>';
      }).join('')
    : '<div class="no-alerts">✅ Sin categorías con alza significativa</div>';
  document.getElementById('tendencias-wrap').innerHTML = tendHtml;

  // Sobre histórico
  const sobreHtml = d.sobre_historico.length
    ? d.sobre_historico.map(s =>
        '<div class="trend-row">' +
        '<div><div class="trend-cat">' + s.categoria + '</div>' +
        '<div style="font-size:10px;color:#64748b">Promedio histórico: ' + fmt(s.promedio_historico) + ' · ' + s.mes_actual_label + '</div></div>' +
        '<div class="trend-now">' + fmt(s.mes_actual) + '</div>' +
        '<div class="trend-pct">+' + s.variacion_pct + '%</div>' +
        '</div>'
      ).join('')
    : '<div class="no-alerts">✅ El último mes estuvo dentro del rango normal</div>';
  document.getElementById('sobre-wrap').innerHTML = sobreHtml;

  // Suscripciones activas
  const subsHtml = d.suscripciones.length
    ? d.suscripciones.map(s => {
        const dot = s.cancelar ? '#ef4444' : '#22c55e';
        return '<div class="sub-row' + (s.cancelar ? ' cancelar' : '') + '">' +
          '<div class="sub-dot" style="background:' + dot + '"></div>' +
          '<div><div class="sub-desc">' + s.descripcion + '</div>' +
          '<div class="sub-cat">' + s.categoria + '</div></div>' +
          '<div class="sub-meses">' + s.meses_activos + '/3 meses</div>' +
          '<div class="sub-monto">' + fmt(s.ultimo_monto) + '</div>' +
          (s.cancelar ? '<span class="sub-badge">CANCELAR</span>' : '') +
          '</div>';
      }).join('')
    : '<div class="no-alerts">Sin suscripciones detectadas</div>';
  document.getElementById('subs-wrap').innerHTML = subsHtml;

  // Heatmap by category and month
  const periodos = d.periodos;
  const monthly = d.monthly_cats;
  const allCats = [...new Set(periodos.flatMap(p => Object.keys(monthly[p] || {})))].sort();
  const maxVal = Math.max(...periodos.flatMap(p => Object.values(monthly[p] || {})));

  const headerRow = '<tr><th>Categoría</th>' + periodos.map(p => '<th>' + p.split(' ')[0].substring(0,3) + ' ' + p.split(' ')[1].slice(-2) + '</th>').join('') + '</tr>';
  const bodyRows = allCats.map(cat => {
    const cells = periodos.map(p => {
      const val = (monthly[p] || {})[cat] || 0;
      const bg = heatColor(val, maxVal);
      return val > 0
        ? '<td><span class="cell-val" style="background:' + bg + '">' + fmt(val) + '</span></td>'
        : '<td class="empty">—</td>';
    }).join('');
    return '<tr><td>' + cat + '</td>' + cells + '</tr>';
  }).join('');

  document.getElementById('heatmap-wrap').innerHTML =
    '<table class="cat-table"><thead>' + headerRow + '</thead><tbody>' + bodyRows + '</tbody></table>';

}).catch(() => {
  document.getElementById('alertas-wrap').innerHTML = '<div class="loading">Error de conexión</div>';
});
</script>
</body>
</html>"""


LOGS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Logs</title>
<style>
  body { background: #0f1117; color: #e2e8f0; font-family: -apple-system, sans-serif; margin: 0; }
  .header { background: #1a1d27; border-bottom: 1px solid #2a2d3e; padding: 16px;
            display: flex; align-items: center; gap: 12px; }
  .header a { color: #6366f1; text-decoration: none; font-size: 14px; }
  .header h1 { font-size: 16px; margin: 0; }
  .container { padding: 16px; max-width: 900px; margin: 0 auto; }
  select { width: 100%; background: #1a1d27; border: 1px solid #2a2d3e; color: #e2e8f0;
           padding: 8px 12px; border-radius: 8px; font-size: 14px; margin-bottom: 12px; }
  pre { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 8px;
        padding: 16px; font-size: 11px; overflow-x: auto; white-space: pre-wrap;
        word-break: break-all; color: #94a3b8; max-height: 70vh; overflow-y: auto; }
  .error { color: #ef4444; } .warn { color: #f59e0b; } .info { color: #94a3b8; }
</style>
</head>
<body>
<div class="header">
  <a href="/">← Inicio</a>
  <h1>📋 Logs del servidor</h1>
</div>
<div class="container">
  <form method="GET">
    <select name="f" onchange="this.form.submit()">
      {% for f in files %}
      <option value="{{ f }}" {% if f == current %}selected{% endif %}>{{ f }}</option>
      {% endfor %}
    </select>
  </form>
  <pre>{% for line in content.split('\\n') %}<span class="{% if '[ERROR]' in line %}error{% elif '[WARNING]' in line %}warn{% else %}info{% endif %}">{{ line }}
</span>{% endfor %}</pre>
</div>
</body>
</html>"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
