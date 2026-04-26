/**
 * app.js — Frontend Logic for Neon Health Monitor
 * Handles data fetching, chart updates, and neon-themed UI management.
 */

// ─── Configuration ──────────────────────────────────────────────────────────
const API_BASE_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? "http://localhost:8000"
    : window.location.origin;
const REFRESH_INTERVAL = 10000; // Increased to 10 seconds for a smoother experience

// Neon Colors
const NEON = {
    cyan: '#00f2ff',
    magenta: '#ff00ff',
    green: '#39ff14',
    yellow: '#fff200',
    red: '#ff3131',
    blue: '#0047ff',
    purple: '#bc13fe'
};

// ─── State ──────────────────────────────────────────────────────────────────
let liveChart = null;
let historyChart = null;
let predictionChart = null;
let currentView = "dashboard";

// ─── Initialization ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    setupEventListeners();
    startDataLoop();

    // Initial fetch
    fetchSystemInfo();
    refreshAllData();
});

function setupEventListeners() {
    // Navigation
    document.querySelectorAll('.nav-links li').forEach(li => {
        li.addEventListener('click', () => {
            const view = li.getAttribute('data-view');
            switchView(view);

            // Highlight active link
            document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
            li.classList.add('active');
        });
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', async () => {
        const btn = document.getElementById('refresh-btn');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> SYNCING...';
        btn.disabled = true;

        try {
            await triggerManualCollection();
            await refreshAllData();
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });
}

function switchView(viewId) {
    currentView = viewId;

    // Update UI
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    document.getElementById(`${viewId}-view`).classList.remove('hidden');

    // Update Title
    const titles = {
        'dashboard': 'Dashboard',
        'charts': 'Metrics & Analytics',
        'anomalies': 'Anomaly Core',
        'system': 'System Kernel'
    };
    document.getElementById('view-title').innerText = titles[viewId];

    // Specialized refresh for specific views
    if (viewId === 'charts') refreshHistory();
    if (viewId === 'anomalies') refreshAnomalies();
    if (viewId === 'system') fetchSystemInfo();
}

// ─── Data Fetching ──────────────────────────────────────────────────────────
async function startDataLoop() {
    setInterval(() => {
        refreshCurrentMetrics();
    }, REFRESH_INTERVAL);
}

async function refreshAllData() {
    await Promise.all([
        refreshCurrentMetrics(),
        refreshHistory(),
        refreshAnomalies(),
        refreshPredictions()
    ]);
}

async function refreshCurrentMetrics() {
    try {
        const response = await fetch(`${API_BASE_URL}/metrics/current`);
        if (!response.ok) throw new Error("CORE OFFLINE");

        const data = await response.json();
        updateStatus(true);
        updateDashboardUI(data);
        updateLiveChart(data);
        updateProcessTable(data.processes?.top_10 || []);
    } catch (err) {
        console.error("Telemetry failure:", err);
        updateStatus(false);
    }
}

async function refreshHistory() {
    try {
        const response = await fetch(`${API_BASE_URL}/metrics/history?limit=30`);
        const data = await response.json();
        updateHistoryChart(data.data || []);
    } catch (err) {
        console.error("History retrieval failure:", err);
    }
}

async function refreshAnomalies() {
    try {
        const response = await fetch(`${API_BASE_URL}/anomalies`);
        const data = await response.json();
        updateAnomalyUI(data.anomalies || []);
    } catch (err) {
        console.error("Anomaly scan failure:", err);
    }
}

async function refreshPredictions() {
    try {
        const response = await fetch(`${API_BASE_URL}/predictions`);
        const data = await response.json();
        updatePredictionChart(data.predictions || []);
    } catch (err) {
        console.error("Prediction projection failure:", err);
    }
}

async function fetchSystemInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/metrics/current`);
        const data = await response.json();
        updateSystemInfo(data.system || {}, data.uptime_seconds);
    } catch (err) {
        console.error("Kernel info failure:", err);
    }
}

async function triggerManualCollection() {
    try {
        await fetch(`${API_BASE_URL}/metrics/collect`, { method: 'POST' });
    } catch (err) {
        console.error("Force sync failure:", err);
    }
}

// ─── UI Updates ─────────────────────────────────────────────────────────────
function updateStatus(online) {
    const dot = document.querySelector('.status-dot');
    const text = document.getElementById('api-status');

    if (online) {
        dot.className = 'status-dot neon-bg-green pulse';
        text.innerText = 'CORE: CONNECTED';
        text.className = 'neon-text-green';
    } else {
        dot.className = 'status-dot neon-bg-red';
        text.innerText = 'CORE: DISCONNECTED';
        text.className = 'neon-text-red';
    }

    document.getElementById('update-time').innerText = new Date().toLocaleTimeString();
}

function updateDashboardUI(data) {
    const score = data.health_score || 0;
    const cpu = data.cpu?.usage_percent || 0;
    const mem = data.memory?.usage_percent || 0;
    const disk = data.disk?.partitions?.[0]?.usage_percent || 0;

    // Health Score
    const scoreEl = document.getElementById('health-score');
    scoreEl.innerText = score;

    // Color logic
    let color = NEON.green;
    if (score < 50) color = NEON.red;
    else if (score < 80) color = NEON.yellow;

    document.querySelector('.score-circle').style.borderColor = color;
    document.querySelector('.score-circle').style.boxShadow = `0 0 30px ${color}33, inset 0 0 30px ${color}33`;
    scoreEl.style.color = color;
    scoreEl.style.textShadow = `0 0 15px ${color}`;

    // Summary Cards
    document.getElementById('hero-cpu').innerText = `${cpu}%`;
    document.getElementById('hero-mem').innerText = `${mem}%`;
    document.getElementById('hero-disk').innerText = `${disk}%`;

    document.getElementById('bar-cpu').style.width = `${cpu}%`;
    document.getElementById('bar-mem').style.width = `${mem}%`;
    document.getElementById('bar-disk').style.width = `${disk}%`;
}

function updateProcessTable(processes) {
    const tbody = document.getElementById('process-list');
    tbody.innerHTML = processes.map(p => `
        <tr>
            <td>${p.pid}</td>
            <td><strong>${p.name}</strong></td>
            <td class="neon-text-cyan">${p.cpu}%</td>
            <td class="neon-text-magenta">${p.mem}%</td>
        </tr>
    `).join('');
}

function updateAnomalyUI(anomalies) {
    const container = document.getElementById('anomaly-list');
    if (anomalies.length === 0) {
        container.innerHTML = '<div class="empty-state neon-text-green">NO THREATS DETECTED IN LOCAL KERNEL.</div>';
        return;
    }

    container.innerHTML = anomalies.map(a => `
        <div class="anomaly-item">
            <div class="anomaly-info">
                <h4>${a.anomaly_reasons.join(', ') || 'UNIDENTIFIED ANOMALY'}</h4>
                <div class="anomaly-time">${new Date(a.collected_at).toLocaleString()}</div>
            </div>
            <div class="anomaly-score neon-text-red">SCORE: ${a.anomaly_score}</div>
        </div>
    `).join('');
}

function updateSystemInfo(sys, uptime) {
    const grid = document.getElementById('system-info-grid');
    const days = Math.floor(uptime / 86400);
    const hrs = Math.floor((uptime % 86400) / 3600);
    const mins = Math.floor((uptime % 3600) / 60);

    const info = {
        'HOSTNAME': sys.hostname,
        'PLATFORM': sys.os,
        'VERSION': sys.os_release,
        'ARCH': sys.architecture,
        'RUNTIME': `PYTHON ${sys.python_version}`,
        'UPTIME': `${days}D ${hrs}H ${mins}M`
    };

    grid.innerHTML = Object.entries(info).map(([label, value]) => `
        <div class="info-item">
            <span class="label">${label}</span>
            <span class="value neon-text-cyan">${value}</span>
        </div>
    `).join('');
}

// ─── Charts ─────────────────────────────────────────────────────────────────
function initCharts() {
    Chart.defaults.color = '#888ba0';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';

    // Live Chart
    const liveCtx = document.getElementById('liveChart').getContext('2d');
    liveChart = new Chart(liveCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'CPU LOAD',
                    borderColor: NEON.cyan,
                    backgroundColor: NEON.cyan + '11',
                    data: [],
                    fill: true,
                    tension: 0.4,
                    borderWidth: 3,
                    pointRadius: 0
                },
                {
                    label: 'MEM LOAD',
                    borderColor: NEON.magenta,
                    backgroundColor: NEON.magenta + '11',
                    data: [],
                    fill: true,
                    tension: 0.4,
                    borderWidth: 3,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false } }
            },
            plugins: { legend: { labels: { font: { weight: 'bold' } } } },
            animation: { duration: 400 }
        }
    });

    // History Chart
    const histCtx = document.getElementById('historyChart').getContext('2d');
    historyChart = new Chart(histCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: '24H LOAD PROFILE',
                borderColor: NEON.blue,
                backgroundColor: NEON.blue + '22',
                data: [],
                fill: true,
                tension: 0.3,
                borderWidth: 2
            }]
        },
        options: {
            scales: { y: { min: 0, max: 100 } }
        }
    });

    // Prediction Chart
    const predCtx = document.getElementById('predictionChart').getContext('2d');
    predictionChart = new Chart(predCtx, {
        type: 'line',
        data: {
            labels: Array.from({length: 10}, (_, i) => `+${i+1}T`),
            datasets: [
                {
                    label: 'PROJ CPU',
                    borderColor: NEON.cyan,
                    borderDash: [5, 5],
                    data: [],
                    pointBackgroundColor: NEON.cyan
                },
                {
                    label: 'PROJ MEM',
                    borderColor: NEON.magenta,
                    borderDash: [5, 5],
                    data: [],
                    pointBackgroundColor: NEON.magenta
                }
            ]
        },
        options: {
            scales: { y: { min: 0, max: 100 } }
        }
    });
}

function updateLiveChart(data) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const cpu = data.cpu?.usage_percent || 0;
    const mem = data.memory?.usage_percent || 0;

    liveChart.data.labels.push(time);
    liveChart.data.datasets[0].data.push(cpu);
    liveChart.data.datasets[1].data.push(mem);

    if (liveChart.data.labels.length > 15) {
        liveChart.data.labels.shift();
        liveChart.data.datasets[0].data.shift();
        liveChart.data.datasets[1].data.shift();
    }
    // Update with 'none' mode to prevent jarring animations/fading every refresh
    liveChart.update('none');
}

function updateHistoryChart(rows) {
    const reversed = [...rows].reverse();
    historyChart.data.labels = reversed.map(r => new Date(r.collected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    historyChart.data.datasets[0].data = reversed.map(r => r.cpu_percent);
    historyChart.update();
}

function updatePredictionChart(predictions) {
    predictionChart.data.datasets[0].data = predictions.map(p => p.cpu_percent);
    predictionChart.data.datasets[1].data = predictions.map(p => p.mem_percent);
    predictionChart.update();
}
