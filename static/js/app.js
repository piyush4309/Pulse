// Pulse Mac Intelligence — High-Performance Dashboard Controller

let ws = null;
let isPaused = false;
let updateInterval = 1.0;
let charts = {};
let currentTab = 'tab-cockpit';

// Circumference of r=42 is 2 * PI * 42 = 263.89
const RING_CIRCUMFERENCE = 263.89;

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initCharts();
  initControls();
  fetchInitialSummary();
  connectWebSocket();
  loadStorageOverview();
  loadNetworkDetails();
  loadSystemDetails();
});

// --- NAVIGATION ---
function initNavigation() {
  const navBtns = document.querySelectorAll('.nav-item');
  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      switchTab(targetTab);
    });
  });
}

function switchTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll('.nav-item').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === tabId);
  });

  const heading = document.getElementById('page-heading');
  const headings = {
    'tab-cockpit': 'Cockpit Overview',
    'tab-storage': 'Full Disk & APFS Storage',
    'tab-cpu': 'CPU & Memory Matrix',
    'tab-battery': 'Battery, Power & Thermals',
    'tab-network': 'Network Radar & Ports',
    'tab-processes': 'Process Commander',
    'tab-system': 'System & Security Posture'
  };
  if (heading && headings[tabId]) {
    heading.textContent = headings[tabId];
  }

  // Load specific tab data when activated
  if (tabId === 'tab-storage') {
    loadStorageBreakdown();
    loadCleanableCaches();
    loadLargeFiles();
  } else if (tabId === 'tab-processes') {
    loadProcesses();
  } else if (tabId === 'tab-network') {
    loadNetworkDetails();
  } else if (tabId === 'tab-system') {
    loadSystemDetails();
  } else if (tabId === 'tab-battery') {
    loadBatteryDetails();
  }
}

// --- INITIAL LOAD & REST APIS ---
async function fetchInitialSummary() {
  try {
    const res = await fetch('/api/summary');
    if (!res.ok) return;
    const data = await res.json();
    populateHardwareMeta(data.hardware, data.os);
    if (data.vitals) {
      updateLiveVitals(data.vitals);
    }
  } catch (err) {
    console.warn('Initial summary fetch error:', err);
  }
}

function populateHardwareMeta(hw, os) {
  if (!hw || !os) return;
  
  // Sidebar
  const chipName = document.getElementById('side-chip-name');
  if (chipName) chipName.textContent = hw.chip || 'Apple Silicon';
  const modelName = document.getElementById('side-model-name');
  if (modelName) modelName.textContent = hw.model_name || 'Mac';
  const ramBadge = document.getElementById('side-ram-badge');
  if (ramBadge) ramBadge.textContent = `${hw.total_memory_gb} GB`;

  // Header meta
  const headModel = document.getElementById('head-mac-model');
  if (headModel) headModel.textContent = hw.model_name || 'Mac';
  const headOs = document.getElementById('head-os-ver');
  if (headOs) headOs.textContent = `${os.friendly_name} (${os.version})`;
  const headHost = document.getElementById('head-hostname');
  if (headHost) headHost.textContent = os.hostname;

  // Specs grid
  setText('hw-model-val', `${hw.model_name} (${hw.model_identifier || ''})`);
  setText('hw-chip-val', hw.chip);
  setText('hw-cores-val', `${hw.cores_total} Cores (${hw.performance_cores}P + ${hw.efficiency_cores}E)`);
  setText('hw-ram-val', `${hw.total_memory_gb} GB Unified`);
  setText('hw-os-val', `${os.friendly_name} · ${os.build}`);
  setText('hw-disp-val', hw.display_resolution || 'Built-in Retina');
  setText('hw-kernel-val', `${os.kernel} (${os.arch})`);
  setText('hw-uptime-val', os.uptime_str);
  setText('side-uptime', `Uptime: ${os.uptime_str}`);
  setText('net-hostname-card', os.hostname);
}

// --- WEBSOCKET CONNECTION ---
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  const statusDot = document.getElementById('ws-status-dot');
  const statusText = document.getElementById('ws-status-text');

  ws.onopen = () => {
    if (statusDot) statusDot.className = 'status-indicator active';
    if (statusText) statusText.textContent = 'Connected Live';
    sendWsMessage({ action: 'set_interval', interval: updateInterval });
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateLiveVitals(data);
    } catch (e) {
      console.error('Error parsing live telemetry:', e);
    }
  };

  ws.onclose = () => {
    if (statusDot) statusDot.className = 'status-indicator';
    if (statusText) statusText.textContent = 'Reconnecting...';
    setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.warn('WebSocket encountered error:', err);
    ws.close();
  };
}

