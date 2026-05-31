/**
 * dashboard.js — Live monitoring view with charts
 */

const MAX_LIVE_ROWS = 50;
let liveRows = [];

let chartTypes     = null;
let chartOwnership = null;
let chartSparkline = null;

// ── Color maps ────────────────────────────────────────────────────────────────
const TYPE_COLORS = {
  car:        '#1D9E75',
  motorcycle: '#378ADD',
  bus:        '#BA7517',
  microbus:   '#D4537E',
  truck:      '#E24B4A',
  van:        '#639922',
  tractor:    '#8B5CF6',
  other:      '#9CA3AF',
};

const OWN_COLORS = {
  private:     '#5F5E5A',
  public:      '#639922',
  government:  '#BA7517',
  police:      '#185FA5',
  army:        '#3B6D11',
  armed_police:'#6B21A8',
  diplomatic:  '#D4537E',
  un:          '#0284C7',
  ngo:         '#854D0E',
};

// ── Init ──────────────────────────────────────────────────────────────────────
function initDashboard() {
  initDonutChart();
  initOwnershipChart();
  initSparkline();
  refresh();
}

// ── Donut chart — vehicle types ───────────────────────────────────────────────
function initDonutChart() {
  const ctx = document.getElementById('chart-donut-types')?.getContext('2d');
  if (!ctx) return;
  chartTypes = new Chart(ctx, {
    type: 'doughnut',
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 12, font: { size: 11 } } }
      },
      cutout: '60%',
    }
  });
}

function updateTypeChart(byType) {
  if (!chartTypes) return;
  const labels = Object.keys(byType);
  const data   = Object.values(byType);
  const colors = labels.map(l => TYPE_COLORS[l] || '#999');
  chartTypes.data.labels = labels;
  chartTypes.data.datasets[0].data = data;
  chartTypes.data.datasets[0].backgroundColor = colors;
  chartTypes.update('none');
}

// ── Bar chart — ownership ─────────────────────────────────────────────────────
function initOwnershipChart() {
  const ctx = document.getElementById('chart-bar-ownership')?.getContext('2d');
  if (!ctx) return;
  chartOwnership = new Chart(ctx, {
    type: 'bar',
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 4 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  });
}

function updateOwnershipChart(byOwnership) {
  if (!chartOwnership) return;
  const labels = Object.keys(byOwnership);
  const data   = Object.values(byOwnership);
  const colors = labels.map(l => OWN_COLORS[l] || '#999');
  chartOwnership.data.labels = labels;
  chartOwnership.data.datasets[0].data = data;
  chartOwnership.data.datasets[0].backgroundColor = colors;
  chartOwnership.update('none');
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function initSparkline() {
  const ctx = document.getElementById('chart-sparkline')?.getContext('2d');
  if (!ctx) return;
  chartSparkline = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        data: [], fill: true,
        borderColor: '#1D9E75',
        backgroundColor: 'rgba(29,158,117,0.12)',
        tension: 0.4, pointRadius: 3,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxTicksLimit: 12 }, grid: { display: false } },
        y: { ticks: { font: { size: 10 } }, beginAtZero: true }
      }
    }
  });
}

async function updateSparkline() {
  try {
    const params = App.checkpointId ? `?checkpoint_id=${App.checkpointId}&hours=12` : '?hours=12';
    const res = await fetch(`${API}/stats/hourly${params}`);
    if (!res.ok) return;
    const data = await res.json();
    if (!chartSparkline) return;
    // Fill all 12 hour slots even if some are empty
    const now = new Date();
    const labels = [], counts = [];
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now);
      d.setHours(d.getHours() - i, 0, 0, 0);
      const bucket = d.toISOString().slice(0, 13) + ':00:00';
      const entry = data.find(e => e.hour === bucket);
      labels.push(d.toLocaleTimeString('en-NP', { hour: '2-digit', minute: '2-digit' }));
      counts.push(entry ? entry.count : 0);
    }
    chartSparkline.data.labels = labels;
    chartSparkline.data.datasets[0].data = counts;
    chartSparkline.update('none');

    // Per-hour metric (current hour)
    const currentCount = counts[counts.length - 1];
    document.getElementById('m-perhour').textContent = currentCount;
  } catch(e) {}
}

// ── Refresh summary stats ─────────────────────────────────────────────────────
async function refresh() {
  try {
    const params = App.checkpointId ? `?checkpoint_id=${App.checkpointId}` : '';
    const res = await fetch(`${API}/stats/summary${params}`);
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('m-total').textContent    = data.total_today;
    document.getElementById('m-accuracy').textContent = data.plate_accuracy_pct + '%';
    document.getElementById('m-alerts').textContent   = data.active_alerts;
    updateTypeChart(data.by_type);
    updateOwnershipChart(data.by_ownership);
  } catch(e) {}

  updateSparkline();

  // Load recent rows for the live table on page switch
  try {
    const params = App.checkpointId
      ? `?checkpoint_id=${App.checkpointId}&limit=30`
      : '?limit=30';
    const res = await fetch(`${API}/vehicles${params}`);
    if (!res.ok) return;
    const rows = await res.json();
    const tbody = document.getElementById('live-feed-body');
    tbody.innerHTML = '';
    liveRows = [];
    rows.reverse().forEach(r => addRow(r, false));
  } catch(e) {}
}

// ── Add a row to the live feed table ─────────────────────────────────────────
function addRow(sighting, animate = true) {
  const tbody = document.getElementById('live-feed-body');
  if (!tbody) return;

  // Remove placeholder
  const placeholder = tbody.querySelector('td[colspan]');
  if (placeholder) placeholder.parentElement.remove();

  const tr = document.createElement('tr');
  if (animate) tr.className = 'new-row';

  // Row color class
  if (sighting.flagged) tr.classList.add('flagged');
  else if (['government', 'police', 'army', 'armed_police'].includes(sighting.ownership_category))
    tr.classList.add('gov-row');
  else if (['diplomatic', 'un'].includes(sighting.ownership_category))
    tr.classList.add('diplomatic-row');

  tr.innerHTML = `
    <td class="font-mono" style="font-size:12px">${formatTime(sighting.timestamp)}</td>
    <td class="font-mono" style="font-weight:700">${sighting.plate_text || '—'}</td>
    <td>${sighting.vehicle_type || '—'}</td>
    <td>${ownershipBadge(sighting.ownership_category)}</td>
    <td>${sighting.origin_city || '—'}</td>
    <td style="font-size:11px">${sighting.direction === 'inbound' ? '→ IN' : '← OUT'}</td>
    <td>${statusBadge(sighting.flagged)}</td>
  `;

  tr.addEventListener('click', () => openDetailPanel(sighting));
  tbody.insertBefore(tr, tbody.firstChild);
  liveRows.unshift(sighting);

  // Cap at MAX_LIVE_ROWS
  if (tbody.children.length > MAX_LIVE_ROWS) {
    tbody.removeChild(tbody.lastChild);
    liveRows.pop();
  }

  // Update donut/bar incrementally from running count
  if (animate) {
    // Small incremental update without full API call
    refreshChartCounts();
  }
}

// Rebuild charts from in-memory liveRows
function refreshChartCounts() {
  const byType = {}, byOwn = {};
  liveRows.forEach(r => {
    byType[r.vehicle_type] = (byType[r.vehicle_type] || 0) + 1;
    byOwn[r.ownership_category] = (byOwn[r.ownership_category] || 0) + 1;
  });
  updateTypeChart(byType);
  updateOwnershipChart(byOwn);
}

// ── Expose ────────────────────────────────────────────────────────────────────
window.Dashboard = { init: initDashboard, refresh, addRow };
