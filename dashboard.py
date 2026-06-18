import os
import csv
import json
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, session, redirect

app = Flask(__name__)
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
  <h1>Finanzas Jonathan</h1>
  <span class="badge" id="total-count">0 registros</span>
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

  tbody.innerHTML = data.slice(0, 200).map((r, i) => `
    <tr>
      <td>${r.fecha_iso || '-'}</td>
      <td>${bancoBadge(r.banco)}</td>
      <td>${r.comercio || r.descripcion?.substring(0,30) || '-'}</td>
      <td><span style="color:var(--muted);font-size:11px">${r.tipo || '-'}</span></td>
      <td class="monto ${(r.tipo||'').includes('credito') ? 'credit' : ''}">${fmt(r.monto)}</td>
      <td><button class="btn-edit" onclick="openEdit(${allData.indexOf(r)})">✏️</button></td>
    </tr>
  `).join('');
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
  if (months[0]) { sel.value = months[0]; activeMonth = months[0]; }
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

// Cargar datos
fetch('/api/transactions').then(r => r.json()).then(data => {
  allData = data;
  populateMonths();
  refresh();
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
    return render_template_string(HTML)


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


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
