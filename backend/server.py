import os
import asyncio
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from .system_info import (
    get_static_hardware,
    get_os_info,
    get_battery_and_power,
    get_security_posture,
    get_developer_toolchain,
)
from .storage_analyzer import (
    get_apfs_overview,
    get_storage_breakdown,
    get_large_files,
    get_cleanable_caches,
)
from .metrics_collector import MetricsCollector

app = FastAPI(title="Pulse Mac Intelligence", version="2.0.0")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

collector = MetricsCollector(history_len=60)

class KillProcessRequest(BaseModel):
    pid: int

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Pulse Mac Intelligence: Frontend loading...</h1>")

@app.get("/api/summary")
async def api_summary():
    hw = get_static_hardware()
    os_info = get_os_info()
    vitals = collector.get_live_metrics()
    return {
        "hardware": hw,
        "os": os_info,
        "vitals": vitals,
    }

@app.get("/api/telemetry")
async def api_telemetry():
    return collector.get_live_metrics()

@app.get("/api/storage/overview")
async def api_storage_overview():
    return get_apfs_overview()

@app.get("/api/storage/breakdown")
async def api_storage_breakdown(refresh: bool = False):
    return get_storage_breakdown(force_refresh=refresh)

@app.get("/api/storage/large-files")
async def api_storage_large_files(min_size: int = Query(default=100, ge=10, le=5000)):
    return get_large_files(min_size_mb=min_size)

@app.get("/api/storage/caches")
async def api_storage_caches():
    return get_cleanable_caches()

@app.get("/api/processes")
async def api_processes(
    search: str = Query(default=""),
    sort: str = Query(default="cpu"),
    limit: int = Query(default=100, ge=1, le=1000)
):
    return collector.get_all_processes(search=search, sort_by=sort, limit=limit)

@app.post("/api/process/kill")
async def api_kill_process(req: KillProcessRequest):
    if req.pid <= 1:
        raise HTTPException(status_code=400, detail="Cannot terminate system root process.")
    try:
        p = psutil.Process(req.pid)
        p_name = p.name()
        p.terminate()
        return {"status": "success", "message": f"Sent SIGTERM to process {p_name} (PID: {req.pid})"}
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail="Process not found.")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail="Permission denied. Process belongs to root or another user.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/network/details")
async def api_network_details():
    interfaces = collector.get_network_interfaces()
    ports = collector.get_listening_ports()
    return {
        "interfaces": interfaces,
        "listening_ports": ports,
    }

@app.get("/api/battery/details")
async def api_battery_details():
    return get_battery_and_power()

@app.get("/api/system/details")
async def api_system_details():
    return {
        "security": get_security_posture(),
        "toolchain": get_developer_toolchain(),
        "hardware": get_static_hardware(),
        "os": get_os_info(),
    }

@app.websocket("/ws")
async def websocket_telemetry_stream(websocket: WebSocket):
    await websocket.accept()
    interval = 1.0
    is_paused = False
    try:
        while True:
            # Check for incoming client messages without blocking indefinitely
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.01)
                action = msg.get("action")
                if action == "pause":
                    is_paused = True
                elif action == "resume":
                    is_paused = False
                elif action == "set_interval":
                    interval = max(0.5, float(msg.get("interval", 1.0)))
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass

            if not is_paused:
                metrics = collector.get_live_metrics()
                await websocket.send_json(metrics)

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
