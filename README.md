# ◉ PULSE — Mac Intelligence Dashboard

An ultra-modern, colourful, and interactive macOS system monitoring dashboard with real-time WebSocket telemetry, APFS deep disk storage analysis, Apple Silicon per-core matrix, and process inspection.

---

## 🚀 Quick Start

Run in your activated virtual environment:

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Install requirements (if not already installed)
pip install -r requirements.txt

# 3. Launch Pulse Dashboard (Standalone High-Performance Web App)
python app.py
```

Pulse will automatically open your default web browser at **`http://127.0.0.1:8501`**.

> **Note:** Dual-mode execution is supported! If you run `streamlit run app.py`, Pulse seamlessly detects the Streamlit environment and embeds the full live interactive dashboard.

---

## 🌟 Key Features

### 1. 💾 Full Disk Storage & APFS Intelligence
- **APFS Container Architecture**: Visual allocation bar for physical container capacity, free space, and mount roles.
- **Volume Inspection**: Real-time roles for Macintosh HD (System snapshot), Data volume (`/System/Volumes/Data`), Virtual Memory (`/System/Volumes/VM`), and Preboot.
- **Category Space Breakdown**: Applications, Documents & Desktop, Downloads, Developer Tools, Media (Photos/Videos), Caches & Logs, and System Base.
- **Large Files Hunter**: Scans and surfaces files > 100 MB, > 250 MB, > 500 MB, and > 1 GB with file type badges and paths.
- **Cleanable Caches Advisor**: Identifies safe-to-clean developer artifacts (`npm`, `pip`, `homebrew`, `gradle`, `Xcode DerivedData`, Trash).

### 2. ⚡ Live Apple Silicon Core Matrix
- **8-Core Dynamic Grid**: Per-core load meters for **4 Performance Cores** (Cyan) and **4 Efficiency Cores** (Magenta).
- **Smooth 60-Second Timeline**: Real-time processor utilization history updated every 1 second via WebSockets.
- **Load Averages**: 1-minute, 5-minute, and 15-minute system load metrics.

### 3. 🧠 Unified Memory Deep-Dive
- **Mach Virtual Memory Composition**: Visual breakdown of Active, Wired (unpageable), Inactive, and Free memory.
- **Memory Pressure Level**: Activity Monitor-grade pressure indicator (Normal / Warning / Critical).
- **APFS Swap Space**: Real-time swap file usage.

### 4. 🔋 Battery, Power & Thermals
- **Battery Health**: Maximum Capacity (e.g. 81%), Cycle Count (e.g. 859 / 1,000 Apple rated cycles), and Wear Progress Bar.
- **Thermal State**: Real-time thermal pressure status.
- **Power Assertions**: Sleep blockers and background inhibitors.

### 5. ⌁ Network Radar & Port Scanner
- **Live Throughput**: Real-time Download and Upload speedometers with historical line charts.
- **Interface Inspection**: Active network interfaces (`en0` Wi-Fi, Ethernet, Loopback, VPN tunnels) with assigned IP addresses and MACs.
- **Open Listening Ports**: Active TCP listening sockets with command name, PID, user, and bind address.

### 6. ≡ Process Commander
- Searchable and sortable live process manager with CPU %, RAM %, memory in MB, thread counts, and an **End Task** action button.

### 7. ⚙️ System & Security Posture
- **Security Check**: FileVault encryption, System Integrity Protection (SIP), Application Firewall.
- **Toolchain Detector**: Versions of Python 3, Node.js, npm, Git, Docker, Homebrew, Java, Rust, Go, Xcode CLI.
- **Hardware Profile**: Chip model, Serial number, Hardware UUID, OS Loader version, Boot ROM version, and display resolution.