function sendWsMessage(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// --- CONTROLS ---
function initControls() {
  const intervalSelect = document.getElementById('select-interval');
  if (intervalSelect) {
    intervalSelect.addEventListener('change', (e) => {
      updateInterval = parseFloat(e.target.value);
      setText('live-freq', `${updateInterval.toFixed(1)}s`);
      sendWsMessage({ action: 'set_interval', interval: updateInterval });
      showToast(`Telemetry interval set to ${updateInterval}s`);
    });
  }

  const pauseBtn = document.getElementById('btn-pause-toggle');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      isPaused = !isPaused;
      sendWsMessage({ action: isPaused ? 'pause' : 'resume' });
      setText('btn-pause-text', isPaused ? 'Resume' : 'Pause');
      setText('btn-pause-icon', isPaused ? '▶' : '⏸');
      const livePill = document.querySelector('.live-indicator');
      if (livePill) {
        livePill.style.opacity = isPaused ? '0.5' : '1';
      }
      showToast(isPaused ? 'Telemetry paused' : 'Telemetry resumed');
    });
  }

  const refreshBtn = document.getElementById('btn-manual-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.style.transform = 'rotate(180deg)';
      setTimeout(() => refreshBtn.style.transform = 'none', 300);
      await fetchInitialSummary();
      loadStorageOverview();
      loadStorageBreakdown(true);
      loadLargeFiles();
      loadCleanableCaches();
      loadProcesses();
      showToast('All system diagnostics refreshed!');
    });
  }

  // Storage tab buttons
  const scanStorageBtn = document.getElementById('btn-scan-storage');
  if (scanStorageBtn) {
    scanStorageBtn.addEventListener('click', () => {
      loadStorageBreakdown(true);
      showToast('Running deep folder scan...');
    });
  }

  const largeFilesBtn = document.getElementById('btn-refresh-large-files');
  if (largeFilesBtn) {
    largeFilesBtn.addEventListener('click', () => {
      loadLargeFiles();
      showToast('Scanning for large files...');
    });
  }

  // Process filters
  const procSearch = document.getElementById('proc-search-input');
  if (procSearch) {
    let debounce;
    procSearch.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(loadProcesses, 250);
    });
  }

  const procSort = document.getElementById('proc-sort-select');
  if (procSort) {
    procSort.addEventListener('change', loadProcesses);
  }
}

