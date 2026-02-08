// PM Automations Dashboard

const POLL_INTERVAL = 30_000; // 30 seconds
let pollTimer = null;
let historyCache = {}; // automation_id -> entries

// ---------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------

async function fetchAutomations() {
    try {
        const res = await fetch('/api/automations');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderDashboard(data);
    } catch (err) {
        console.error('Failed to fetch automations:', err);
        document.getElementById('scheduler-status').textContent = 'Error';
        document.getElementById('scheduler-status').style.color = 'var(--error-color)';
    }
    document.getElementById('last-poll').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

async function triggerAutomation(id) {
    try {
        const res = await fetch(`/api/automations/${id}/trigger`, { method: 'POST' });
        if (!res.ok) {
            const data = await res.json();
            alert(data.detail || 'Failed to trigger');
            return;
        }
        // Immediately refresh
        setTimeout(fetchAutomations, 500);
    } catch (err) {
        alert('Error triggering automation: ' + err.message);
    }
}

async function toggleAutomation(id, enabled) {
    try {
        const res = await fetch(`/api/automations/${id}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        fetchAutomations();
    } catch (err) {
        alert('Error toggling automation: ' + err.message);
    }
}

async function fetchHistory(id) {
    try {
        const res = await fetch(`/api/automations/${id}/history?limit=10`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        historyCache[id] = data.entries || [];
        renderHistory(id);
    } catch (err) {
        console.error('Failed to fetch history:', err);
    }
}

// ---------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------

function renderDashboard(data) {
    // Meta bar
    const statusEl = document.getElementById('scheduler-status');
    if (data.scheduler_running) {
        statusEl.textContent = 'Running';
        statusEl.style.color = 'var(--success-color)';
    } else {
        statusEl.textContent = 'Stopped';
        statusEl.style.color = 'var(--error-color)';
    }
    document.getElementById('tz').textContent = data.timezone || '--';

    // Cards
    const container = document.getElementById('automations-container');
    if (!data.automations || data.automations.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:4rem 0;color:var(--text-secondary)">No automations configured. Add one in config/automations.json</div>';
        return;
    }

    // Preserve expanded state
    const expandedIds = new Set();
    container.querySelectorAll('.auto-card.expanded').forEach(el => expandedIds.add(el.dataset.id));

    container.innerHTML = data.automations.map(a => renderCard(a, expandedIds.has(a.id))).join('');
}

function renderCard(auto, expanded) {
    const badge = getBadge(auto);
    const schedule = formatSchedule(auto.schedule);
    const lastRun = auto.last_run || {};
    const lastTime = lastRun.time ? formatRelative(lastRun.time) : '--';
    const lastDur = lastRun.duration_seconds != null ? formatDuration(lastRun.duration_seconds) : '--';
    const nextRun = auto.next_run ? formatRelative(auto.next_run) : '--';

    return `
    <div class="auto-card ${expanded ? 'expanded' : ''}" data-id="${auto.id}">
        <div class="auto-card-header" onclick="toggleCard('${auto.id}')">
            <div class="auto-card-left">
                <div class="auto-card-name">${esc(auto.name)}</div>
                <div class="auto-card-desc">${esc(auto.description || '')}</div>
            </div>
            <div class="auto-card-right">
                ${badge}
                <label class="toggle" onclick="event.stopPropagation()">
                    <input type="checkbox" ${auto.enabled ? 'checked' : ''} onchange="toggleAutomation('${auto.id}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>
        <div class="auto-card-body">
            <div class="detail-grid">
                <div class="detail-item"><label>Schedule</label><div class="val">${esc(schedule)}</div></div>
                <div class="detail-item"><label>Next Run</label><div class="val">${esc(nextRun)}</div></div>
                <div class="detail-item"><label>Last Run</label><div class="val">${esc(lastTime)} ${lastRun.status ? '(' + lastRun.status + ', ' + lastDur + ')' : ''}</div></div>
                <div class="detail-item"><label>Runs / Failures</label><div class="val">${auto.run_count} / ${auto.fail_count}</div></div>
            </div>
            ${lastRun.error ? '<div style="color:var(--error-color);font-size:0.8rem;margin-bottom:1rem;">Error: ' + esc(lastRun.error) + '</div>' : ''}
            <div class="auto-card-actions">
                <button onclick="triggerAutomation('${auto.id}')" ${auto.currently_running || !auto.enabled ? 'disabled' : ''}>
                    ${auto.currently_running ? 'Running...' : 'Run Now'}
                </button>
                <button onclick="fetchHistory('${auto.id}')">Refresh History</button>
            </div>
            <div class="history-section" id="history-${auto.id}">
                <h4>Run History</h4>
                ${renderHistoryTable(auto.id)}
            </div>
        </div>
    </div>`;
}

function renderHistory(id) {
    const section = document.getElementById('history-' + id);
    if (!section) return;
    section.innerHTML = '<h4>Run History</h4>' + renderHistoryTable(id);
}

function renderHistoryTable(id) {
    const entries = historyCache[id];
    if (!entries || entries.length === 0) {
        return '<div class="history-empty">No runs yet. Click "Run Now" or wait for the next scheduled time.</div>';
    }
    let rows = entries.map(e => {
        const time = new Date(e.timestamp).toLocaleString();
        const badgeCls = e.status === 'success' ? 'badge-success' : 'badge-failed';
        const dur = e.duration_seconds != null ? formatDuration(e.duration_seconds) : '--';
        const stepsOk = (e.steps || []).filter(s => s.status === 'success').length;
        const stepsTotal = (e.steps || []).length;
        return `<tr>
            <td>${esc(time)}</td>
            <td><span class="badge ${badgeCls}">${esc(e.status)}</span></td>
            <td>${dur}</td>
            <td>${stepsOk}/${stepsTotal} steps</td>
            <td>${esc(e.triggered_by || '')}</td>
        </tr>`;
    }).join('');

    return `<table class="history-table">
        <thead><tr><th>Time</th><th>Status</th><th>Duration</th><th>Steps</th><th>Trigger</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function getBadge(auto) {
    if (!auto.enabled) return '<span class="badge badge-disabled">Disabled</span>';
    if (auto.currently_running) return '<span class="badge badge-running">Running</span>';
    if (!auto.last_run || !auto.last_run.status) return '<span class="badge badge-idle">Idle</span>';
    if (auto.last_run.status === 'success') return '<span class="badge badge-success">Success</span>';
    return '<span class="badge badge-failed">Failed</span>';
}

function formatSchedule(schedule) {
    if (!schedule) return '--';
    const times = (schedule.times || []).map(t => {
        const [h, m] = t.split(':').map(Number);
        const suffix = h >= 12 ? 'PM' : 'AM';
        const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h;
        return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
    });
    const days = schedule.days === 'mon-fri' ? 'Mon-Fri' : schedule.days === '*' ? 'Daily' : schedule.days;
    return times.join(', ') + ' EST (' + days + ')';
}

function formatRelative(isoString) {
    const d = new Date(isoString);
    const now = new Date();
    const diffMs = now - d;

    if (diffMs < 0) {
        // Future
        const mins = Math.round(-diffMs / 60000);
        if (mins < 60) return `in ${mins}m`;
        const hrs = Math.round(mins / 60);
        if (hrs < 24) return `in ${hrs}h`;
        return d.toLocaleString();
    }

    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return d.toLocaleString();
}

function formatDuration(seconds) {
    if (seconds < 60) return seconds.toFixed(1) + 's';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
}

function toggleCard(id) {
    const card = document.querySelector(`.auto-card[data-id="${id}"]`);
    if (!card) return;
    const wasExpanded = card.classList.contains('expanded');
    card.classList.toggle('expanded');
    // Fetch history on first expand
    if (!wasExpanded && !historyCache[id]) {
        fetchHistory(id);
    }
}

function esc(str) {
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
}

// ---------------------------------------------------------------
// Init
// ---------------------------------------------------------------

fetchAutomations();
pollTimer = setInterval(fetchAutomations, POLL_INTERVAL);
