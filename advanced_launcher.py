"""
Name:            advanced_launcher.py
Family:          BEJSON_CMS
Description:     Advanced interactive launcher menu for the BEJSON CMS service
                 family. Replaces cms_launcher.sh's "kill-everything-then-
                 block" model with persistent, backgrounded subprocesses:
                 each service is started via subprocess.Popen, watched by its
                 own thread, and tracked by PID in a small on-disk registry
                 so it can be force-closed individually later -- including
                 from a different launcher session. Explicitly supports
                 running Admin and Publisher at the same time (they default
                 to the same port, 5001 -- this launcher assigns Publisher an
                 alternate port automatically when Admin is already up, via
                 the CMS_PUBLISHER_PORT env override added alongside this
                 file). Styled to the #DE2626 BECSS accent, with a typewriter
                 effect on headers and status transitions.
Version:         1
Date created:    2026-08-07
Author:          Elton Boehnen
Contact:         boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
RELATIONAL_ID:   2f6a9e2e-1b6c-4b3e-8b0e-6a7b6b4f0a1c
"""

import os
import sys
import json
import time
import signal
import threading
import subprocess
from pathlib import Path
from datetime import datetime

VERSION = 1


# ─── Self-locating path resolution (per System Development Policy §3.5/§8) ──
def get_script_path() -> Path:
    return Path(__file__).resolve().parent


SCRIPT_PATH = get_script_path()
SCRIPT_NAME = Path(__file__).name
WEB_DIR = SCRIPT_PATH / "src" / "web"
LOG_DIR = SCRIPT_PATH / "storage" / "tmp" / "logs"
REGISTRY_PATH = SCRIPT_PATH / "storage" / "tmp" / "launcher_registry.json"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─── #DE2626 BECSS theme, terminal-safe: white/black base, red for accents
# only -- never a solid red block, never black text on red (Style Policy §10).
RED = "\033[38;2;222;38;38m"       # #DE2626 -- headers, active status, prompts
WHITE = "\033[97m"                 # body text
DIM = "\033[2m"                    # secondary/log text
GREEN = "\033[38;2;90;200;120m"    # running / success
YELLOW = "\033[38;2;230;190;60m"   # warnings
RESET = "\033[0m"
BOLD = "\033[1m"

LIB_DIR = SCRIPT_PATH / "src" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.append(str(LIB_DIR))
import lib_bejson_CMS_cms_ports as CMSPorts  # noqa: E402

CONFIG_PATH = SCRIPT_PATH / "config.json"

SERVICES = {
    "1": {"key": "admin", "label": "Admin (Dashboard)", "file": "BEJSON_CMS_Admin.py",
          "port_env": "CMS_ADMIN_PORT", "setting_name": "admin_port"},
    "2": {"key": "editor", "label": "Page Editor (V1)", "file": "BEJSON_CMS_PageEditor.py",
          "port_env": "CMS_PAGEEDITOR_PORT", "setting_name": "pageeditor_port"},
    "3": {"key": "editorv2", "label": "Page Editor V2", "file": "BEJSON_CMS_PageEditorV2.py",
          "port_env": "CMS_PAGEEDITORV2_PORT", "setting_name": "pageeditorv2_port"},
    "4": {"key": "publisher", "label": "Static Site Publisher", "file": "BEJSON_CMS_Publisher.py",
          "port_env": "CMS_PUBLISHER_PORT", "setting_name": "publisher_port"},
    "5": {"key": "profiles", "label": "Persona Hub (Profile Manager)", "file": "BEJSON_CMS_ProfileManager.py",
          "port_env": "CMS_PROFILES_PORT", "setting_name": "profiles_port"},
}
# Ports are resolved lazily per-launch (see launch_service()) via
# CMSPorts.get_port(), which reads config.json and honors an already-set env
# var override -- not baked into SERVICES as a static default anymore.

# key -> {"pid": int, "port": int, "log_file": str, "started": iso-ts, "proc": Popen}
_running = {}
_lock = threading.Lock()
_print_lock = threading.Lock()  # keeps watcher-thread output from interleaving mid-typewrite


# ─── Typewriter effect ───────────────────────────────────────────────────────
def typewrite(text: str, color: str = WHITE, delay: float = 0.012, end: str = "\n"):
    """Prints text one character at a time. Used for headers/banners and
    status transitions only -- never for log output, which prints instantly.
    Holds _print_lock for the whole call so a watcher thread's async status
    report can't interleave mid-character with the main thread's output."""
    with _print_lock:
        sys.stdout.write(color)
        for ch in text:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(delay)
        sys.stdout.write(RESET + end)
        sys.stdout.flush()


