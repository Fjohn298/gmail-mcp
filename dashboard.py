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
    """Return cuenta_corriente balance and movements."""
    try:
        settings = load_settings()
        cuenta = settings.get('cuenta_corriente', {})
        movimientos = cuenta.get('movimientos', [])
        # Compute running balance from movements (most recent last → reverse for display)
        saldo = cuenta.get('saldo', 0)
        planner = settings.get('planner', {})
        cards = planner.get('cards', [])
        fi = settings.get('intrafinanciamientos', [])
        prestamos = settings.get('prestamos', [])
        salary_per_period = planner.get('salary_per_period', 0)
        ingreso_mensual = round(salary_per_period * 2, 2)
        obligaciones_mes = round(
            sum(c.get('min_pago', 0) for c in cards) +
            sum(i.get('cuota_mensual', 0) for i in fi) +
            sum(p.get('cuota_mensual', 0) for p in prestamos), 2
        )
        return jsonify({
            'saldo': saldo,
            'banco': cuenta.get('banco', ''),
            'movimientos': list(reversed(movimientos)),
            'salary_per_period': salary_per_period,
            'ingreso_mensual': ingreso_mensual,
            'obligaciones_mes': obligaciones_mes,
            'proyectado': round(saldo + ingreso_mensual - obligaciones_mes, 2)
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
  </div>
</div>
<script>
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
</style>
</head>
<body>
<div class="header">
  <a href="/">← Menú</a>
  <h1>🗓️ Estado de Deuda</h1>
</div>
<div class="container">

  <!-- Liquidez -->
  <div class="section" id="liquidez-section">
    <h2>💵 Liquidez — Cuenta corriente</h2>
    <div class="liq-hero">
      <div class="liq-saldo" id="liq-saldo">—</div>
      <div class="liq-banco" id="liq-banco"></div>
    </div>
    <div class="liq-proyectado">
      Proyectado fin de mes:
      <strong id="liq-proyectado">—</strong>
      <span style="font-size:11px;color:#64748b" id="liq-oblig"></span>
    </div>
    <div class="mov-list" id="mov-list"></div>
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

function renderCuenta(data) {
  if (!data || data.error) return;
  document.getElementById('liq-saldo').textContent = fmt(data.saldo);
  document.getElementById('liq-banco').textContent = data.banco;
  const proy = data.proyectado;
  document.getElementById('liq-proyectado').textContent = fmt(proy);
  document.getElementById('liq-proyectado').style.color = proy >= 0 ? '#22c55e' : '#ef4444';
  document.getElementById('liq-oblig').textContent =
    ` (+${fmt(data.ingreso_mensual)} ingresos − ${fmt(data.obligaciones_mes)} obligaciones)`;
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

fetch('/api/cuenta').then(r => r.json()).then(renderCuenta).catch(() => {});
fetch('/api/plan/snapshot').then(r => r.json()).then(renderCards).catch(() => {});
fetch('/api/tarjetas/calendario').then(r => r.json()).then(renderCalendario).catch(() => {});
fetch('/api/plan/financiamientos').then(r => r.json()).then(renderFinanciamientos).catch(() => {});
fetch('/api/plan/fondos').then(r => r.json()).then(renderFondos).catch(() => {});
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
