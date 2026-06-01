/**
 * main.js — App shell: navigation, theme, checkpoints, WebSocket manager, global state
 */

// Derive API + WebSocket base from the page origin so the dashboard works on
// any host/port the backend is served from (it serves this frontend itself).
// Override by setting window.API_ORIGIN before this script loads.
const _ORIGIN = window.API_ORIGIN || window.location.origin;
const API = `${_ORIGIN}/api`;
const WS_BASE = _ORIGIN.replace(/^http/, 'ws');

// ── Global state ──────────────────────────────────────────────────────────────
window.App = {
  checkpointId: '',
  checkpoints: [],
  ws: null,
  wsAlerts: null,
  alertCount: 0,
  totalToday: 0,
};

// ── Theme ─────────────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────
function initNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const page = item.dataset.page;
      navigateTo(page);
    });
  });
}

function navigateTo(page) {
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
  const pageEl  = document.getElementById(`page-${page}`);
  if (navItem) navItem.classList.add('active');
  if (pageEl)  pageEl.classList.add('active');

  // Trigger page-specific load
  if (page === 'dashboard')    window.Dashboard?.refresh();
  if (page === 'vehicle-log')  window.VehicleLog?.load();
  if (page === 'analytics')    window.Analytics?.load();
  if (page === 'alerts')       window.Alerts?.load();
  if (page === 'registry')     document.getElementById('registry-search')?.focus();
  if (page === 'settings')     window.Settings?.load();
}

// ── Live clock ────────────────────────────────────────────────────────────────
function initClock() {
  function update() {
    const now = new Date();
    document.getElementById('topbar-meta').textContent =
      now.toLocaleDateString('en-NP', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) +
      ' · ' + now.toLocaleTimeString('en-NP');
  }
  update();
  setInterval(update, 1000);
}

// ── Checkpoints ───────────────────────────────────────────────────────────────
async function loadCheckpoints() {
  try {
    const res = await fetch(`${API}/checkpoints`);
    if (!res.ok) return;
    const checkpoints = await res.json();
    App.checkpoints = checkpoints;

    const sel = document.getElementById('checkpoint-select');
    const anaSel = document.getElementById('ana-checkpoint');
    checkpoints.forEach(cp => {
      [sel, anaSel].forEach(s => {
        if (!s) return;
        const opt = document.createElement('option');
        opt.value = cp.id;
        opt.textContent = cp.name;
        s.appendChild(opt);
      });
    });

    sel.addEventListener('change', () => {
      App.checkpointId = sel.value;
      const cp = checkpoints.find(c => c.id === sel.value);
      document.getElementById('topbar-title').textContent =
        cp ? cp.name : 'All Checkpoints';
      connectWebSocket();
      window.Dashboard?.refresh();
    });

    // Default to first checkpoint
    if (checkpoints.length > 0) {
      sel.value = checkpoints[0].id;
      App.checkpointId = checkpoints[0].id;
      document.getElementById('topbar-title').textContent = checkpoints[0].name;
    }
  } catch (e) {
    console.warn('Could not load checkpoints:', e);
  }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let wsRetryTimer = null;

function connectWebSocket() {
  const cpId = App.checkpointId || 'all';

  // Close old connections
  if (App.ws) { try { App.ws.close(); } catch(e){} }
  if (App.wsAlerts) { try { App.wsAlerts.close(); } catch(e){} }

  // Sightings feed
  App.ws = new WebSocket(`${WS_BASE}/ws/live/${cpId}`);
  App.ws.onopen = () => {
    document.getElementById('reconnect-banner').classList.remove('show');
    document.getElementById('live-badge').className = 'live-badge';
    document.getElementById('live-badge').innerHTML = '<div class="dot"></div> LIVE';
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null; }
  };
  App.ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'sighting') {
        window.Dashboard?.addRow(msg.data);
        App.totalToday++;
        document.getElementById('stat-today').textContent = App.totalToday;
        document.getElementById('m-total').textContent = App.totalToday;
      }
    } catch(e) {}
  };
  App.ws.onclose = () => scheduleReconnect(cpId);
  App.ws.onerror = () => scheduleReconnect(cpId);

  // Alerts feed
  App.wsAlerts = new WebSocket(`${WS_BASE}/ws/alerts/${cpId}`);
  App.wsAlerts.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'alert') {
        App.alertCount++;
        updateAlertBadge(App.alertCount);
        window.Alerts?.prepend(msg.data);
      }
    } catch(e) {}
  };
}