def line(text: str = "", color: str = WHITE):
    with _print_lock:
        print(f"{color}{text}{RESET}")


# ─── Registry persistence (so PIDs survive a launcher restart) ──────────────
def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_registry():
    with _lock:
        serializable = {
            k: {"pid": v["pid"], "port": v["port"], "log_file": v["log_file"], "started": v["started"]}
            for k, v in _running.items()
        }
    REGISTRY_PATH.write_text(json.dumps(serializable, indent=2))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _reconcile_registry_on_start():
    """On launcher startup, adopt any still-alive PIDs from a previous
    session (e.g. this menu was closed but a service kept running in the
    background) so they show correctly and can still be force-closed."""
    saved = _load_registry()
    for key, info in saved.items():
        if _pid_alive(info["pid"]):
            _running[key] = {**info, "proc": None}


# ─── Watcher thread (the "multi-threaded launching" piece) ─────────────────
def _watch_service(key: str, label: str, proc: subprocess.Popen, log_file: Path):
    """Runs on its own thread per service. Blocks on proc.wait() so the main
    menu thread is never blocked, then reports whether the exit was clean."""
    exit_code = proc.wait()
    with _lock:
        was_tracked = key in _running and _running[key]["pid"] == proc.pid
        if was_tracked:
            del _running[key]
    _save_registry()
    if was_tracked:
        if exit_code == 0:
            typewrite(f"[System] {label} stopped normally.", color=DIM, delay=0.004)
        else:
            typewrite(f"[CRITICAL] {label} exited with code {exit_code} -- see {log_file}",
                       color=YELLOW, delay=0.004)


def launch_service(entry: dict):
    key, label, filename = entry["key"], entry["label"], entry["file"]

    with _lock:
        already = _running.get(key)
    if already and _pid_alive(already["pid"]):
        line(f" {label} is already running (pid {already['pid']}, port {already['port']}).", YELLOW)
        return

    script_file = WEB_DIR / filename
    if not script_file.exists():
        line(f" [Error] {filename} not found under {WEB_DIR}", RED)
        return

    # Resolve this service's port the same way the service itself will:
    # env var (if already set) > config.json > hardcoded default.
    port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
    env = os.environ.copy()

    # Auto-resolve the Admin/Publisher port collision: if the other one of
    # the pair is already running on that same port, bump this one and pin
    # it via env var so the child process picks up the bumped value too.
    if entry["port_env"]:
        other_key = "publisher" if key == "admin" else ("admin" if key == "publisher" else None)
        with _lock:
            other = _running.get(other_key) if other_key else None
        if other and other.get("port") == port:
            port = port + 10  # 5001 -> 5011, stays clear of the other three services' fixed ports
            env[entry["port_env"]] = str(port)
            line(f" [System] Port {port - 10} is in use by {other_key} -- "
                 f"starting {label} on {port} instead.", YELLOW)

    log_file = LOG_DIR / f"{filename}.log"
    typewrite(f"[System] Starting {label} (port {port})...", color=RED, delay=0.006)

    with open(log_file, "ab") as lf:
        lf.write(f"\n=== launched {datetime.now().isoformat()} ===\n".encode())
        proc = subprocess.Popen(
            [sys.executable, str(script_file)],
            cwd=str(WEB_DIR),
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # own process group -- force-close won't take the launcher down with it
        )

    with _lock:
        _running[key] = {
            "pid": proc.pid, "port": port, "log_file": str(log_file),
            "started": datetime.now().isoformat(), "proc": proc,
        }
    _save_registry()

    watcher = threading.Thread(target=_watch_service, args=(key, label, proc, log_file), daemon=True)
    watcher.start()

    line(f" [System] {label} is up -- pid {proc.pid}, logging to {log_file}", GREEN)


def force_close(key: str, label: str):
    with _lock:
        info = _running.get(key)
    if not info or not _pid_alive(info["pid"]):
        line(f" {label} is not currently running.", DIM)
        with _lock:
            _running.pop(key, None)
        _save_registry()
        return

    pid = info["pid"]
    typewrite(f"[System] Force-closing {label} (pid {pid})...", color=RED, delay=0.006)
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    for _ in range(20):  # up to ~2s grace period
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _pid_alive(pid):
        line(" [System] Did not exit cleanly -- sending SIGKILL.", YELLOW)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    with _lock:
        _running.pop(key, None)
    _save_registry()
    line(f" [System] {label} stopped.", GREEN)


