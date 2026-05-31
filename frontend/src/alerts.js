/**
 * alerts.js — Alert management view (Page 4)
 */

async function loadAlerts() {
  const severity = document.getElementById('alert-filter-sev')?.value || '';
  const type     = document.getElementById('alert-filter-type')?.value || '';

  const params = new URLSearchParams({ limit: 100 });
  if (severity) params.set('severity', severity);
  if (type)     params.set('alert_type', type);

  try {
    const [activeRes, resolvedRes] = await Promise.all([
      fetch(`${API}/alerts?resolved=false&${params}`),
      fetch(`${API}/alerts?resolved=true&${params}&limit=50`),
    ]);

    const active   = activeRes.ok   ? await activeRes.json()   : [];
    const resolved = resolvedRes.ok ? await resolvedRes.json() : [];

    renderAlertList(document.getElementById('active-alerts-list'),   active,   false);
    renderAlertList(document.getElementById('resolved-alerts-list'), resolved, true);

    // Update badge
    if (App) App.alertCount = active.length;
    const badge = document.getElementById('alert-badge');
    if (badge) {
      badge.textContent = active.length;
      badge.style.display = active.length > 0 ? 'inline-block' : 'none';
    }
  } catch(e) {
    console.error('Alert load error:', e);
  }
}

function renderAlertList(container, alerts, isResolved) {
  if (!container) return;
  if (!alerts.length) {
    container.innerHTML = `<div class="empty-state">${isResolved ? 'No resolved alerts' : 'No active alerts'}</div>`;
    return;
  }
  container.innerHTML = alerts.map(a => alertCardHTML(a, isResolved)).join('');

  // Bind resolve buttons
  if (!isResolved) {
    container.querySelectorAll('.resolve-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        await resolveAlert(id);
      });
    });
  }
}

function alertCardHTML(a, isResolved) {
  const typeLabels = {
    watchlist_match:  'Watchlist Match',
    unregistered:     'Unregistered Vehicle',
    expired_fitness:  'Expired Fitness',
    expired_insurance:'Expired Insurance',
    obscured_plate:   'Obscured Plate',
    high_volume:      'High Volume',
    unreadable_plate: 'Unreadable Plate',
  };

  const created = a.created_at ? new Date(a.created_at).toLocaleString('en-NP') : '—';
  const resolved = a.resolved_at ? new Date(a.resolved_at).toLocaleString('en-NP') : '';

  return `
    <div class="alert-card ${a.severity}" style="margin-bottom:10px">
      <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-start">
        <span class="badge-alert ${a.severity}">${a.severity.toUpperCase()}</span>
      </div>
      <div class="alert-card-body">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="plate font-mono">${a.plate_text || '—'}</span>
          <span style="font-size:12px;color:var(--text-muted);font-weight:600">${typeLabels[a.alert_type] || a.alert_type}</span>
        </div>
        <div class="desc">${a.description || ''}</div>
        <div class="time">${created}${resolved ? ' · Resolved: ' + resolved : ''}</div>
        ${a.sighting_id ? `<div style="margin-top:4px;font-size:11px;color:var(--text-muted)">Sighting ID: ${a.sighting_id.slice(0,8)}...</div>` : ''}
      </div>
      ${!isResolved ? `<button class="btn btn-outline btn-sm resolve-btn" data-id="${a.id}" style="flex-shrink:0">✓ Resolve</button>` : ''}
    </div>
  `;
}

async function resolveAlert(alertId) {
  try {
    const res = await fetch(`${API}/alerts/${alertId}/resolve`, { method: 'PATCH' });
    if (res.ok) {
      loadAlerts();
    }
  } catch(e) {
    console.error('Resolve alert error:', e);
  }
}

// Prepend a new alert from WebSocket
function prependAlert(alertData) {
  const container = document.getElementById('active-alerts-list');
  if (!container) return;
  const placeholder = container.querySelector('.empty-state');
  if (placeholder) container.innerHTML = '';

  const div = document.createElement('div');
  div.innerHTML = alertCardHTML(alertData, false);
  container.insertBefore(div.firstChild, container.firstChild);

  // Rebind resolve button for the new card
  const btn = container.firstChild?.querySelector('.resolve-btn');
  if (btn) {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await resolveAlert(btn.dataset.id);
    });
  }
}

// ── Bind events ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('alert-load-btn')?.addEventListener('click', loadAlerts);
});

window.Alerts = { load: loadAlerts, prepend: prependAlert };
