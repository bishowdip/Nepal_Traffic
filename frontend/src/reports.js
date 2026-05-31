/**
 * reports.js — Vehicle Log (page 2) + Analytics (page 3)
 */

// ═══════════════════════════════════════════════════════════════
// PAGE 2 — VEHICLE LOG
// ═══════════════════════════════════════════════════════════════
let logPage = 1;
const LOG_LIMIT = 50;

async function loadLog() {
  logPage = 1;
  await fetchLogPage();
}

async function fetchLogPage() {
  const start    = document.getElementById('f-start').value;
  const end      = document.getElementById('f-end').value;
  const type     = document.getElementById('f-type').value;
  const ownership= document.getElementById('f-ownership').value;
  const direction= document.getElementById('f-direction').value;
  const flagged  = document.getElementById('f-flagged').checked;
  const plate    = document.getElementById('f-plate').value;

  const params = new URLSearchParams({ page: logPage, limit: LOG_LIMIT });
  if (App.checkpointId) params.set('checkpoint_id', App.checkpointId);
  if (start) params.set('start', start + 'T00:00:00');
  if (end)   params.set('end',   end   + 'T23:59:59');
  if (type)      params.set('type', type);
  if (ownership) params.set('ownership', ownership);
  if (direction) params.set('direction', direction);
  if (flagged)   params.set('flagged', 'true');
  if (plate)     params.set('plate', plate);

  const tbody = document.getElementById('log-body');
  tbody.innerHTML = '<tr><td colspan="11" class="empty-state"><div class="spinner" style="margin:auto"></div></td></tr>';

  try {
    const res = await fetch(`${API}/vehicles?${params}`);
    if (!res.ok) throw new Error('Failed');
    const rows = await res.json();
    renderLogTable(rows);
    renderPagination(rows.length);
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="11" class="empty-state text-muted">Error loading data</td></tr>';
  }
}