def force_close_all():
    with _lock:
        keys = list(_running.keys())
    for key in keys:
        entry = next(e for e in SERVICES.values() if e["key"] == key)
        force_close(key, entry["label"])


def tail_log(entry: dict, n: int = 20):
    log_file = LOG_DIR / f"{entry['file']}.log"
    if not log_file.exists():
        line(f" No log yet for {entry['label']}.", DIM)
        return
    lines = log_file.read_text(errors="replace").splitlines()[-n:]
    line(f"\n --- last {len(lines)} lines: {entry['label']} ---", RED)
    for l in lines:
        print(f"{DIM}{l}{RESET}")
    line(" --- end of log ---\n", RED)


# ─── Menu ────────────────────────────────────────────────────────────────────
def status_block():
    with _lock:
        snapshot = dict(_running)
    if not snapshot:
        line(" No services currently running.", DIM)
        return
    for entry in SERVICES.values():
        info = snapshot.get(entry["key"])
        if info and _pid_alive(info["pid"]):
            uptime = datetime.now() - datetime.fromisoformat(info["started"])
            mins, secs = divmod(int(uptime.total_seconds()), 60)
            line(f"  [{GREEN}RUNNING{RESET}{WHITE}] {entry['label']:<28} pid {info['pid']:<7} "
                 f"port {info['port']:<5} up {mins:02d}:{secs:02d}", WHITE)


def print_menu():
    os.system("clear" if os.name != "nt" else "cls")
    line("=" * 68, RED)
    typewrite(" BEJSON ECOSYSTEM: ADVANCED CMS LAUNCHER", color=RED, delay=0.008)
    line("=" * 68, RED)
    line(" Persistent, multi-threaded, PID-tracked. Services keep running", DIM)
    line(" after you pick another menu option -- nothing is auto-killed.", DIM)
    print()
    status_block()
    print()
    for num, entry in SERVICES.items():
        configured_port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
        line(f"  {num}) Launch {entry['label']:<28} [:{configured_port}]", WHITE)
    line("  (Ports come from config.json — edit it to change any service's default.)", DIM)
    line("", WHITE)
    line("  l) View recent log for a service", WHITE)
    line("  k) Force-close one running service", WHITE)
    line("  a) Force-close ALL services", WHITE)
    line("  q) Quit menu (services keep running in background)", WHITE)
    line("  x) Quit menu AND stop everything", WHITE)
    line("=" * 68, RED)


def _pick_running_service() -> dict | None:
    with _lock:
        keys = [k for k, v in _running.items() if _pid_alive(v["pid"])]
    if not keys:
        line(" Nothing is running.", DIM)
        return None
    entries = [e for e in SERVICES.values() if e["key"] in keys]
    for i, e in enumerate(entries, 1):
        line(f"  {i}) {e['label']}", WHITE)
    choice = input(f"{RED} Select: {RESET}").strip()
    try:
        return entries[int(choice) - 1]
    except (ValueError, IndexError):
        line(" Invalid selection.", YELLOW)
        return None


def main():
    _reconcile_registry_on_start()
    while True:
        print_menu()
        choice = input(f"{RED} Select an option: {RESET}").strip().lower()

        if choice in SERVICES:
            launch_service(SERVICES[choice])
            input(f"{DIM} Press [Enter] to continue...{RESET}")
        elif choice == "l":
            entry = _pick_running_service()
            if entry:
                tail_log(entry)
                input(f"{DIM} Press [Enter] to continue...{RESET}")
        elif choice == "k":
            entry = _pick_running_service()
            if entry:
                force_close(entry["key"], entry["label"])
                input(f"{DIM} Press [Enter] to continue...{RESET}")
        elif choice == "a":
            force_close_all()
            input(f"{DIM} Press [Enter] to continue...{RESET}")
        elif choice == "q":
            typewrite("[System] Leaving services running in the background. Bye.", color=RED, delay=0.006)
            break
        elif choice == "x":
            force_close_all()
            typewrite("[System] All services stopped. Bye.", color=RED, delay=0.006)
            break
        else:
            line(" Invalid selection.", YELLOW)
            time.sleep(1)


if __name__ == "__main__":
    main()
