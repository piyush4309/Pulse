import os
import re
import socket
import subprocess
import platform
import time
from datetime import datetime, timedelta
import psutil

# Cache static hardware info to keep queries sub-millisecond
_STATIC_HW_CACHE = None

def run_cmd(cmd: str, timeout: float = 4.0) -> str:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (res.stdout or res.stderr).strip()
    except Exception:
        return ""

def get_static_hardware():
    global _STATIC_HW_CACHE
    if _STATIC_HW_CACHE is not None:
        return _STATIC_HW_CACHE

    info = {
        "model_name": "Mac",
        "model_identifier": run_cmd("sysctl -n hw.model"),
        "chip": run_cmd("sysctl -n machdep.cpu.brand_string") or "Apple Silicon",
        "cores_total": psutil.cpu_count(logical=True) or 8,
        "cores_physical": psutil.cpu_count(logical=False) or 8,
        "performance_cores": run_cmd("sysctl -n hw.perflevel0.logicalcpu 2>/dev/null") or "4",
        "efficiency_cores": run_cmd("sysctl -n hw.perflevel1.logicalcpu 2>/dev/null") or "4",
        "total_memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "total_memory_bytes": psutil.virtual_memory().total,
        "serial_number": "",
        "hardware_uuid": "",
        "boot_rom_version": "",
        "os_loader_version": "",
        "model_number": "",
        "gpu_name": "",
        "display_resolution": "",
    }

    # Query system_profiler SPHardwareDataType
    try:
        hw_raw = run_cmd("system_profiler SPHardwareDataType", timeout=5)
        for line in hw_raw.splitlines():
            line = line.strip()
            if "Model Name:" in line:
                info["model_name"] = line.split(":", 1)[1].strip()
            elif "Serial Number" in line:
                info["serial_number"] = line.split(":", 1)[1].strip()
            elif "Hardware UUID:" in line:
                info["hardware_uuid"] = line.split(":", 1)[1].strip()
            elif "Boot ROM Version:" in line or "System Firmware Version:" in line:
                info["boot_rom_version"] = line.split(":", 1)[1].strip()
            elif "OS Loader Version:" in line:
                info["os_loader_version"] = line.split(":", 1)[1].strip()
            elif "Model Number:" in line:
                info["model_number"] = line.split(":", 1)[1].strip()
            elif "Chip:" in line and not info["chip"]:
                info["chip"] = line.split(":", 1)[1].strip()
    except Exception:
        pass

    # Query GPU and Display
    try:
        disp_raw = run_cmd("system_profiler SPDisplaysDataType", timeout=5)
        for line in disp_raw.splitlines():
            line = line.strip()
            if "Chipset Model:" in line and not info["gpu_name"]:
                info["gpu_name"] = line.split(":", 1)[1].strip()
            elif "Resolution:" in line and not info["display_resolution"]:
                info["display_resolution"] = line.split(":", 1)[1].strip()
    except Exception:
        pass

    if not info["gpu_name"]:
        info["gpu_name"] = info["chip"]

    _STATIC_HW_CACHE = info
    return info

def get_os_info():
    sw = run_cmd("sw_vers")
    product_name = "macOS"
    product_version = platform.mac_ver()[0] or "macOS"
    build_version = ""

    for line in sw.splitlines():
        if "ProductName:" in line:
            product_name = line.split(":", 1)[1].strip()
        elif "ProductVersion:" in line:
            product_version = line.split(":", 1)[1].strip()
        elif "BuildVersion:" in line:
            build_version = line.split(":", 1)[1].strip()

    # Determine friendly release name
    major = product_version.split(".")[0] if product_version else ""
    names = {
        "15": "macOS Sequoia",
        "14": "macOS Sonoma",
        "13": "macOS Ventura",
        "12": "macOS Monterey",
        "11": "macOS Big Sur",
        "27": "macOS Sequoia Developer",
    }
    friendly_name = names.get(major, f"macOS {product_version}")

    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime_sec = int(time.time() - psutil.boot_time())
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"

    return {
        "product_name": product_name,
        "friendly_name": friendly_name,
        "version": product_version,
        "build": build_version,
        "kernel": platform.release(),
        "arch": platform.machine(),
        "hostname": socket.gethostname(),
        "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_str": uptime_str,
        "uptime_seconds": uptime_sec,
    }