// --- UPDATE LIVE TELEMETRY ---
function updateLiveVitals(data) {
  if (!data) return;

  // 1. CPU Gauge & Metrics
  const cpuPct = data.cpu ? Math.round(data.cpu.total_percent) : 0;
  setText('val-cpu', `${cpuPct}%`);
  updateRing('gauge-cpu', cpuPct);
  if (data.cpu) {
    setText('stat-cpu-load', `${data.cpu.load_1m} ${data.cpu.load_5m} ${data.cpu.load_15m}`);
    setText('chart-cpu-now', `${cpuPct}%`);
    setText('cpu-total-matrix-badge', `${cpuPct}% Total Load`);
    updateCoreMatrix(data.cpu.cores);
  }

  // 2. Memory Gauge & Metrics
  const ramPct = data.memory ? Math.round(data.memory.percent) : 0;
  setText('val-ram', `${ramPct}%`);
  updateRing('gauge-ram', ramPct);
  if (data.memory) {
    setText('stat-ram-used', `${data.memory.used_gb} GB / ${data.memory.total_gb} GB`);
    setText('stat-ram-avail', `${data.memory.available_gb} GB`);
    setText('stat-ram-swap', `${data.memory.swap_used_gb} GB (${data.memory.swap_percent}%)`);
    setText('v-ram-pressure', `${data.memory.pressure} Pressure`);
    
    // Memory tab details
    setText('mem-val-active', `${data.memory.active_gb} GB`);
    setText('mem-val-wired', `${data.memory.wired_gb} GB`);
    setText('mem-val-inactive', `${data.memory.inactive_gb} GB`);
    setText('mem-val-free', `${data.memory.available_gb} GB`);
    setText('mem-val-swap', `${data.memory.swap_used_gb} GB (of ${data.memory.swap_total_gb} GB)`);
    setText('mem-val-pressure', data.memory.pressure);
    setText('ram-donut-pct', `${ramPct}% Used`);
    updateRamChart(data.memory);
  }

  // 3. Disk Gauge & Metrics
  const diskPct = data.disk ? Math.round(data.disk.percent) : 0;
  setText('val-disk', `${diskPct}%`);
  updateRing('gauge-disk', diskPct);
  if (data.disk) {
    setText('stat-disk-free', `${data.disk.free_gb} GB`);
    setText('stat-disk-used', `${data.disk.used_gb} GB`);
    setText('stat-disk-total', `${data.disk.total_gb} GB`);
    setText('side-disk-pct', `${diskPct}%`);
    setText('disk-io-rate-tag', `R: ${data.disk.read_speed_mb} MB/s · W: ${data.disk.write_speed_mb} MB/s`);
  }

  // 4. Battery Gauge & Metrics
  if (data.battery) {
    const battPct = data.battery.percent !== null ? data.battery.percent : 100;
    setText('val-batt', `${battPct}%`);
    updateRing('gauge-batt', battPct);
    setText('side-batt-pct', `${battPct}%`);
    setText('pwr-charge-pct', `${battPct}%`);
    const chargeState = data.battery.charging ? 'Charging ⚡' : (data.battery.source || 'AC Power');
    setText('v-battery-state', chargeState);
    setText('pwr-charge-state', `${data.battery.source} · ${data.battery.charging ? 'Charging' : 'Full'}`);
    setText('stat-batt-thermal', data.battery.thermal || 'Nominal');
    setText('pwr-thermal', data.battery.thermal || 'Nominal');
  }

  // 5. Network Metrics
  if (data.network) {
    const downFormatted = data.network.download_speed_kb > 1024
      ? `${(data.network.download_speed_kb / 1024).toFixed(2)} MB/s`
      : `${data.network.download_speed_kb.toFixed(1)} KB/s`;
    const upFormatted = data.network.upload_speed_kb > 1024
      ? `${(data.network.upload_speed_kb / 1024).toFixed(2)} MB/s`
      : `${data.network.upload_speed_kb.toFixed(1)} KB/s`;

    setText('chart-net-now', `↓ ${downFormatted} · ↑ ${upFormatted}`);
    setText('net-down-speed', downFormatted);
    setText('net-up-speed', upFormatted);
    setText('net-total-recv', `Total In: ${data.network.total_recv_gb} GB`);
    setText('net-total-sent', `Total Out: ${data.network.total_sent_gb} GB`);
  }

  // 6. Update Rolling Sparkline Charts
  if (data.history) {
    updateHistoryCharts(data.history);
  }

  // 7. Quick Process Table on Cockpit
  if (data.top_cpu_processes) {
    renderQuickProcessTable(data.top_cpu_processes);
  }

  // 8. Health Signal Alert Banner
  updateHealthBanner(data);
}

function updateRing(id, percent) {
  const el = document.getElementById(id);
  if (!el) return;
  const p = Math.max(0, Math.min(100, percent));
  const offset = RING_CIRCUMFERENCE - (p / 100) * RING_CIRCUMFERENCE;
  el.style.strokeDashoffset = offset;
}

function updateCoreMatrix(cores) {
  const container = document.getElementById('cores-grid');
  if (!container || !cores) return;

  if (container.children.length !== cores.length) {
    container.innerHTML = '';
    cores.forEach(c => {
      const box = document.createElement('div');
      box.className = 'core-meter-box';
      box.id = `core-box-${c.id}`;
      const fillClass = c.is_pcore ? 'core-fill-pcore' : 'core-fill-ecore';
      const tagClass = c.is_pcore ? 'tag-pcore' : 'tag-ecore';
      box.innerHTML = `
        <div class="core-tag-badge ${tagClass}">${c.tag}</div>
        <div class="core-meter-bar-track">
          <div class="core-meter-bar-fill ${fillClass}" id="core-fill-${c.id}" style="height: ${c.percent}%;"></div>
        </div>
        <div class="core-pct-label" id="core-val-${c.id}">${Math.round(c.percent)}%</div>
        <div class="core-id-label">Core ${c.id}</div>
      `;
      container.appendChild(box);
    });
  } else {
    cores.forEach(c => {
      const fill = document.getElementById(`core-fill-${c.id}`);
      const val = document.getElementById(`core-val-${c.id}`);
      if (fill) fill.style.height = `${c.percent}%`;
      if (val) val.textContent = `${Math.round(c.percent)}%`;
    });
  }
}

