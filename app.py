#!/usr/bin/env python3
"""
Pulse — Mac Intelligence Center
Ultimate Real-Time macOS System Monitor & Full Disk Storage Dashboard
"""

import sys
import os
import socket
import threading
import time
import webbrowser

# Check if running under Streamlit runtime
_is_streamlit = False
try:
    import streamlit as st
    if st.runtime.exists():
        _is_streamlit = True
except Exception:
    _is_streamlit = False

def find_available_port(start_port=8501, max_attempts=50):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

def run_fastapi_server(host="127.0.0.1", port=8501):
    import uvicorn
    from backend.server import app
    uvicorn.run(app, host=host, port=port, log_level="warning")

if _is_streamlit:
    # --- STREAMLIT WRAPPER MODE ---
    # When user runs: streamlit run app.py
    st.set_page_config(
        page_title="Pulse — Mac Intelligence",
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Clean up Streamlit default header/footer for maximum immersion
    st.markdown("""
        <style>
        #MainMenu, header, footer {visibility: hidden; height: 0;}
        .block-container {padding: 0 !important; max-width: 100% !important;}
        iframe {border: none !important; width: 100% !important; min-height: 98vh !important;}
        </style>
    """, unsafe_allow_html=True)

    # Start FastAPI backend in a background daemon thread if not already running
    if "backend_port" not in st.session_state:
        backend_port = find_available_port(8765)
        st.session_state["backend_port"] = backend_port

        server_thread = threading.Thread(
            target=run_fastapi_server,
            kwargs={"host": "127.0.0.1", "port": backend_port},
            daemon=True
        )
        server_thread.start()
        time.sleep(0.5)

    backend_url = f"http://127.0.0.1:{st.session_state['backend_port']}"
    
    # Embed the rich live dashboard full-screen
    import streamlit.components.v1 as components
    components.iframe(src=backend_url, height=1050, scrolling=True)

else:
    # --- STANDALONE WEB APPLICATION MODE (RECOMMENDED) ---
    # When user runs: python app.py
    port = find_available_port(8501)
    url = f"http://127.0.0.1:{port}"

    print("\033[1;36m" + "="*60 + "\033[0m")
    print("\033[1;32m  ◉ PULSE — MAC INTELLIGENCE DASHBOARD \033[0m")
    print("\033[1;35m  Full Disk Storage & Live System Telemetry Engine\033[0m")
    print("\033[1;36m" + "="*60 + "\033[0m")
    print(f"\n  🚀 Dashboard running at: \033[1;34m\033[4m{url}\033[0m")
    print("  ⚡ Real-Time WebSocket Telemetry: Active (1.0s stream)")
    print("  💾 APFS Deep Storage & Large File Hunter: Ready")
    print("  ⌨️  Press Ctrl+C to stop the monitor\n")

    # Automatically open the web browser after a brief delay
    def open_browser():
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        run_fastapi_server(host="127.0.0.1", port=port)
    except KeyboardInterrupt:
        print("\n\033[1;33mShutting down Pulse Mac Intelligence. Goodbye!\033[0m")
        sys.exit(0)