def get_battery_and_power():
    res = {
        "present": False,
        "percent": None,
        "charging": False,
        "power_source": "AC Power",
        "cycle_count": None,
        "max_capacity_pct": None,
        "condition": "Normal",
        "thermal_pressure": "Nominal",
        "sleep_blockers": [],
    }

    # 1. Quick pmset check
    batt_str = run_cmd("pmset -g batt")
    if batt_str:
        res["present"] = "InternalBattery" in batt_str
        m = re.search(r"(\d+)%", batt_str)
        if m:
            res["percent"] = int(m.group(1))
        res["charging"] = "charging" in batt_str.lower() and "discharging" not in batt_str.lower()
        if "Battery Power" in batt_str:
            res["power_source"] = "Battery"
        elif "AC Power" in batt_str:
            res["power_source"] = "AC Power"

    # 2. Detailed battery health (cached for 30s)
    pwr_str = run_cmd("system_profiler SPPowerDataType", timeout=4)
    if pwr_str:
        cycle_m = re.search(r"Cycle Count:\s*(\d+)", pwr_str)
        if cycle_m:
            res["cycle_count"] = int(cycle_m.group(1))

        cond_m = re.search(r"Condition:\s*(.+)", pwr_str)
        if cond_m:
            res["condition"] = cond_m.group(1).strip()

        cap_m = re.search(r"Maximum Capacity:\s*(\d+)%", pwr_str)
        if cap_m:
            res["max_capacity_pct"] = int(cap_m.group(1))

    # 3. Thermal State
    therm_str = run_cmd("pmset -g therm")
    if "Serious" in therm_str:
        res["thermal_pressure"] = "Serious"
    elif "Critical" in therm_str:
        res["thermal_pressure"] = "Critical"
    elif "Fair" in therm_str:
        res["thermal_pressure"] = "Fair"
    else:
        res["thermal_pressure"] = "Nominal"

    # 4. Sleep assertions
    assertions = run_cmd("pmset -g assertions")
    blockers = []
    for line in assertions.splitlines():
        if "PreventUserIdleSystemSleep" in line and "1" in line:
            blockers.append("System Idle Sleep Prevented")
        elif "PreventUserIdleDisplaySleep" in line and "1" in line:
            blockers.append("Display Sleep Prevented")
    res["sleep_blockers"] = list(set(blockers))

    return res

def get_security_posture():
    filevault = run_cmd("fdesetup status")
    sip = run_cmd("csrutil status")
    firewall = run_cmd("/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate")

    fv_enabled = "FileVault is On" in filevault
    sip_enabled = "enabled" in sip.lower()
    fw_enabled = "enabled" in firewall.lower() and "State = 1" in firewall

    return {
        "filevault": {
            "status": "Enabled" if fv_enabled else "Disabled",
            "is_secure": fv_enabled,
            "raw": filevault,
        },
        "sip": {
            "status": "Enabled" if sip_enabled else "Disabled",
            "is_secure": sip_enabled,
            "raw": sip,
        },
        "firewall": {
            "status": "Enabled" if fw_enabled else "Disabled",
            "is_secure": fw_enabled,
            "raw": firewall,
        },
    }

def get_developer_toolchain():
    tools = [
        {"name": "Python 3", "icon": "python", "cmd": "python3 --version"},
        {"name": "Node.js", "icon": "node", "cmd": "node --version"},
        {"name": "npm", "icon": "npm", "cmd": "npm --version"},
        {"name": "Git", "icon": "git", "cmd": "git --version"},
        {"name": "Docker", "icon": "docker", "cmd": "docker --version"},
        {"name": "Homebrew", "icon": "brew", "cmd": "brew --version | head -n 1"},
        {"name": "Java", "icon": "java", "cmd": "java --version 2>&1 | head -n 1"},
        {"name": "Rust / Cargo", "icon": "rust", "cmd": "cargo --version"},
        {"name": "Go", "icon": "go", "cmd": "go version"},
        {"name": "Xcode CLI", "icon": "apple", "cmd": "xcode-select -p"},
    ]

    results = []
    for t in tools:
        out = run_cmd(t["cmd"], timeout=1.5)
        installed = bool(out and "not found" not in out.lower() and "error" not in out.lower())
        version = out if installed else "Not installed"
        # Clean up version string
        if installed:
            version = version.replace("version", "").replace("Homebrew", "").replace("Apple Git-", "Git-").strip()
            if len(version) > 40:
                version = version[:40] + "..."
        results.append({
            "name": t["name"],
            "icon": t["icon"],
            "installed": installed,
            "version": version
        })

    return results
