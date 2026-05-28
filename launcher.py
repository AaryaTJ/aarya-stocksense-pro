"""
Aarya StockSense Pro — launcher.py
Starts Streamlit via its internal bootstrap API (works inside PyInstaller .exe),
then opens a native Windows window via pywebview.
"""

import os
import sys
import time
import socket
import threading

# ── CONFIG ────────────────────────────────────────────────────────────
APP_TITLE = "Aarya StockSense Pro"
PORT      = 8502
URL       = f"http://localhost:{PORT}"
WIN_W     = 1440
WIN_H     = 900
WIN_MIN_W = 1024
WIN_MIN_H = 680


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _wait_for_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _run_streamlit():
    """Run Streamlit using its internal bootstrap — works in frozen .exe."""
    base = _base_dir()
    app  = os.path.join(base, "app.py")

    if base not in sys.path:
        sys.path.insert(0, base)

    # Change CWD to workspace so Streamlit finds .streamlit/config.toml there.
    # Without this, CWD is the dist folder and config is ignored.
    os.chdir(base)

    # Newer Streamlit calls signal.signal() during startup which fails in threads.
    import signal as _sig
    _orig = _sig.signal
    def _safe_signal(signum, handler):
        if threading.current_thread() is threading.main_thread():
            return _orig(signum, handler)
    _sig.signal = _safe_signal

    # Write config.toml to workspace .streamlit dir (now our CWD).
    cfg_dir = os.path.join(base, ".streamlit")
    os.makedirs(cfg_dir, exist_ok=True)
    with open(os.path.join(cfg_dir, "config.toml"), "w") as _f:
        _f.write(f"""
[global]
developmentMode = false

[server]
port = {PORT}
address = "127.0.0.1"
headless = true

[browser]
gatherUsageStats = false

[theme]
base = "dark"
primaryColor = "#1D9E75"
backgroundColor = "#0F1B2D"
secondaryBackgroundColor = "#0A1628"
textColor = "#C9D6E3"
""")

    from streamlit.web import bootstrap
    bootstrap.run(app, False, [], {})


def main():
    # 1. Start Streamlit in background thread
    t = threading.Thread(target=_run_streamlit, daemon=True)
    t.start()

    # 2. Wait for server to be ready
    print(f"[Aarya] Starting on port {PORT} ...")
    ready = _wait_for_port(PORT, timeout=60)

    if not ready:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Aarya StockSense Pro",
                             "Server failed to start.\nPlease restart the app.")
        sys.exit(1)

    print("[Aarya] Server ready — opening window.")

    # 3. Open native pywebview window
    import webview
    webview.create_window(
        title       = APP_TITLE,
        url         = URL,
        width       = WIN_W,
        height      = WIN_H,
        min_size    = (WIN_MIN_W, WIN_MIN_H),
        resizable   = True,
        text_select = True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