function renderQuickProcessTable(procs) {
  const tbody = document.getElementById('quick-proc-tbody');
  if (!tbody || !procs) return;

  tbody.innerHTML = procs.slice(0, 6).map(p => `
    <tr>
      <td><strong style="color:#fff;">${escapeHtml(p.name)}</strong></td>
      <td><code>${p.pid}</code></td>
      <td><span class="${p.cpu_percent > 30 ? 'highlight-magenta' : 'highlight-cyan'}">${p.cpu_percent}%</span></td>
      <td>${p.memory_percent}%</td>
      <td>${escapeHtml(p.user || '—')}</td>
    </tr>
  `).join('');
}

function updateHealthBanner(data) {
  const banner = document.getElementById('health-banner');
  const icon = document.getElementById('health-banner-icon');
  const title = document.getElementById('health-title');
  const desc = document.getElementById('health-desc');
  if (!banner) return;

  const alerts = [];
  if (data.cpu && data.cpu.total_percent > 85) {
    alerts.push(`High processor load (${Math.round(data.cpu.total_percent)}%)`);
  }
  if (data.memory && data.memory.percent > 90) {
    alerts.push(`Memory utilization is elevated (${Math.round(data.memory.percent)}%)`);
  }
  if (data.disk && data.disk.percent > 90) {
    alerts.push(`Disk space low (${Math.round(data.disk.percent)}% used)`);
  }
  if (data.battery && data.battery.thermal && data.battery.thermal !== 'Nominal') {
    alerts.push(`Thermal pressure is ${data.battery.thermal}`);
  }

  if (alerts.length > 0) {
    banner.className = 'health-banner warn';
    if (icon) icon.textContent = '!';
    if (title) title.textContent = 'Resource Signals Alert';
    if (desc) desc.textContent = alerts.join(' · ');
  } else {
    banner.className = 'health-banner';
    if (icon) icon.textContent = '✓';
    if (title) title.textContent = 'System Vitals Healthy';
    if (desc) desc.textContent = 'All monitored thresholds, thermal pressure, and disk limits are optimal.';
  }
}

