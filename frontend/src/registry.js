/**
 * registry.js — DoTM Registry Search (Page 5) + Settings (Page 6)
 */

// ═══════════════════════════════════════════════════════════════
// PAGE 5 — REGISTRY SEARCH
// ═══════════════════════════════════════════════════════════════
let searchDebounceTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('registry-search');
  if (input) {
    input.addEventListener('input', () => {
      clearTimeout(searchDebounceTimer);
      const val = input.value.trim();
      if (val.length < 2) {
        document.getElementById('registry-result').innerHTML = '';
        document.getElementById('registry-sightings').innerHTML = '';
        return;
      }
      searchDebounceTimer = setTimeout(() => doSearch(val), 400);
    });
  }
});

async function doSearch(plateText) {
  const resultEl   = document.getElementById('registry-result');
  const sightingsEl = document.getElementById('registry-sightings');
  resultEl.innerHTML   = '<div class="empty-state"><div class="spinner" style="margin:auto"></div></div>';
  sightingsEl.innerHTML = '';

  try {
    const res = await fetch(`${API}/dotm/${encodeURIComponent(plateText)}`);
    if (res.ok) {
      const record = await res.json();
      resultEl.innerHTML = renderDoTMCard(record, plateText);
    } else {
      resultEl.innerHTML = renderNotFound(plateText);
    }
  } catch(e) {
    resultEl.innerHTML = renderNotFound(plateText);
  }

  // Also load sightings for this plate
  try {
    const res = await fetch(`${API}/vehicles/search?plate=${encodeURIComponent(plateText)}`);
    if (res.ok) {
      const sightings = await res.json();
      if (sightings.length) {
        sightingsEl.innerHTML = `
          <div style="margin-top:20px">
            <h3 style="font-size:14px;font-weight:700;margin-bottom:10px">Recent Sightings (last 30 days)</h3>
            <div class="card">
              <table>
                <thead><tr><th>Time</th><th>Checkpoint</th><th>Direction</th><th>Status</th></tr></thead>
                <tbody>${sightings.map(s => `
                  <tr>
                    <td class="font-mono" style="font-size:12px">${new Date(s.timestamp).toLocaleString('en-NP')}</td>
                    <td>${s.checkpoint_id}</td>
                    <td>${s.direction === 'inbound' ? '→ IN' : '← OUT'}</td>
                    <td>${statusBadge(s.flagged)}</td>
                  </tr>
                `).join('')}</tbody>
              </table>
            </div>
          </div>
        `;
      } else {
        sightingsEl.innerHTML = `<div style="margin-top:16px" class="text-muted" style="font-size:13px">No sightings recorded in the last 30 days.</div>`;
      }
    }
  } catch(e) {}
}