function renderLogTable(rows) {
  const tbody = document.getElementById('log-body');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="empty-state">No records found</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr class="${r.flagged ? 'flagged' : ''}" onclick="openDetailPanel(${JSON.stringify(r).replace(/"/g, '&quot;')})">
      <td class="font-mono" style="font-size:11.5px">${new Date(r.timestamp).toLocaleString('en-NP')}</td>
      <td class="font-mono" style="font-weight:700">${r.plate_text}</td>
      <td>${(r.plate_confidence * 100).toFixed(0)}%</td>
      <td>${r.vehicle_type}</td>
      <td>${ownershipBadge(r.ownership_category)}</td>
      <td>${r.origin_city || '—'}</td>
      <td>${r.direction === 'inbound' ? '→ IN' : '← OUT'}</td>
      <td><span class="badge-status ${r.dotm_registered ? 'ok' : 'fail'}">${r.dotm_registered ? '✓' : '✗'}</span></td>
      <td><span class="badge-status ${r.fitness_valid === null ? 'na' : r.fitness_valid ? 'ok' : 'fail'}">${r.fitness_valid === null ? '—' : r.fitness_valid ? '✓' : '✗'}</span></td>
      <td><span class="badge-status ${r.insurance_valid === null ? 'na' : r.insurance_valid ? 'ok' : 'fail'}">${r.insurance_valid === null ? '—' : r.insurance_valid ? '✓' : '✗'}</span></td>
      <td>${statusBadge(r.flagged)}</td>
    </tr>
  `).join('');
}

function renderPagination(rowCount) {
  const wrap = document.getElementById('log-pagination');
  wrap.innerHTML = '';
  if (logPage > 1) {
    const btn = document.createElement('button');
    btn.className = 'page-btn';
    btn.textContent = '← Prev';
    btn.onclick = () => { logPage--; fetchLogPage(); };
    wrap.appendChild(btn);
  }
  const info = document.createElement('span');
  info.style.cssText = 'font-size:12px;color:var(--text-muted)';
  info.textContent = `Page ${logPage}`;
  wrap.appendChild(info);
  if (rowCount === LOG_LIMIT) {
    const btn = document.createElement('button');
    btn.className = 'page-btn';
    btn.textContent = 'Next →';
    btn.onclick = () => { logPage++; fetchLogPage(); };
    wrap.appendChild(btn);
  }
}

// Export buttons
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('f-search-btn')?.addEventListener('click', () => { logPage = 1; fetchLogPage(); });
  document.getElementById('log-export-csv')?.addEventListener('click', () => {
    const params = App.checkpointId ? `?checkpoint_id=${App.checkpointId}` : '';
    window.open(`${API}/reports/export/csv${params}`, '_blank');
  });
  document.getElementById('log-export-pdf')?.addEventListener('click', () => {
    const params = App.checkpointId ? `?checkpoint_id=${App.checkpointId}` : '';
    window.open(`${API}/reports/export/pdf${params}`, '_blank');
  });
});

window.VehicleLog = { load: loadLog };


// ═══════════════════════════════════════════════════════════════
// PAGE 3 — ANALYTICS
// ═══════════════════════════════════════════════════════════════
let charts = {};

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

async function loadAnalytics() {
  const startEl = document.getElementById('ana-start');
  const endEl   = document.getElementById('ana-end');
  if (!startEl.value) {
    const d = new Date();
    endEl.value   = d.toISOString().slice(0, 10);
    d.setDate(d.getDate() - 6);
    startEl.value = d.toISOString().slice(0, 10);
  }
  const cpId = document.getElementById('ana-checkpoint')?.value || App.checkpointId;

  const [hourlyData, originData, summaryData] = await Promise.all([
    fetch(`${API}/stats/hourly?hours=168${cpId ? '&checkpoint_id='+cpId : ''}`).then(r => r.json()).catch(() => []),
    fetch(`${API}/stats/origin?days=7${cpId ? '&checkpoint_id='+cpId : ''}`).then(r => r.json()).catch(() => []),
    fetch(`${API}/stats/summary${cpId ? '?checkpoint_id='+cpId : ''}`).then(r => r.json()).catch(() => ({})),
  ]);

  renderHourlyLine(hourlyData);
  renderDailyStacked(hourlyData);
  renderOriginBar(originData);
  renderOwnershipPie(summaryData.by_ownership || {});
  renderInOutArea(hourlyData);
  renderHeatmap(hourlyData);
}

// 1. Hourly line chart (multi-day)
function renderHourlyLine(data) {
  destroyChart('hourly-line');
  const ctx = document.getElementById('chart-hourly-line')?.getContext('2d');
  if (!ctx) return;

  // Group by day
  const dayMap = {};
  data.forEach(d => {
    const day  = d.hour.slice(0, 10);
    const hour = parseInt(d.hour.slice(11, 13));
    if (!dayMap[day]) dayMap[day] = Array(24).fill(0);
    dayMap[day][hour] = d.count;
  });

  const days = Object.keys(dayMap).sort().slice(-7);
  const colors = ['#1D9E75','#378ADD','#BA7517','#D4537E','#E24B4A','#639922','#8B5CF6'];
  const datasets = days.map((day, i) => ({
    label: day.slice(5),
    data: dayMap[day],
    borderColor: colors[i % colors.length],
    backgroundColor: 'transparent',
    tension: 0.3, borderWidth: 2, pointRadius: 2,
  }));

  charts['hourly-line'] = new Chart(ctx, {
    type: 'line',
    data: { labels: Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2,'0')}:00`), datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: {
        x: { ticks: { font: { size: 9 }, maxTicksLimit: 12 } },
        y: { beginAtZero: true, ticks: { font: { size: 10 } } }
      }
    }
  });
}

// 2. Stacked bar by type (per day)
function renderDailyStacked(data) {
  destroyChart('daily-stacked');
  const ctx = document.getElementById('chart-daily-stacked')?.getContext('2d');
  if (!ctx) return;

  const dayMap = {};
  data.forEach(d => {
    const day = d.hour.slice(0, 10);
    dayMap[day] = (dayMap[day] || 0) + d.count;
  });

  const days   = Object.keys(dayMap).sort().slice(-7);
  const counts = days.map(d => dayMap[d]);

  charts['daily-stacked'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: days.map(d => d.slice(5)),
      datasets: [{ label: 'Vehicles', data: counts, backgroundColor: '#1D9E75', borderRadius: 4 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { font: { size: 10 } } }
      }
    }
  });
}