function scheduleReconnect(cpId) {
  document.getElementById('reconnect-banner').classList.add('show');
  document.getElementById('live-badge').className = 'live-badge offline';
  document.getElementById('live-badge').innerHTML = '<div class="dot"></div> OFFLINE';
  if (!wsRetryTimer) {
    wsRetryTimer = setTimeout(() => {
      wsRetryTimer = null;
      connectWebSocket();
    }, 5000);
  }
}

// ── Alert badge ───────────────────────────────────────────────────────────────
function updateAlertBadge(count) {
  const badge = document.getElementById('alert-badge');
  badge.textContent = count;
  badge.style.display = count > 0 ? 'inline-block' : 'none';
  document.getElementById('stat-alerts').textContent = count;
  document.getElementById('m-alerts').textContent = count;
}

// ── Stats polling ─────────────────────────────────────────────────────────────
async function pollStats() {
  try {
    const params = App.checkpointId ? `?checkpoint_id=${App.checkpointId}` : '';
    const res = await fetch(`${API}/stats/summary${params}`);
    if (!res.ok) return;
    const data = await res.json();
    App.totalToday = data.total_today;
    document.getElementById('stat-today').textContent = data.total_today;
    document.getElementById('m-total').textContent = data.total_today;
    document.getElementById('m-accuracy').textContent = data.plate_accuracy_pct + '%';
    updateAlertBadge(data.active_alerts);
  } catch(e) {}
}

// ── Detail panel ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('detail-close').addEventListener('click', closeDetailPanel);
});

function openDetailPanel(sighting) {
  const panel = document.getElementById('detail-panel');
  panel.classList.add('open');
  document.getElementById('detail-plate').textContent = sighting.plate_text || '—';

  const fields = [
    ['Type',        sighting.vehicle_type],
    ['Ownership',   sighting.ownership_category],
    ['Direction',   sighting.direction],
    ['District',    sighting.district_code || '—'],
    ['Origin',      sighting.origin_city   || '—'],
    ['Destination', sighting.destination_city || '—'],
    ['Checkpoint',  sighting.checkpoint_id],
    ['Camera',      sighting.camera_id || '—'],
    ['Confidence',  sighting.plate_confidence ? (sighting.plate_confidence * 100).toFixed(1) + '%' : '—'],
    ['Time',        sighting.timestamp ? new Date(sighting.timestamp).toLocaleString() : '—'],
  ];

  const grid = document.getElementById('detail-grid');
  grid.innerHTML = fields.map(([label, val]) =>
    `<div class="detail-field"><label>${label}</label><span>${val}</span></div>`
  ).join('');

  // DoTM info
  const dotmEl = document.getElementById('detail-dotm');
  if (sighting.dotm_registered) {
    dotmEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px">
        <div class="detail-field"><label>Owner</label><span>${sighting.owner_name || '—'}</span></div>
        <div class="detail-field"><label>Registered</label><span class="badge-status ok">✓ Yes</span></div>
        <div class="detail-field"><label>Fitness</label><span class="badge-status ${sighting.fitness_valid ? 'ok' : 'fail'}">${sighting.fitness_valid ? '✓ Valid' : '✗ Expired'}</span></div>
        <div class="detail-field"><label>Insurance</label><span class="badge-status ${sighting.insurance_valid ? 'ok' : 'fail'}">${sighting.insurance_valid ? '✓ Valid' : '✗ Expired'}</span></div>
      </div>`;
  } else {
    dotmEl.innerHTML = `<span class="badge-alert warning">⚠ Not registered in DoTM</span>`;
  }

  // Alerts
  const alertsEl = document.getElementById('detail-alerts');
  if (sighting.flagged) {
    alertsEl.innerHTML = `<div class="badge-alert critical">🚨 ${sighting.flag_reason || 'Flagged'}</div>`;
  } else {
    alertsEl.innerHTML = `<span class="badge-status ok">No alerts</span>`;
  }
}

function closeDetailPanel() {
  document.getElementById('detail-panel').classList.remove('open');
}

window.openDetailPanel = openDetailPanel;

// ── Helpers ───────────────────────────────────────────────────────────────────
window.formatTime = (ts) => {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString('en-NP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

window.ownershipBadge = (cat) =>
  `<span class="badge-ownership ${cat}">${cat}</span>`;

window.statusBadge = (flagged) =>
  flagged
    ? `<span class="badge-alert warning">⚠ Flagged</span>`
    : `<span class="badge-status ok">OK</span>`;

window.API = API;
window.WS_BASE = WS_BASE;

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initNav();
  initClock();
  await loadCheckpoints();
  connectWebSocket();
  await pollStats();
  setInterval(pollStats, 30000);
  window.Dashboard?.init();
});
