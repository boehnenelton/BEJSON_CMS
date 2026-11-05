#!/usr/bin/env python3
"""
Name:            advanced_launcher.py
Family:          BEJSON_CMS
Description:     Advanced interactive 57-column TUI service orchestrator for the
                 BEJSON CMS service family, enforcing the BEJSON Positional
                 Telemetry Discipline, atomic BEJSON 104a state persistence,
                 single-source telemetry, unified service table, and direct
                 compound command grammar.
Version:         3
Date created:    2026-08-07
Date modified:   2026-11-05
Author:          Elton Boehnen
Contact:         boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
RELATIONAL_ID:   d65d31c6-a0eb-4fed-b399-e5baff8c622b
"""

import os
import sys
import json
import time
import signal
import socket
import shutil
import tempfile
import threading
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime

VERSION = 3
AUTHOR = "Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton"
RELATIONAL_ID = "d65d31c6-a0eb-4fed-b399-e5baff8c622b"

# ─── Self-locating path resolution ──────────────────────────────────────────
def get_script_path() -> Path:
    return Path(__file__).resolve().parent


SCRIPT_PATH = get_script_path()
SCRIPT_NAME = Path(__file__).name
WEB_DIR = SCRIPT_PATH / "src" / "web"
LOG_DIR = SCRIPT_PATH / "storage" / "tmp" / "logs"
REGISTRY_PATH = SCRIPT_PATH / "storage" / "tmp" / "launcher_registry.104a.bejson"
LEGACY_REGISTRY_PATH = SCRIPT_PATH / "storage" / "tmp" / "launcher_registry.json"
CONFIG_PATH = SCRIPT_PATH / "config.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─── Style & Palette (#DE2626 BECSS Terminal Accent) ────────────────────────
RED = "\033[38;2;222;38;38m"       # #DE2626 -- headers, fields, option selectors
WHITE = "\033[97m"                 # body text / values
DIM = "\033[2m"                    # secondary / log text
GREEN = "\033[38;2;90;200;120m"    # UP status / success
YELLOW = "\033[38;2;230;190;60m"   # warnings / probes
RESET = "\033[0m"
BOLD = "\033[1m"

DIV_MAIN = "=" * 57
DIV_SUB  = "-" * 57

LIB_DIR = SCRIPT_PATH / "src" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.append(str(LIB_DIR))
import lib_bejson_CMS_cms_ports as CMSPorts  # noqa: E402

SERVICES = {
    "1": {"key": "admin", "label": "Admin (Dashboard)", "file": "BEJSON_CMS_Admin.py",
          "port_env": "CMS_ADMIN_PORT", "setting_name": "admin_port"},
    "2": {"key": "editor", "label": "Page Editor (V1)", "file": "BEJSON_CMS_PageEditor.py",
          "port_env": "CMS_PAGEEDITOR_PORT", "setting_name": "pageeditor_port"},
    "3": {"key": "editorv2", "label": "Page Editor V2", "file": "BEJSON_CMS_PageEditorV2.py",
          "port_env": "CMS_PAGEEDITORV2_PORT", "setting_name": "pageeditorv2_port"},
    "4": {"key": "publisher", "label": "Static Site Publisher", "file": "BEJSON_CMS_Publisher.py",
          "port_env": "CMS_PUBLISHER_PORT", "setting_name": "publisher_port"},
    "5": {"key": "profiles", "label": "Persona Hub (Profiles)", "file": "BEJSON_CMS_ProfileManager.py",
          "port_env": "CMS_PROFILES_PORT", "setting_name": "profiles_port"},
}

# State: key -> {"pid": int, "port": int, "log_file": str, "started": str, "port_bumped": bool, "proc": Popen}
_running = {}
_lock = threading.Lock()
_print_lock = threading.Lock()