// 3. Horizontal bar — top 15 origin cities
function renderOriginBar(data) {
  destroyChart('origin-bar');
  const ctx = document.getElementById('chart-origin-bar')?.getContext('2d');
  if (!ctx) return;

  const labels = data.map(d => d.city);
  const counts = data.map(d => d.count);
  const colors = labels.map((_, i) => `hsl(${160 + i * 12}, 55%, 45%)`);

  charts['origin-bar'] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ data: counts, backgroundColor: colors, borderRadius: 4 }] },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { font: { size: 10 } } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  });
}

// 4. Ownership pie
function renderOwnershipPie(byOwn) {
  destroyChart('ownership-pie');
  const ctx = document.getElementById('chart-ownership-pie')?.getContext('2d');
  if (!ctx) return;

  const OWN_COLORS = {
    private:'#5F5E5A', public:'#639922', government:'#BA7517',
    police:'#185FA5', army:'#3B6D11', armed_police:'#6B21A8',
    diplomatic:'#D4537E', un:'#0284C7', ngo:'#854D0E',
  };

  const labels = Object.keys(byOwn);
  charts['ownership-pie'] = new Chart(ctx, {
    type: 'pie',
    data: {
      labels,
      datasets: [{ data: labels.map(l => byOwn[l]), backgroundColor: labels.map(l => OWN_COLORS[l] || '#999'), borderWidth: 2 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { boxWidth: 11, font: { size: 10 } } } }
    }
  });
}

// 5. Inbound vs Outbound area chart
function renderInOutArea(data) {
  destroyChart('inout-area');
  const ctx = document.getElementById('chart-inout-area')?.getContext('2d');
  if (!ctx) return;

  const labels  = data.map(d => d.hour.slice(5, 16).replace('T', ' '));
  const inbound  = data.map(d => d.inbound);
  const outbound = data.map(d => d.outbound);

  charts['inout-area'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Inbound',  data: inbound,  fill: true, backgroundColor: 'rgba(29,158,117,0.15)', borderColor: '#1D9E75', tension: 0.3, borderWidth: 2, pointRadius: 0 },
        { label: 'Outbound', data: outbound, fill: true, backgroundColor: 'rgba(226,75,74,0.10)',  borderColor: '#E24B4A', tension: 0.3, borderWidth: 2, pointRadius: 0 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: {
        x: { ticks: { font: { size: 9 }, maxTicksLimit: 12 }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { font: { size: 10 } } }
      }
    }
  });
}

// 6. Heatmap table — day × hour
function renderHeatmap(data) {
  const wrap = document.getElementById('heatmap-wrap');
  if (!wrap) return;

  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  // Build matrix [day][hour]
  const matrix = Array.from({ length: 7 }, () => Array(24).fill(0));
  data.forEach(d => {
    const date = new Date(d.hour);
    matrix[date.getDay()][date.getHours()] += d.count;
  });

  const maxVal = Math.max(...matrix.flat(), 1);
  let html = '<table class="heatmap-table"><thead><tr><th>Day</th>' +
    Array.from({ length: 24 }, (_, h) => `<th>${String(h).padStart(2,'0')}</th>`).join('') +
    '</tr></thead><tbody>';

  DAYS.forEach((day, di) => {
    html += `<tr><th style="text-align:left;padding:3px 6px">${day}</th>`;
    for (let h = 0; h < 24; h++) {
      const v = matrix[di][h];
      const intensity = v / maxVal;
      const r = Math.round(29  + (226 - 29)  * (1 - intensity));
      const g = Math.round(158 + (75  - 158) * (1 - intensity));
      const b = Math.round(117 + (74  - 117) * (1 - intensity));
      const textColor = intensity > 0.5 ? '#fff' : 'var(--text-muted)';
      html += `<td class="heatmap-cell" style="background:rgb(${r},${g},${b});color:${textColor}" title="${day} ${h}:00 — ${v} vehicles">${v || ''}</td>`;
    }
    html += '</tr>';
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

// ── Bind events ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('ana-load-btn')?.addEventListener('click', loadAnalytics);
});

window.Analytics = { load: loadAnalytics };