function renderDoTMCard(r, plateText) {
  const today = new Date().toISOString().slice(0, 10);
  const fitnessOk   = r.fitness_expiry   >= today;
  const insuranceOk = r.insurance_expiry >= today;

  return `
    <div class="dotm-card">
      <div class="dotm-card-header">
        <span style="font-size:20px">🚗</span>
        <div>
          <div style="font-size:20px;font-family:monospace;font-weight:800;letter-spacing:0.12em">${r.plate_text}</div>
          <div style="font-size:12px;opacity:0.85">${r.vehicle_make} ${r.vehicle_model} · ${r.color} · ${r.registered_year}</div>
        </div>
        <span class="badge-status ok" style="margin-left:auto">✓ Registered</span>
      </div>
      <div class="dotm-card-body">
        <div class="dotm-field"><label>Owner Name</label><div class="val">${r.owner_name}</div></div>
        <div class="dotm-field"><label>Vehicle Type</label><div class="val">${r.vehicle_type}</div></div>
        <div class="dotm-field"><label>Engine</label><div class="val">${r.engine_cc} cc</div></div>
        <div class="dotm-field"><label>Registered District</label><div class="val">${r.registered_district}</div></div>
        <div class="dotm-field">
          <label>Fitness Expiry</label>
          <div class="val">
            <span class="badge-status ${fitnessOk ? 'ok' : 'fail'}">${fitnessOk ? '✓' : '✗'} ${r.fitness_expiry}</span>
          </div>
        </div>
        <div class="dotm-field">
          <label>Insurance Expiry</label>
          <div class="val">
            <span class="badge-status ${insuranceOk ? 'ok' : 'fail'}">${insuranceOk ? '✓' : '✗'} ${r.insurance_expiry}</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderNotFound(plateText) {
  return `
    <div class="not-found-card">
      <div style="font-size:32px;margin-bottom:8px">🔍</div>
      <div style="font-size:16px;font-weight:700">Plate Not Found</div>
      <div style="margin-top:6px;font-size:13px;opacity:0.8">
        <strong>${plateText}</strong> is not registered in the DoTM registry.<br>
        This vehicle may be unregistered or the plate may be misread.
      </div>
    </div>
  `;
}


// ═══════════════════════════════════════════════════════════════
// PAGE 6 — SETTINGS
// ═══════════════════════════════════════════════════════════════
async function loadSettings() {
  // Checkpoints
  const cpList = document.getElementById('checkpoint-list-settings');
  if (cpList && App.checkpoints.length) {
    cpList.innerHTML = App.checkpoints.map(cp => `
      <div class="settings-row">
        <div>
          <label>${cp.name}</label>
          <div class="desc">${cp.location || ''} ${cp.lat ? `· (${cp.lat}, ${cp.lng})` : ''}</div>
        </div>
        <span class="badge-status ${cp.active ? 'ok' : 'na'}">${cp.active ? 'Active' : 'Inactive'}</span>
      </div>
    `).join('');
  }

  // Watchlist
  await loadWatchlist();

  // System info
  try {
    const res = await fetch(`${API}/../health`);
    if (res.ok) {
      const info = await res.json();
      document.getElementById('system-info').innerHTML = `
        <div class="settings-row"><div><label>Status</label></div><span class="badge-status ok">${info.status}</span></div>
        <div class="settings-row"><div><label>Mock Mode</label></div><span class="badge-alert info">${info.mock_mode ? 'Enabled' : 'Disabled'}</span></div>
        <div class="settings-row"><div><label>Checkpoint</label></div><span>${info.checkpoint}</span></div>
      `;
    }
  } catch(e) {
    document.getElementById('system-info').innerHTML = '<div class="text-muted" style="padding:10px">Server not reachable</div>';
  }
}

async function loadWatchlist() {
  try {
    const res = await fetch(`${API}/watchlist`);
    if (!res.ok) return;
    const items = await res.json();
    const el = document.getElementById('watchlist-list');
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="text-muted" style="padding:8px 0;font-size:13px">No watchlist entries</div>';
      return;
    }
    el.innerHTML = items.map(w => `
      <div class="settings-row">
        <div>
          <label class="font-mono">${w.plate_text}</label>
          <div class="desc">${w.reason || ''} · Added by ${w.added_by || 'system'}</div>
        </div>
        <button class="btn btn-danger btn-sm wl-remove-btn" data-plate="${w.plate_text}">Remove</button>
      </div>
    `).join('');

    el.querySelectorAll('.wl-remove-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        await fetch(`${API}/watchlist/${encodeURIComponent(btn.dataset.plate)}`, { method: 'DELETE' });
        loadWatchlist();
      });
    });
  } catch(e) {}
}

// ── Bind settings events ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Confidence slider
  const slider = document.getElementById('conf-slider');
  const valEl  = document.getElementById('conf-val');
  if (slider) {
    slider.addEventListener('input', () => {
      valEl.textContent = (slider.value / 100).toFixed(2);
    });
  }

  // Add watchlist
  document.getElementById('wl-add-btn')?.addEventListener('click', async () => {
    const plate  = document.getElementById('wl-plate')?.value.trim();
    const reason = document.getElementById('wl-reason')?.value.trim();
    if (!plate) return;
    try {
      await fetch(`${API}/watchlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate_text: plate, reason, added_by: 'operator' }),
      });
      document.getElementById('wl-plate').value  = '';
      document.getElementById('wl-reason').value = '';
      loadWatchlist();
    } catch(e) {}
  });
});

window.Settings = { load: loadSettings };
