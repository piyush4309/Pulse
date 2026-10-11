import os
import subprocess
import time
import re
import psutil
from datetime import datetime
from threading import Lock

_BREAKDOWN_CACHE = None
_CACHE_TIMESTAMP = 0
_CACHE_LOCK = Lock()

def run_cmd(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or p.stderr).strip()
    except Exception:
        return ""

def format_bytes(b):
    if b is None or b < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"

def get_apfs_overview():
    res = {
        "device_name": "APPLE SSD",
        "container_name": "disk3",
        "total_bytes": 0,
        "used_bytes": 0,
        "free_bytes": 0,
        "percent_used": 0.0,
        "volumes": [],
        "snapshots": [],
        "smart_status": "Verified",
        "protocol": "PCI-Express / Apple Fabric",
    }

    # 1. Inspect APFS container with diskutil
    raw_apfs = run_cmd("diskutil apfs list", timeout=4)
    # Parse container size
    size_m = re.search(r"Size \(Capacity Ceiling\):\s*(\d+)\s*B", raw_apfs)
    if size_m:
        res["total_bytes"] = int(size_m.group(1))

    in_use_m = re.search(r"Capacity In Use By Volumes:\s*(\d+)\s*B", raw_apfs)
    if in_use_m:
        res["used_bytes"] = int(in_use_m.group(1))

    free_m = re.search(r"Capacity Not Allocated:\s*(\d+)\s*B", raw_apfs)
    if free_m:
        res["free_bytes"] = int(free_m.group(1))

    if res["total_bytes"] > 0:
        res["percent_used"] = round((res["used_bytes"] / res["total_bytes"]) * 100, 1)

    # Physical drive model name
    try:
        sp_out = run_cmd("system_profiler SPStorageDataType -json", timeout=4)
        if "APPLE SSD" in sp_out:
            for line in sp_out.splitlines():
                if "device_name" in line and "SSD" in line:
                    res["device_name"] = line.split(":", 1)[1].replace('"', '').replace(',', '').strip()
                    break
    except Exception:
        pass

    # 2. Key Volumes
    # Volumes of interest: /, /System/Volumes/Data, /System/Volumes/VM, /System/Volumes/Preboot
    volume_targets = [
        {"name": "Macintosh HD - Data", "mount": "/System/Volumes/Data", "role": "Data", "color": "#00f0ff"},
        {"name": "Macintosh HD (System)", "mount": "/", "role": "System", "color": "#a855f7"},
        {"name": "Virtual Memory (VM)", "mount": "/System/Volumes/VM", "role": "VM / Swap", "color": "#ffb800"},
        {"name": "Preboot & Recovery", "mount": "/System/Volumes/Preboot", "role": "Bootloader", "color": "#ff007f"},
    ]

    for vt in volume_targets:
        if os.path.exists(vt["mount"]):
            try:
                st = os.statvfs(vt["mount"])
                total = st.f_blocks * st.f_frsize
                free = st.f_bavail * st.f_frsize
                used = total - free
                
                # Get more specific usage from diskutil info if available
                res["volumes"].append({
                    "name": vt["name"],
                    "mount": vt["mount"],
                    "role": vt["role"],
                    "color": vt["color"],
                    "total_bytes": total,
                    "used_bytes": used,
                    "free_bytes": free,
                    "used_str": format_bytes(used),
                    "total_str": format_bytes(total),
                    "free_str": format_bytes(free),
                    "percent": round((used / total) * 100, 1) if total > 0 else 0
                })
            except Exception:
                pass

    # Fallback if container size wasn't captured from regex
    if res["total_bytes"] == 0 and res["volumes"]:
        primary = res["volumes"][0]
        res["total_bytes"] = primary["total_bytes"]
        res["free_bytes"] = primary["free_bytes"]
        res["used_bytes"] = primary["used_bytes"]
        res["percent_used"] = primary["percent"]

    # 3. Snapshots
    snap_out = run_cmd("diskutil apfs listSnapshots /System/Volumes/Data 2>/dev/null", timeout=3)
    if "No snapshots" not in snap_out:
        for line in snap_out.splitlines():
            line = line.strip()
            if line.startswith("Snapshot:"):
                res["snapshots"].append(line.replace("Snapshot:", "").strip())

    return res

