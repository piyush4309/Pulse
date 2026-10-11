import time
import os
import re
import socket
import subprocess
import psutil
from collections import deque
from datetime import datetime

class MetricsCollector:
    def __init__(self, history_len: int = 60):
        self.history_len = history_len
        self.prev_time = time.time()
        self.prev_net = psutil.net_io_counters()
        self.prev_disk = psutil.disk_io_counters()

        # Rolling history buffers for charts
        self.cpu_history = deque(maxlen=history_len)
        self.net_down_history = deque(maxlen=history_len)
        self.net_up_history = deque(maxlen=history_len)
        self.disk_read_history = deque(maxlen=history_len)
        self.disk_write_history = deque(maxlen=history_len)
        self.time_history = deque(maxlen=history_len)

        # Pre-seed history with zeros so charts render cleanly immediately
        now = time.time()
        for i in range(history_len):
            t_str = datetime.fromtimestamp(now - (history_len - i)).strftime("%H:%M:%S")
            self.time_history.append(t_str)
            self.cpu_history.append(0.0)
            self.net_down_history.append(0.0)
            self.net_up_history.append(0.0)
            self.disk_read_history.append(0.0)
            self.disk_write_history.append(0.0)

        # Prime psutil CPU non-blocking
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

        self._cached_battery = None
        self._last_battery_poll = 0

    def _get_battery_quick(self):
        now = time.time()
        if self._cached_battery and (now - self._last_battery_poll) < 4:
            return self._cached_battery

        res = {"percent": 100, "charging": False, "source": "AC Power", "thermal": "Nominal"}
        try:
            p = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=1.5)
            s = p.stdout
            m = re.search(r"(\d+)%", s)
            if m:
                res["percent"] = int(m.group(1))
            res["charging"] = "charging" in s.lower() and "discharging" not in s.lower()
            if "Battery Power" in s:
                res["source"] = "Battery"
        except Exception:
            pass

        try:
            p = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=1.5)
            st = p.stdout
            if "Serious" in st:
                res["thermal"] = "Serious"
            elif "Critical" in st:
                res["thermal"] = "Critical"
            elif "Fair" in st:
                res["thermal"] = "Fair"
        except Exception:
            pass

        self._cached_battery = res
        self._last_battery_poll = now
        return res

    def get_live_metrics(self):
        now = time.time()
        dt = max(now - self.prev_time, 0.001)

        # 1. CPU
        total_cpu = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        # Format core list with performance vs efficiency tags (M1 has 4 P-Cores, 4 E-Cores)
        cores_data = []
        for idx, val in enumerate(per_core):
            tag = "P-Core" if idx < 4 else "E-Core"
            cores_data.append({
                "id": idx + 1,
                "label": f"Core {idx+1}",
                "tag": tag,
                "percent": val,
                "is_pcore": idx < 4,
            })

        load_1m, load_5m, load_15m = os.getloadavg()

        # 2. Memory
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Estimate memory pressure: Normal, Warning, Critical
        # On macOS, memory pressure is a function of available / total + swap
        free_ratio = vm.available / vm.total
        if free_ratio < 0.10 or swap.percent > 70:
            mem_pressure = "Critical"
            pressure_color = "#ff007f"
        elif free_ratio < 0.20 or swap.percent > 40:
            mem_pressure = "Warning"
            pressure_color = "#ffb800"
        else:
            mem_pressure = "Normal"
            pressure_color = "#00ff9d"

        # 3. Disk I/O Rates
        curr_disk = psutil.disk_io_counters()
        read_speed_mb = 0.0
        write_speed_mb = 0.0
        if curr_disk and self.prev_disk:
            read_speed_mb = max(0.0, round((curr_disk.read_bytes - self.prev_disk.read_bytes) / (1024 * 1024 * dt), 2))
            write_speed_mb = max(0.0, round((curr_disk.write_bytes - self.prev_disk.write_bytes) / (1024 * 1024 * dt), 2))
        self.prev_disk = curr_disk

        # 4. Network I/O Rates
        curr_net = psutil.net_io_counters()
        down_speed_kb = 0.0
        up_speed_kb = 0.0
        if curr_net and self.prev_net:
            down_speed_kb = max(0.0, round((curr_net.bytes_recv - self.prev_net.bytes_recv) / (1024 * dt), 1))
            up_speed_kb = max(0.0, round((curr_net.bytes_sent - self.prev_net.bytes_sent) / (1024 * dt), 1))
        self.prev_net = curr_net

        self.prev_time = now

        # Append to rolling histories
        time_str = datetime.now().strftime("%H:%M:%S")
        self.time_history.append(time_str)
        self.cpu_history.append(total_cpu)
        self.net_down_history.append(down_speed_kb)
        self.net_up_history.append(up_speed_kb)
        self.disk_read_history.append(read_speed_mb)
        self.disk_write_history.append(write_speed_mb)

        # 5. Top 8 processes by CPU & RAM
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username']):
            try:
                info = p.info
                cpu_p = info.get('cpu_percent') or 0.0
                mem_p = info.get('memory_percent') or 0.0
                name = info.get('name') or 'Unknown'
                # psutil process cpu_percent can exceed 100 on multi-core
                procs.append({
                    "pid": info['pid'],
                    "name": name,
                    "cpu_percent": round(cpu_p, 1),
                    "memory_percent": round(mem_p, 1),
                    "user": info.get('username') or "",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        top_cpu_procs = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:8]
        top_ram_procs = sorted(procs, key=lambda x: x["memory_percent"], reverse=True)[:8]

        # 6. Battery quick
        batt = self._get_battery_quick()

        # 7. Disk usage (Data volume)
        try:
            du = psutil.disk_usage('/System/Volumes/Data')
            disk_total_gb = round(du.total / (1024**3), 1)
            disk_used_gb = round(du.used / (1024**3), 1)
            disk_free_gb = round(du.free / (1024**3), 1)
            disk_pct = du.percent
        except Exception:
            du = psutil.disk_usage('/')
            disk_total_gb = round(du.total / (1024**3), 1)
            disk_used_gb = round(du.used / (1024**3), 1)
            disk_free_gb = round(du.free / (1024**3), 1)
            disk_pct = du.percent

        return {
            "timestamp": time_str,
            "cpu": {
                "total_percent": total_cpu,
                "cores": cores_data,
                "load_1m": round(load_1m, 2),
                "load_5m": round(load_5m, 2),
                "load_15m": round(load_15m, 2),
            },
            "memory": {
                "percent": vm.percent,
                "total_gb": round(vm.total / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "free_gb": round(vm.free / (1024**3), 2),
                "active_gb": round(getattr(vm, 'active', 0) / (1024**3), 2),
                "inactive_gb": round(getattr(vm, 'inactive', 0) / (1024**3), 2),
                "wired_gb": round(getattr(vm, 'wired', 0) / (1024**3), 2),
                "swap_used_gb": round(swap.used / (1024**3), 2),
                "swap_total_gb": round(swap.total / (1024**3), 2),
                "swap_percent": swap.percent,
                "pressure": mem_pressure,
                "pressure_color": pressure_color,
            },
            "disk": {
                "total_gb": disk_total_gb,
                "used_gb": disk_used_gb,
                "free_gb": disk_free_gb,
                "percent": disk_pct,
                "read_speed_mb": read_speed_mb,
                "write_speed_mb": write_speed_mb,
            },
            "network": {
                "download_speed_kb": down_speed_kb,
                "upload_speed_kb": up_speed_kb,
                "total_recv_gb": round(curr_net.bytes_recv / (1024**3), 2),
                "total_sent_gb": round(curr_net.bytes_sent / (1024**3), 2),
            },
            "battery": batt,
            "history": {
                "labels": list(self.time_history),
                "cpu": list(self.cpu_history),
                "net_down": list(self.net_down_history),
                "net_up": list(self.net_up_history),
                "disk_read": list(self.disk_read_history),
                "disk_write": list(self.disk_write_history),
            },
            "top_cpu_processes": top_cpu_procs,
            "top_ram_processes": top_ram_procs,
            "total_process_count": len(procs),
        }

    def get_all_processes(self, search="", sort_by="cpu_percent", limit=100):
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info', 'status', 'username', 'num_threads']):
            try:
                info = p.info
                name = info.get('name') or 'Unknown'
                if search and search.lower() not in name.lower() and search.lower() not in str(info['pid']):
                    continue
                rss_mb = round((info.get('memory_info').rss if info.get('memory_info') else 0) / (1024*1024), 1)
                procs.append({
                    "pid": info['pid'],
                    "name": name,
                    "cpu": round(info.get('cpu_percent') or 0.0, 1),
                    "memory_percent": round(info.get('memory_percent') or 0.0, 1),
                    "memory_mb": rss_mb,
                    "status": info.get('status') or "running",
                    "user": info.get('username') or "",
                    "threads": info.get('num_threads') or 1,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        reverse = True
        if sort_by in ["name", "pid", "status", "user"]:
            reverse = False

        if sort_by == "cpu":
            sort_by = "cpu"
        elif sort_by == "ram" or sort_by == "memory":
            sort_by = "memory_mb"

        try:
            procs.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
        except Exception:
            procs.sort(key=lambda x: x["cpu"], reverse=True)

        return procs[:limit]

    def get_listening_ports(self):
        try:
            p = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=2.5)
            lines = p.stdout.strip().splitlines()
        except Exception:
            return []

        results = []
        # Header: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 9:
                cmd = parts[0]
                pid = parts[1]
                user = parts[2]
                name_field = parts[8] # e.g. *:7000 or 127.0.0.1:8000
                port = name_field.split(":")[-1] if ":" in name_field else name_field
                results.append({
                    "command": cmd,
                    "pid": pid,
                    "user": user,
                    "address": name_field,
                    "port": port,
                })
        return results

    def get_network_interfaces(self):
        interfaces = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        for name, stat in stats.items():
            if not stat.isup:
                continue
            ip_list = []
            mac = None
            if name in addrs:
                for a in addrs[name]:
                    if a.family == socket.AF_INET:
                        ip_list.append(a.address)
                    elif hasattr(psutil, 'AF_LINK') and a.family == psutil.AF_LINK:
                        mac = a.address

            # Pretty name
            label = name
            if name == "en0":
                label = "en0 (Wi-Fi / Primary)"
            elif name == "lo0":
                label = "lo0 (Loopback Localhost)"
            elif "utun" in name:
                label = f"{name} (VPN / Tunnel)"
            elif "bridge" in name:
                label = f"{name} (Thunderbolt Bridge)"

            interfaces.append({
                "interface": name,
                "label": label,
                "speed_mbps": stat.speed,
                "is_up": stat.isup,
                "ips": ip_list,
                "mac": mac or "—",
            })

        return interfaces