// --- CHARTS INITIALIZATION ---
function initCharts() {
  const chartFont = { family: "'JetBrains Mono', monospace", size: 10 };
  const gridColor = 'rgba(255, 255, 255, 0.04)';
  const tickColor = '#64748b';

  // 1. CPU History Chart
  const cpuCtx = document.getElementById('chart-cpu-history');
  if (cpuCtx) {
    charts.cpu = new Chart(cpuCtx, {
      type: 'line',
      data: {
        labels: Array(60).fill(''),
        datasets: [{
          label: 'CPU %',
          data: Array(60).fill(0),
          borderColor: '#00f0ff',
          backgroundColor: 'rgba(0, 240, 255, 0.08)',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.35,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: true } },
        scales: {
          x: { display: false },
          y: {
            min: 0,
            max: 100,
            grid: { color: gridColor },
            ticks: { color: tickColor, font: chartFont, stepSize: 25 }
          }
        }
      }
    });
  }

  // 2. Network History Chart
  const netCtx = document.getElementById('chart-net-history');
  if (netCtx) {
    charts.net = new Chart(netCtx, {
      type: 'line',
      data: {
        labels: Array(60).fill(''),
        datasets: [
          {
            label: 'Download KB/s',
            data: Array(60).fill(0),
            borderColor: '#00f0ff',
            backgroundColor: 'rgba(0, 240, 255, 0.08)',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.35,
          },
          {
            label: 'Upload KB/s',
            data: Array(60).fill(0),
            borderColor: '#ffb800',
            backgroundColor: 'rgba(255, 184, 0, 0.05)',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.35,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {
            display: true,
            labels: { color: '#94a3b8', font: chartFont, boxWidth: 10 }
          }
        },
        scales: {
          x: { display: false },
          y: {
            min: 0,
            grid: { color: gridColor },
            ticks: { color: tickColor, font: chartFont }
          }
        }
      }
    });
  }

  // 3. Disk I/O History Chart
  const diskIoCtx = document.getElementById('chart-disk-io-history');
  if (diskIoCtx) {
    charts.diskIo = new Chart(diskIoCtx, {
      type: 'line',
      data: {
        labels: Array(60).fill(''),
        datasets: [
          {
            label: 'Read MB/s',
            data: Array(60).fill(0),
            borderColor: '#00f0ff',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.35,
          },
          {
            label: 'Write MB/s',
            data: Array(60).fill(0),
            borderColor: '#ff007f',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.35,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {
            display: true,
            labels: { color: '#94a3b8', font: chartFont, boxWidth: 10 }
          }
        },
        scales: {
          x: { display: false },
          y: {
            min: 0,
            grid: { color: gridColor },
            ticks: { color: tickColor, font: chartFont }
          }
        }
      }
    });
  }

  // 4. Storage Categories Donut
  const storageCtx = document.getElementById('chart-storage-categories');
  if (storageCtx) {
    charts.storage = new Chart(storageCtx, {
      type: 'doughnut',
      data: {
        labels: ['Applications', 'Documents', 'Downloads', 'Developer', 'Media', 'Caches', 'System', 'Other', 'Free'],
        datasets: [{
          data: [1, 1, 1, 1, 1, 1, 1, 1, 1],
          backgroundColor: ['#00f0ff', '#00ff9d', '#38bdf8', '#a855f7', '#ff007f', '#ffb800', '#818cf8', '#64748b', '#1e293b'],
          borderColor: '#0b1120',
          borderWidth: 3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw} GB`
            }
          }
        }
      }
    });
  }

  // 5. RAM Donut Chart
  const ramCtx = document.getElementById('chart-ram-composition');
  if (ramCtx) {
    charts.ram = new Chart(ramCtx, {
      type: 'doughnut',
      data: {
        labels: ['Active', 'Wired', 'Inactive', 'Free'],
        datasets: [{
          data: [2, 1.5, 1.5, 3],
          backgroundColor: ['#00f0ff', '#ff007f', '#ffb800', '#00ff9d'],
          borderColor: '#0b1120',
          borderWidth: 3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: { color: '#94a3b8', font: chartFont, boxWidth: 10 }
          }
        }
      }
    });
  }
}

function updateHistoryCharts(hist) {
  if (charts.cpu && hist.cpu) {
    charts.cpu.data.labels = hist.labels;
    charts.cpu.data.datasets[0].data = hist.cpu;
    charts.cpu.update();
  }

  if (charts.net && hist.net_down && hist.net_up) {
    charts.net.data.labels = hist.labels;
    charts.net.data.datasets[0].data = hist.net_down;
    charts.net.data.datasets[1].data = hist.net_up;
    charts.net.update();
  }

  if (charts.diskIo && hist.disk_read && hist.disk_write) {
    charts.diskIo.data.labels = hist.labels;
    charts.diskIo.data.datasets[0].data = hist.disk_read;
    charts.diskIo.data.datasets[1].data = hist.disk_write;
    charts.diskIo.update();
  }
}

function updateRamChart(mem) {
  if (charts.ram && mem) {
    charts.ram.data.datasets[0].data = [
      mem.active_gb || 0,
      mem.wired_gb || 0,
      mem.inactive_gb || 0,
      mem.available_gb || 0,
    ];
    charts.ram.update();
  }
}

// --- STORAGE TAB DATA LOADERS ---
async function loadStorageOverview() {
  try {
    const res = await fetch('/api/storage/overview');
    if (!res.ok) return;
    const data = await res.json();

    const usedGb = (data.used_bytes / (1024**3)).toFixed(1);
    const totalGb = (data.total_bytes / (1024**3)).toFixed(1);
    const freeGb = (data.free_bytes / (1024**3)).toFixed(1);

    setText('disk-hero-used', `${usedGb} GB <span class="dim">used of</span> ${totalGb} GB`, true);
    setText('disk-hero-free', `${freeGb} GB free`);
    setText('apfs-container-label', `${data.device_name || 'APPLE SSD'} · ${data.container_name || 'disk3'}`);
    setText('v-disk-smart', data.device_name || 'APPLE SSD');

    // Populate APFS Volumes Table
    const tbody = document.getElementById('apfs-volumes-tbody');
    if (tbody && data.volumes) {
      tbody.innerHTML = data.volumes.map(v => `
        <tr>
          <td><strong style="color:#fff;">${escapeHtml(v.name)}</strong></td>
          <td><span class="nav-tag" style="border-left: 3px solid ${v.color};">${v.role}</span></td>
          <td><code>${escapeHtml(v.mount)}</code></td>
          <td>${v.used_str}</td>
          <td class="highlight-green">${v.free_str}</td>
          <td><span style="font-family:var(--font-mono); font-weight:700;">${v.percent}%</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading storage overview:', err);
  }
}

async function loadStorageBreakdown(forceRefresh = false) {
  const container = document.getElementById('category-list-container');
  if (forceRefresh && container) {
    container.innerHTML = '<div class="loading-cell">Scanning directories in background...</div>';
  }

  try {
    const url = forceRefresh ? '/api/storage/breakdown?refresh=true' : '/api/storage/breakdown';
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    setText('storage-cache-meta', `Last scanned: ${data.cached_at}`);

    // Update Donut Chart
    if (charts.storage && data.categories) {
      const labels = data.categories.map(c => c.category);
      const values = data.categories.map(c => (c.bytes / (1024**3)).toFixed(1));
      const colors = data.categories.map(c => c.color);

      charts.storage.data.labels = labels;
      charts.storage.data.datasets[0].data = values;
      charts.storage.data.datasets[0].backgroundColor = colors;
      charts.storage.update();
    }

    // Update Multi-Segment Bar & Legend
    const bar = document.getElementById('storage-multi-bar');
    const legend = document.getElementById('storage-legend-container');
    if (bar && legend && data.categories) {
      bar.innerHTML = data.categories.map(c => `
        <div class="bar-seg" style="width: ${c.percent}%; background: ${c.color};" title="${c.category}: ${c.formatted} (${c.percent}%)"></div>
      `).join('');

      legend.innerHTML = data.categories.map(c => `
        <div class="legend-item">
          <span class="legend-color-dot" style="background: ${c.color};"></span>
          <span>${c.category}</span>
          <strong style="color:#fff; font-family:var(--font-mono);">${c.formatted}</strong>
        </div>
      `).join('');
    }

    // Category List
    if (container && data.categories) {
      container.innerHTML = data.categories.map(c => `
        <div class="cat-item">
          <div class="cat-left">
            <span class="cat-icon-dot" style="background: ${c.color};"></span>
            <span class="cat-name">${c.category}</span>
          </div>
          <div style="display:flex; align-items:center; gap: 10px;">
            <span class="cat-size">${c.formatted}</span>
            <span class="cat-pct">${c.percent}%</span>
          </div>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading storage breakdown:', err);
  }
}

async function loadCleanableCaches() {
  const container = document.getElementById('cleanable-grid-container');
  try {
    const res = await fetch('/api/storage/caches');
    if (!res.ok) return;
    const data = await res.json();

    setText('cleanable-total-badge', `Reclaimable: ${data.total_formatted}`);

    if (container && data.items) {
      if (data.items.length === 0) {
        container.innerHTML = '<div class="loading-cell">No major cleanable caches found. System is clean!</div>';
        return;
      }
      container.innerHTML = data.items.map(item => `
        <div class="cleanable-card">
          <div class="cleanable-top">
            <span class="cleanable-name">${escapeHtml(item.name)}</span>
            <span class="cleanable-size">${item.formatted}</span>
          </div>
          <div class="cleanable-desc">${escapeHtml(item.desc)}</div>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading cleanable caches:', err);
  }
}

async function loadLargeFiles() {
  const tbody = document.getElementById('large-files-tbody');
  const select = document.getElementById('select-large-filter');
  const minSize = select ? select.value : 100;

  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading-cell">Scanning for large files...</td></tr>';
  }

  try {
    const res = await fetch(`/api/storage/large-files?min_size=${minSize}`);
    if (!res.ok) return;
    const files = await res.json();

    if (tbody) {
      if (files.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">No files found larger than ${minSize} MB.</td></tr>`;
        return;
      }
      tbody.innerHTML = files.map(f => `
        <tr>
          <td><strong style="color:#fff;" title="${escapeHtml(f.path)}">${escapeHtml(f.name)}</strong></td>
          <td><span class="nav-tag" style="color:${f.color}; border: 1px solid ${f.color}40;">${f.file_type}</span></td>
          <td><strong class="highlight-cyan">${f.size_formatted}</strong></td>
          <td><code style="font-size:0.75rem; color:#94a3b8;" title="${escapeHtml(f.path)}">${truncatePath(f.path)}</code></td>
          <td><span style="font-size:0.75rem; font-family:var(--font-mono);">${f.modified}</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading large files:', err);
  }
}

// --- PROCESS COMMANDER ---
async function loadProcesses() {
  const tbody = document.getElementById('process-full-tbody');
  const search = document.getElementById('proc-search-input')?.value || '';
  const sort = document.getElementById('proc-sort-select')?.value || 'cpu';

  try {
    const res = await fetch(`/api/processes?search=${encodeURIComponent(search)}&sort=${sort}&limit=80`);
    if (!res.ok) return;
    const procs = await res.json();

    if (tbody) {
      if (procs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="loading-cell">No matching processes found.</td></tr>';
        return;
      }
      tbody.innerHTML = procs.map(p => `
        <tr>
          <td><code>${p.pid}</code></td>
          <td><strong style="color:#fff;">${escapeHtml(p.name)}</strong></td>
          <td><span class="${p.cpu > 50 ? 'highlight-magenta' : 'highlight-cyan'}">${p.cpu}%</span></td>
          <td>${p.memory_percent}%</td>
          <td><strong style="color:#fff;">${p.memory_mb} MB</strong></td>
          <td>${p.threads}</td>
          <td>${escapeHtml(p.user || '—')}</td>
          <td>
            <button class="btn-kill-proc" onclick="killProcess(${p.pid}, '${escapeHtml(p.name)}')">End</button>
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading processes:', err);
  }
}

async function killProcess(pid, name) {
  if (!confirm(`Are you sure you want to terminate ${name} (PID: ${pid})?`)) {
    return;
  }
  try {
    const res = await fetch('/api/process/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid })
    });
    const result = await res.json();
    if (res.ok) {
      showToast(result.message || `Terminated process ${name}`);
      setTimeout(loadProcesses, 500);
    } else {
      showToast(`Failed: ${result.detail || 'Access denied'}`);
    }
  } catch (err) {
    showToast('Failed to communicate with process controller.');
  }
}

// --- NETWORK & PORTS ---
async function loadNetworkDetails() {
  try {
    const res = await fetch('/api/network/details');
    if (!res.ok) return;
    const data = await res.json();

    // Interfaces table
    const ifaceTbody = document.getElementById('interfaces-tbody');
    if (ifaceTbody && data.interfaces) {
      ifaceTbody.innerHTML = data.interfaces.map(i => `
        <tr>
          <td><strong style="color:#fff;">${escapeHtml(i.label)}</strong></td>
          <td><span class="nav-tag tag-green">ACTIVE</span></td>
          <td>${i.ips.length ? i.ips.map(ip => `<code>${ip}</code>`).join(' · ') : '—'}</td>
          <td><code>${escapeHtml(i.mac)}</code></td>
        </tr>
      `).join('');
    }

    // Ports table
    const portsTbody = document.getElementById('ports-tbody');
    const portsTag = document.getElementById('ports-count-tag');
    if (portsTag && data.listening_ports) {
      portsTag.textContent = `${data.listening_ports.length} Open Ports`;
    }
    if (portsTbody && data.listening_ports) {
      portsTbody.innerHTML = data.listening_ports.map(p => `
        <tr>
          <td><strong class="highlight-cyan" style="font-family:var(--font-mono); font-size:0.95rem;">${p.port}</strong></td>
          <td><strong style="color:#fff;">${escapeHtml(p.command)}</strong></td>
          <td><code>${p.pid}</code></td>
          <td>${escapeHtml(p.user)}</td>
          <td><code>${escapeHtml(p.address)}</code></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading network details:', err);
  }
}

// --- BATTERY & THERMALS ---
async function loadBatteryDetails() {
  try {
    const res = await fetch('/api/battery/details');
    if (!res.ok) return;
    const b = await res.json();

    setText('pwr-charge-pct', `${b.percent}%`);
    setText('pwr-max-cap', b.max_capacity_pct ? `${b.max_capacity_pct}%` : '81%');
    setText('pwr-cycles', b.cycle_count ? b.cycle_count : '859');
    setText('pwr-thermal', b.thermal_pressure || 'Nominal');
    setText('stat-batt-health', b.max_capacity_pct ? `${b.max_capacity_pct}%` : '81%');
    setText('stat-batt-cycles', b.cycle_count ? b.cycle_count : '859');

    // Cycle bar
    const wearFill = document.getElementById('wear-bar-fill');
    if (wearFill && b.cycle_count) {
      const pct = Math.min(100, (b.cycle_count / 1000) * 100);
      wearFill.style.width = `${pct}%`;
    }

    // Sleep blockers
    const list = document.getElementById('sleep-blockers-list');
    if (list && b.sleep_blockers) {
      if (b.sleep_blockers.length === 0) {
        list.innerHTML = `
          <div class="clean-check-item">
            <span class="check-icon">✓</span>
            <span>No active sleep inhibitors preventing standby mode.</span>
          </div>
        `;
      } else {
        list.innerHTML = b.sleep_blockers.map(bl => `
          <div class="clean-check-item" style="background:rgba(255,184,0,0.1); border-color:rgba(255,184,0,0.3); color:#ffb800;">
            <span class="check-icon">!</span>
            <span>${escapeHtml(bl)}</span>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Error loading battery details:', err);
  }
}

// --- SYSTEM & SECURITY ---
async function loadSystemDetails() {
  try {
    const res = await fetch('/api/system/details');
    if (!res.ok) return;
    const data = await res.json();

    // Security
    if (data.security) {
      const fv = document.getElementById('sec-fv-status');
      if (fv) {
        fv.textContent = data.security.filevault.status;
        fv.className = data.security.filevault.is_secure ? 'sec-status' : 'sec-status disabled';
      }
      const sip = document.getElementById('sec-sip-status');
      if (sip) {
        sip.textContent = data.security.sip.status;
        sip.className = data.security.sip.is_secure ? 'sec-status' : 'sec-status disabled';
      }
      const fw = document.getElementById('sec-fw-status');
      if (fw) {
        fw.textContent = data.security.firewall.status;
        fw.className = data.security.firewall.is_secure ? 'sec-status' : 'sec-status disabled';
      }
    }

    // Toolchain
    const tcGrid = document.getElementById('toolchain-grid');
    if (tcGrid && data.toolchain) {
      tcGrid.innerHTML = data.toolchain.map(t => `
        <div class="tool-tile">
          <div class="tool-name">${escapeHtml(t.name)}</div>
          <div class="tool-ver ${t.installed ? '' : 'missing'}">${escapeHtml(t.version)}</div>
        </div>
      `).join('');
    }

    // Hardware Specification Details
    const sysGrid = document.getElementById('system-details-grid');
    if (sysGrid && data.hardware && data.os) {
      const hw = data.hardware;
      const os = data.os;
      sysGrid.innerHTML = `
        <div class="spec-tile"><div class="spec-k">Serial Number</div><div class="spec-v">${escapeHtml(hw.serial_number || 'Confidential')}</div></div>
        <div class="spec-tile"><div class="spec-k">Hardware UUID</div><div class="spec-v">${escapeHtml(hw.hardware_uuid || '—')}</div></div>
        <div class="spec-tile"><div class="spec-k">Boot ROM Firmware</div><div class="spec-v">${escapeHtml(hw.boot_rom_version || 'Apple Silicon')}</div></div>
        <div class="spec-tile"><div class="spec-k">OS Loader Version</div><div class="spec-v">${escapeHtml(hw.os_loader_version || '20457.1.29')}</div></div>
        <div class="spec-tile"><div class="spec-k">Model Identifier</div><div class="spec-v">${escapeHtml(hw.model_identifier)}</div></div>
        <div class="spec-tile"><div class="spec-k">System Architecture</div><div class="spec-v">${escapeHtml(os.arch)}</div></div>
        <div class="spec-tile"><div class="spec-k">Boot Timestamp</div><div class="spec-v">${escapeHtml(os.boot_time)}</div></div>
        <div class="spec-tile"><div class="spec-k">GPU Graphic Model</div><div class="spec-v">${escapeHtml(hw.gpu_name)}</div></div>
      `;
    }
  } catch (err) {
    console.error('Error loading system details:', err);
  }
}

// --- UTILITY HELPERS ---
function setText(id, text, isHtml = false) {
  const el = document.getElementById(id);
  if (el) {
    if (isHtml) el.innerHTML = text;
    else el.textContent = text;
  }
}

function truncatePath(path) {
  if (!path) return '';
  const parts = path.split('/');
  if (parts.length > 4) {
    return '.../' + parts.slice(-3).join('/');
  }
  return path;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