def _measure_dir_kb(path, timeout=3.0):
    if not os.path.exists(path):
        return 0
    try:
        p = subprocess.run(["du", "-sk", path], capture_output=True, text=True, timeout=timeout)
        if p.returncode == 0 and p.stdout:
            parts = p.stdout.strip().split()
            if parts:
                return int(parts[0])
    except Exception:
        pass
    return 0

def get_storage_breakdown(force_refresh=False):
    global _BREAKDOWN_CACHE, _CACHE_TIMESTAMP
    with _CACHE_LOCK:
        now = time.time()
        if not force_refresh and _BREAKDOWN_CACHE is not None and (now - _CACHE_TIMESTAMP) < 180:
            return _BREAKDOWN_CACHE

        home = os.path.expanduser("~")
        
        # Measure folder sizes
        apps_kb = _measure_dir_kb("/Applications", timeout=3.5)
        user_apps_kb = _measure_dir_kb(os.path.join(home, "Applications"), timeout=1.5)
        downloads_kb = _measure_dir_kb(os.path.join(home, "Downloads"), timeout=2.5)
        docs_kb = _measure_dir_kb(os.path.join(home, "Documents"), timeout=2.5)
        desktop_kb = _measure_dir_kb(os.path.join(home, "Desktop"), timeout=1.5)
        movies_kb = _measure_dir_kb(os.path.join(home, "Movies"), timeout=1.5)
        pictures_kb = _measure_dir_kb(os.path.join(home, "Pictures"), timeout=1.5)
        music_kb = _measure_dir_kb(os.path.join(home, "Music"), timeout=1.5)
        developer_kb = _measure_dir_kb(os.path.join(home, "Library/Developer"), timeout=2.5)
        caches_kb = _measure_dir_kb(os.path.join(home, "Library/Caches"), timeout=2.5)
        npm_kb = _measure_dir_kb(os.path.join(home, ".npm"), timeout=1.5)

        # Overview totals
        apfs = get_apfs_overview()
        total_disk_bytes = apfs["total_bytes"]
        free_disk_bytes = apfs["free_bytes"]

        total_apps_bytes = (apps_kb + user_apps_kb) * 1024
        total_dev_bytes = (developer_kb + npm_kb) * 1024
        total_docs_bytes = (docs_kb + desktop_kb) * 1024
        total_media_bytes = (movies_kb + pictures_kb + music_kb) * 1024
        total_downloads_bytes = downloads_kb * 1024
        total_caches_bytes = caches_kb * 1024

        # System volume
        system_bytes = 14 * (1024**3) # Approximate sealed system
        for v in apfs.get("volumes", []):
            if v["mount"] == "/":
                system_bytes = v["used_bytes"]

        measured_used = total_apps_bytes + total_dev_bytes + total_docs_bytes + total_media_bytes + total_downloads_bytes + total_caches_bytes + system_bytes
        total_used_actual = apfs["used_bytes"]
        other_bytes = max(0, total_used_actual - measured_used)

        breakdown = [
            {"category": "Applications", "bytes": total_apps_bytes, "formatted": format_bytes(total_apps_bytes), "color": "#00f0ff", "icon": "app"},
            {"category": "Documents & Desktop", "bytes": total_docs_bytes, "formatted": format_bytes(total_docs_bytes), "color": "#00ff9d", "icon": "document"},
            {"category": "Downloads", "bytes": total_downloads_bytes, "formatted": format_bytes(total_downloads_bytes), "color": "#38bdf8", "icon": "download"},
            {"category": "Developer & Tools", "bytes": total_dev_bytes, "formatted": format_bytes(total_dev_bytes), "color": "#a855f7", "icon": "code"},
            {"category": "Media (Photos/Video)", "bytes": total_media_bytes, "formatted": format_bytes(total_media_bytes), "color": "#ff007f", "icon": "media"},
            {"category": "Caches & Logs", "bytes": total_caches_bytes, "formatted": format_bytes(total_caches_bytes), "color": "#ffb800", "icon": "cache"},
            {"category": "macOS System Base", "bytes": system_bytes, "formatted": format_bytes(system_bytes), "color": "#818cf8", "icon": "system"},
            {"category": "System Data & Other", "bytes": other_bytes, "formatted": format_bytes(other_bytes), "color": "#64748b", "icon": "other"},
            {"category": "Free Available", "bytes": free_disk_bytes, "formatted": format_bytes(free_disk_bytes), "color": "#1e293b", "icon": "free"},
        ]

        # Calculate percentages
        for item in breakdown:
            item["percent"] = round((item["bytes"] / total_disk_bytes) * 100, 1) if total_disk_bytes > 0 else 0

        _BREAKDOWN_CACHE = {
            "total_bytes": total_disk_bytes,
            "total_formatted": format_bytes(total_disk_bytes),
            "free_bytes": free_disk_bytes,
            "free_formatted": format_bytes(free_disk_bytes),
            "used_bytes": total_used_actual,
            "used_formatted": format_bytes(total_used_actual),
            "categories": breakdown,
            "cached_at": datetime.now().strftime("%H:%M:%S")
        }
        _CACHE_TIMESTAMP = now
        return _BREAKDOWN_CACHE