# ─── Console Clear & Terminal Formatting ────────────────────────────────────
def clear_screen():
    """Clear terminal and home cursor (\033[2J\033[H) per 57-column TUI discipline."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def typewrite(text: str, color: str = WHITE, delay: float = 0.008, end: str = "\n"):
    """Used strictly on initial cold-boot banner, never in the redraw loop."""
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


# ─── Atomic BEJSON 104a State Persistence ──────────────────────────────────
def _atomic_bejson_write(target_path: Path, doc: dict) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(dir=str(target_path.parent), prefix=".tmp_launcher_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
            json.dump(doc, file_handle, indent=2)
        os.replace(tmp_path_str, target_path)
    except OSError:
        if os.path.exists(tmp_path_str):
            os.remove(tmp_path_str)
        raise


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as file_handle:
                doc = json.load(file_handle)
            fields = doc.get("Fields", [])
            cache = {str(f.get("name", "")).strip(): i for i, f in enumerate(fields) if isinstance(f, dict)}
            key_idx = cache.get("service_key")
            pid_idx = cache.get("pid")
            port_idx = cache.get("port")
            bump_idx = cache.get("port_bumped")
            start_idx = cache.get("started_iso")
            log_idx = cache.get("log_file")

            loaded = {}
            for row in doc.get("Values", []):
                if isinstance(row, list) and len(row) > max(key_idx or 0, pid_idx or 0):
                    svc_key = str(row[key_idx])
                    loaded[svc_key] = {
                        "pid": int(row[pid_idx]),
                        "port": int(row[port_idx]) if port_idx is not None else 5000,
                        "port_bumped": bool(row[bump_idx]) if bump_idx is not None else False,
                        "started": str(row[start_idx]) if start_idx is not None else datetime.now().isoformat(),
                        "log_file": str(row[log_idx]) if log_idx is not None else "",
                    }
            return loaded
        except Exception:
            pass

    # Backward compatibility with legacy json
    if LEGACY_REGISTRY_PATH.exists():
        try:
            with open(LEGACY_REGISTRY_PATH, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def _save_registry() -> None:
    with _lock:
        rows = [
            [
                k,
                int(v["pid"]),
                int(v["port"]),
                bool(v.get("port_bumped", False)),
                str(v["started"]),
                str(v["log_file"]),
            ]
            for k, v in _running.items()
        ]

    doc = {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["CMS_Service_Registry"],
        "Fields": [
            {"name": "service_key", "type": "string"},
            {"name": "pid", "type": "integer"},
            {"name": "port", "type": "integer"},
            {"name": "port_bumped", "type": "boolean"},
            {"name": "started_iso", "type": "string"},
            {"name": "log_file", "type": "string"},
        ],
        "Values": rows,
    }
    try:
        _atomic_bejson_write(REGISTRY_PATH, doc)
    except Exception as exc:
        line(f" [Error] Registry write failed: {exc}", RED)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _reconcile_registry_on_start() -> None:
    saved = _load_registry()
    for key, info in saved.items():
        if _pid_alive(info["pid"]):
            _running[key] = {**info, "proc": None}
    _save_registry()


# ─── Watcher Thread ─────────────────────────────────────────────────────────
def _watch_service(key: str, label: str, proc: subprocess.Popen, log_file: Path):
    exit_code = proc.wait()
    with _lock:
        was_tracked = key in _running and _running[key].get("pid") == proc.pid
        if was_tracked:
            del _running[key]
    _save_registry()


# ─── Service Lifecycle Operations ───────────────────────────────────────────
def launch_service(entry: dict) -> str:
    key, label, filename = entry["key"], entry["label"], entry["file"]

    with _lock:
        already = _running.get(key)
    if already and _pid_alive(already["pid"]):
        return f"#{entry['id']} {label} already UP (PID {already['pid']}, :{already['port']})"

    script_file = WEB_DIR / filename
    if not script_file.exists():
        return f"[Error] {filename} missing in {WEB_DIR}"

    port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
    env = os.environ.copy()
    port_bumped = False

    # Auto-resolve Admin/Publisher collision
    if entry["port_env"]:
        other_key = "publisher" if key == "admin" else ("admin" if key == "publisher" else None)
        with _lock:
            other = _running.get(other_key) if other_key else None
        if other and other.get("port") == port:
            port = port + 10
            env[entry["port_env"]] = str(port)
            port_bumped = True

    log_file = LOG_DIR / f"{filename}.log"
    with open(log_file, "ab") as lf:
        lf.write(f"\n=== launched {datetime.now().isoformat()} ===\n".encode())
        proc = subprocess.Popen(
            [sys.executable, str(script_file)],
            cwd=str(WEB_DIR),
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    with _lock:
        _running[key] = {
            "pid": proc.pid,
            "port": port,
            "port_bumped": port_bumped,
            "log_file": str(log_file),
            "started": datetime.now().isoformat(),
            "proc": proc,
        }
    _save_registry()

    watcher = threading.Thread(target=_watch_service, args=(key, label, proc, log_file), daemon=True)
    watcher.start()

    bump_note = f" (bumped -> {port})" if port_bumped else ""
    return f"#{entry['id']} {label} started: PID {proc.pid}, :{port}{bump_note}"


def force_close(key: str, label: str) -> str:
    with _lock:
        info = _running.get(key)
    if not info or not _pid_alive(info["pid"]):
        with _lock:
            _running.pop(key, None)
        _save_registry()
        return f"{label} is not running."

    pid = info["pid"]
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    with _lock:
        _running.pop(key, None)
    _save_registry()
    return f"{label} stopped (PID {pid})."


def restart_service(entry: dict) -> str:
    close_msg = force_close(entry["key"], entry["label"])
    time.sleep(0.3)
    start_msg = launch_service(entry)
    return f"{entry['label']} restarted: {start_msg}"


def force_close_all() -> str:
    with _lock:
        keys = list(_running.keys())
    if not keys:
        return "No running services to stop."
    for key in keys:
        entry = next((e for e in SERVICES.values() if e["key"] == key), None)
        if entry:
            force_close(key, entry["label"])
    return f"Stopped {len(keys)} service(s)."


def start_all_services() -> str:
    started_count = 0
    for entry in SERVICES.values():
        res = launch_service(entry)
        if "started" in res:
            started_count += 1
    return f"Start-all executed: {started_count} newly launched."


# ─── Port Probe & Browser Opener ────────────────────────────────────────────
def probe_port(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, socket.timeout):
        return False


def run_port_probe() -> None:
    line(f"\n{DIV_MAIN}", RED)
    line(" HTTP TCP PORT READINESS PROBE (127.0.0.1)", RED)
    line(DIV_SUB, DIM)
    line(f" {'ID':<3} {'PORT':<6} {'STATUS':<10} {'SOCKET_STATE':<14} {'SERVICE':<20}", BOLD)
    for num, entry in SERVICES.items():
        with _lock:
            info = _running.get(entry["key"])
        cfg_port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
        active_port = info["port"] if (info and _pid_alive(info["pid"])) else cfg_port
        is_up = info and _pid_alive(info["pid"])

        is_listening = probe_port(active_port)
        if is_listening:
            sock_state = f"{GREEN}LISTENING{RESET}"
        elif is_up:
            sock_state = f"{YELLOW}BOOTING/HANG{RESET}"
        else:
            sock_state = f"{DIM}CLOSED{RESET}"

        status_str = f"{GREEN}UP{RESET}" if is_up else f"{DIM}STOP{RESET}"
        print(f" {int(num):02d}  {active_port:<6} {status_str:<19} {sock_state:<23} {entry['label'][:18]}")
    line(DIV_MAIN, RED)


def open_service_url(entry: dict) -> str:
    with _lock:
        info = _running.get(entry["key"])
    if not (info and _pid_alive(info["pid"])):
        return f"{entry['label']} is not running."
    url = f"http://127.0.0.1:{info['port']}"
    if shutil.which("termux-open-url"):
        subprocess.run(["termux-open-url", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)
    return f"Opened {url} in browser."


def tail_log(entry: dict, n: int = 20) -> None:
    log_file = LOG_DIR / f"{entry['file']}.log"
    line(f"\n{DIV_MAIN}", RED)
    line(f" LAST {n} LINES: {entry['label']}", RED)
    line(DIV_SUB, DIM)
    if not log_file.exists():
        line(" No log file generated yet.", DIM)
    else:
        lines = log_file.read_text(errors="replace").splitlines()[-n:]
        for log_line in lines:
            line(f" {log_line[:55]}", DIM)
    line(DIV_MAIN, RED)


# ─── Render 57-Column Unified TUI Menu ──────────────────────────────────────
# Populate IDs for fast lookup
for k_num, s_val in SERVICES.items():
    s_val["id"] = int(k_num)


def render_menu(last_msg: str = "Ready."):
    clear_screen()
    with _lock:
        snapshot = dict(_running)

    up_count = sum(1 for v in snapshot.values() if _pid_alive(v["pid"]))

    # Main Header Strip (57 columns)
    line(DIV_MAIN, RED)
    header_left = "BEJSON CMS LAUNCHER [v2]"
    header_right = "~/..launcher.104a.bejson"
    print(f" {RED}{header_left:<26}{RESET} {DIM}{header_right:>28}{RESET}")
    line(DIV_SUB, DIM)

    # Band 1: Telemetry Strip (Fields in RED -> Values in WHITE)
    print(f" {RED}{'UP_SVC':<7} {'HOST_IP':<13} {'CFG_FILE':<12} {'LOG_DIR':<15} {'MODE':<4}{RESET}")
    print(f" {f'{up_count}/{len(SERVICES)}':<7} {'127.0.0.1':<13} {'config.json':<12} {'storage/..logs':<15} {'BG':<4}")
    line(DIV_SUB, DIM)

    # Band 2: Unified Positional Service Table (57 columns)
    print(f" {RED}{'ID':<3} {'STATE':<7} {'PID':<6} {'PORT':<6} {'UPTIME':<7} {'SERVICE_NAME':<22}{RESET}")
    for num, entry in SERVICES.items():
        info = snapshot.get(entry["key"])
        cfg_port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
        if info and _pid_alive(info["pid"]):
            uptime = int((datetime.now() - datetime.fromisoformat(info["started"])).total_seconds())
            mins, secs = divmod(uptime, 60)
            state_str = "UP*" if info.get("port_bumped") or info["port"] != cfg_port else "UP"
            state_col = f"{GREEN}{state_str:<7}{RESET}"
            pid_str = f"{info['pid']:<6}"
            port_str = f"{info['port']:<6}"
            up_str = f"{mins:02d}:{secs:02d} "
        else:
            state_col = f"{DIM}{'STOP':<7}{RESET}"
            pid_str = f"{DIM}{'--':<6}{RESET}"
            port_str = f"{cfg_port:<6}"
            up_str = f"{DIM}{'--:--':<7}{RESET}"

        short_label = entry["label"][:22]
        print(f" {int(num):02d}  {state_col} {pid_str} {port_str} {up_str} {short_label:<22}")

    line(DIV_MAIN, RED)

    # Band 3: Decoupled 3-Column Action Grid (<= 57 columns)
    def fmt_col(key_str: str, desc: str, col_w: int) -> str:
        tag = f"[{RED}{key_str}{RESET}]"
        rem = col_w - (len(key_str) + 3)
        return f"{tag} {desc:<{rem}}"

    row1 = f" {fmt_col('1-5', 'Start/Toggle', 19)}{fmt_col('R', 'Restart Svc', 18)}{fmt_col('S', 'Start All', 18)}"
    row2 = f" {fmt_col('K', 'Kill One Svc', 19)}{fmt_col('Z', 'Kill All', 18)}{fmt_col('L', 'Tail Svc Log', 18)}"
    row3 = f" {fmt_col('P', 'Port Probe', 19)}{fmt_col('O', 'Open URL', 18)}{fmt_col('C', 'Reload Config', 18)}"
    row4 = f" {fmt_col('E', 'Export 104a', 19)}{fmt_col('Q', 'Quit (Keep)', 18)}{fmt_col('X', 'Quit & Kill', 18)}"

    print(row1)
    print(row2)
    print(row3)
    print(row4)

    line(DIV_MAIN, RED)
    # Band 4: 1-Line Status Ticker
    ticker_text = last_msg[:48]
    print(f" {RED}[LAST]{RESET} {ticker_text}")


# ─── Command Line Argument Parsing ──────────────────────────────────────────
def parse_cli_arguments():
    import argparse
    command_line_argument_parser = argparse.ArgumentParser(
        description="BEJSON CMS Advanced Interactive 57-column TUI Service Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    command_line_argument_parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"advanced_launcher.py v{VERSION} (BEJSON_CMS)",
    )
    command_line_argument_parser.add_argument(
        "--about",
        action="store_true",
        help="Display author and architecture metadata and exit",
    )
    command_line_argument_parser.add_argument(
        "--status",
        action="store_true",
        help="Display non-interactive service status summary and exit",
    )
    command_line_argument_parser.add_argument(
        "--probe",
        action="store_true",
        help="Run port probe non-interactively and exit",
    )
    return command_line_argument_parser.parse_args()


# ─── Main Interactive Loop ──────────────────────────────────────────────────
def main():
    parsed_cli_arguments = parse_cli_arguments()

    if parsed_cli_arguments.about:
        print(f"BEJSON CMS Advanced Launcher v{VERSION}")
        print(f"Author: {AUTHOR}")
        print(f"Relational ID: {RELATIONAL_ID}")
        print(f"Registry: {REGISTRY_PATH}")
        sys.exit(0)

    if parsed_cli_arguments.probe:
        _reconcile_registry_on_start()
        run_port_probe()
        sys.exit(0)

    if parsed_cli_arguments.status:
        _reconcile_registry_on_start()
        print(f"BEJSON CMS Service Status (Launcher v{VERSION}):")
        for service_numeric_key, service_definition_entry in sorted(SERVICES.items()):
            service_identifier_key = service_definition_entry["key"]
            configured_service_port = CMSPorts.get_port(
                str(CONFIG_PATH),
                service_definition_entry["setting_name"],
                service_definition_entry["port_env"],
            )
            active_service_info = _running.get(service_identifier_key)
            if active_service_info and _pid_alive(active_service_info["pid"]):
                print(f"  [{service_numeric_key}] {service_definition_entry['label']:<24} RUNNING  PID: {active_service_info['pid']:<6} Port: {active_service_info['port']}")
            else:
                print(f"  [{service_numeric_key}] {service_definition_entry['label']:<24} STOPPED  Port: {configured_service_port}")
        sys.exit(0)

    clear_screen()
    typewrite(f"== BEJSON CMS ADVANCED LAUNCHER ORCHESTRATOR [v{VERSION}] ==", color=RED, delay=0.005)
    _reconcile_registry_on_start()
    last_status = "Launcher initialized. System ready."

    while True:
        render_menu(last_msg=last_status)
        try:
            raw_input = input(f" {RED}Action > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not raw_input:
            last_status = "No command entered."
            continue

        cmd = raw_input.lower()

        # 1-5: Start / Toggle
        if cmd in SERVICES:
            last_status = launch_service(SERVICES[cmd])

        # R1-R5 or bare R
        elif cmd.startswith("r") and len(cmd) > 1 and cmd[1:] in SERVICES:
            last_status = restart_service(SERVICES[cmd[1:]])
        elif cmd == "r":
            sub = input(f" {RED}Restart which service (1-5)? {RESET}").strip()
            if sub in SERVICES:
                last_status = restart_service(SERVICES[sub])
            else:
                last_status = "Invalid service ID for restart."

        # K1-K5 or bare K
        elif cmd.startswith("k") and len(cmd) > 1 and cmd[1:] in SERVICES:
            entry = SERVICES[cmd[1:]]
            last_status = force_close(entry["key"], entry["label"])
        elif cmd == "k":
            sub = input(f" {RED}Kill which service (1-5)? {RESET}").strip()
            if sub in SERVICES:
                entry = SERVICES[sub]
                last_status = force_close(entry["key"], entry["label"])
            else:
                last_status = "Invalid service ID for termination."

        # L1-L5 or bare L
        elif cmd.startswith("l") and len(cmd) > 1 and cmd[1:] in SERVICES:
            tail_log(SERVICES[cmd[1:]])
            input(f"\n {DIM}Press [Enter] to return to menu...{RESET}")
            last_status = f"Tailed log for #{cmd[1:]}."
        elif cmd == "l":
            sub = input(f" {RED}Tail log for which service (1-5)? {RESET}").strip()
            if sub in SERVICES:
                tail_log(SERVICES[sub])
                input(f"\n {DIM}Press [Enter] to return to menu...{RESET}")
                last_status = f"Tailed log for #{sub}."
            else:
                last_status = "Invalid service ID for log tailing."

        # O1-O5 or bare O
        elif cmd.startswith("o") and len(cmd) > 1 and cmd[1:] in SERVICES:
            last_status = open_service_url(SERVICES[cmd[1:]])
        elif cmd == "o":
            sub = input(f" {RED}Open URL for which service (1-5)? {RESET}").strip()
            if sub in SERVICES:
                last_status = open_service_url(SERVICES[sub])
            else:
                last_status = "Invalid service ID."

        # S: Start All
        elif cmd == "s":
            last_status = start_all_services()

        # Z: Kill All
        elif cmd == "z":
            last_status = force_close_all()

        # P: Port Probe
        elif cmd == "p":
            run_port_probe()
            input(f"\n {DIM}Press [Enter] to return to menu...{RESET}")
            last_status = "Port probe completed."

        # C: Reload Config
        elif cmd == "c":
            last_status = "Config reloaded; ports refreshed."

        # E: Export 104a Registry inspection
        elif cmd == "e":
            line(f"\n{DIV_MAIN}", RED)
            line(" BEJSON 104a LAUNCHER REGISTRY (storage/tmp/)", RED)
            line(DIV_SUB, DIM)
            if REGISTRY_PATH.exists():
                print(f"{DIM}{REGISTRY_PATH.read_text()}{RESET}")
            else:
                line(" Registry file not yet created.", DIM)
            line(DIV_MAIN, RED)
            input(f"\n {DIM}Press [Enter] to return to menu...{RESET}")
            last_status = "Exported registry inspected."

        # Q: Quit and Keep Running
        elif cmd == "q":
            clear_screen()
            line("[System] Leaving active services running in background. Goodbye.", RED)
            break

        # X: Quit and Stop Everything
        elif cmd == "x":
            clear_screen()
            force_close_all()
            line("[System] All services terminated cleanly. Goodbye.", RED)
            break

        else:
            last_status = f"Unknown command: '{raw_input[:15]}'"


if __name__ == "__main__":
    main()