def get_large_files(min_size_mb=100, max_results=30):
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Movies"),
        os.path.join(home, "Music"),
    ]
    valid_dirs = [d for d in search_dirs if os.path.exists(d)]
    if not valid_dirs:
        return []

    cmd = ["find"] + valid_dirs + ["-type", "f", "-size", f"+{min_size_mb}M", "-exec", "stat", "-f", "%z|%m|%N", "{}", "+"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        lines = p.stdout.strip().splitlines()
    except Exception:
        return []

    results = []
    for l in lines:
        parts = l.split("|", 2)
        if len(parts) == 3:
            try:
                size_b = int(parts[0])
                mtime = int(parts[1])
                path = parts[2]
                filename = os.path.basename(path)
                ext = os.path.splitext(filename)[1].lower()

                # Categorize file
                if ext in ['.dmg', '.pkg', '.iso']:
                    file_type = "Installer / Disk Image"
                    color = "#00f0ff"
                elif ext in ['.mp4', '.mov', '.mkv', '.avi', '.m4v']:
                    file_type = "Video File"
                    color = "#ff007f"
                elif ext in ['.zip', '.tar', '.gz', '.tgz', '.bz2', '.7z']:
                    file_type = "Archive"
                    color = "#ffb800"
                elif ext in ['.app', '.ipa']:
                    file_type = "Application"
                    color = "#00ff9d"
                else:
                    file_type = "Large Data File"
                    color = "#a855f7"

                results.append({
                    "name": filename,
                    "path": path,
                    "size_bytes": size_b,
                    "size_formatted": format_bytes(size_b),
                    "file_type": file_type,
                    "color": color,
                    "modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                })
            except Exception:
                continue

    results.sort(key=lambda x: x["size_bytes"], reverse=True)
    return results[:max_results]

def get_cleanable_caches():
    home = os.path.expanduser("~")
    items = [
        {"name": "User Trash", "path": os.path.join(home, ".Trash"), "desc": "Deleted items pending permanent purge", "safe": True},
        {"name": "Xcode DerivedData", "path": os.path.join(home, "Library/Developer/Xcode/DerivedData"), "desc": "Temporary build intermediate files", "safe": True},
        {"name": "npm Cache", "path": os.path.join(home, ".npm"), "desc": "Node Package Manager global tarball cache", "safe": True},
        {"name": "Homebrew Cache", "path": os.path.join(home, "Library/Caches/Homebrew"), "desc": "Downloaded formulae bottle packages", "safe": True},
        {"name": "Pip Cache", "path": os.path.join(home, "Library/Caches/pip"), "desc": "Python wheel and source tarball cache", "safe": True},
        {"name": "Yarn Cache", "path": os.path.join(home, "Library/Caches/Yarn"), "desc": "Yarn dependency cache", "safe": True},
        {"name": "Gradle Cache", "path": os.path.join(home, ".gradle/caches"), "desc": "Java & Android build artifacts", "safe": True},
    ]

    total_cleanable_bytes = 0
    results = []

    for item in items:
        if os.path.exists(item["path"]):
            kb = _measure_dir_kb(item["path"], timeout=1.8)
            bytes_sz = kb * 1024
            if bytes_sz > 0:
                total_cleanable_bytes += bytes_sz
                results.append({
                    "name": item["name"],
                    "path": item["path"],
                    "bytes": bytes_sz,
                    "formatted": format_bytes(bytes_sz),
                    "desc": item["desc"],
                    "safe": item["safe"],
                })

    results.sort(key=lambda x: x["bytes"], reverse=True)
    return {
        "items": results,
        "total_bytes": total_cleanable_bytes,
        "total_formatted": format_bytes(total_cleanable_bytes),
    }
