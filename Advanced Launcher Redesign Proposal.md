# Redesign Proposal: `advanced_launcher.py` (BEJSON_CMS Service Orchestrator)

**Target Module:** `advanced_launcher.py` (`BEJSON_CMS` Family)  
**Proposed Version:** `2` (Solid Integer Increment per Dual-Version Standard)  
**Design Standard:** BEJSON Positional Telemetry Discipline (57-Column Termux Standard) & `#DE2626` BECSS Terminal Accent Policy

## 1. Executive Audit of Current `advanced_launcher.py` (v1)

While `advanced_launcher.py` v1 successfully replaces blocking shell execution with `subprocess.Popen` process groups, daemon watcher threads, and Admin/Publisher port collision auto-bumping (`5001 -> 5011`), its terminal interface and state persistence exhibit six structural bottlenecks:

| Defect Category | Current Behavior in v1 | Operational Impact |
| :--- | :--- | :--- |
| **1. Viewport Overflow** | Dividers use `"=" * 68` and running status rows reach **72 columns** (`[RUNNING] Persona Hub (Profile Manager) pid 14201 port 5004 up 00:12`). | Wraps across 2 lines on 57-column mobile/Termux portrait screens, breaking visual alignment. |
| **2. Split Service Duplication** | Prints services once in `status_block()` and prints all 5 services a second time in the launch menu (`1) Launch ...`). | Doubles vertical screen height and forces the operator's eyes to cross-reference two separate lists. |
| **3. JSON-Style Inline Key Repetition** | Repeats `pid `, `port `, and `up ` inline on every running service row, and `[RUNNING]` on every line. | Wastes 26 horizontal characters per row on static labels instead of using positional columns. |
| **4. Dynamic Sub-Menu Re-Indexing** | Pressing `k` or `l` calls `_pick_running_service()`, which re-numbers running services `1..N` dynamically. | If only Service `#4` (Publisher) is running, it becomes `#1` in the kill menu—creating muscle-memory errors that kill the wrong process. |
| **5. Static Prose & Typewriter Lag** | Re-prints 3 lines of tutorial prose (`Persistent, multi-threaded...` and `Ports come from config.json...`) and runs `typewrite()` inside the main redraw loop. | Adds ~320ms blocking delay on every screen refresh and wastes 5 vertical lines on static text. |
| **6. Non-BEJSON State Persistence** | Saves process state to `launcher_registry.json` as standard keyed JSON via non-atomic `write_text()`. | Violates `BEJSON_CMS` family persistence standards and risks partial file corruption if interrupted mid-write. |

## 2. Visual Redesign: Legacy v1 vs. Proposed v2 (57-Column BEJSON TUI)

### Current v1 Output (68–72 Columns, Duplicated Lists, Inline Labels)

```text
====================================================================
 BEJSON ECOSYSTEM: ADVANCED CMS LAUNCHER
====================================================================
 Persistent, multi-threaded, PID-tracked. Services keep running
 after you pick another menu option -- nothing is auto-killed.

  [RUNNING] Admin (Dashboard)            pid 14822   port 5001  up 12:04
  [RUNNING] Static Site Publisher        pid 14890   port 5011  up 03:41

  1) Launch Admin (Dashboard)            [:5001]
  2) Launch Page Editor (V1)             [:5002]
  3) Launch Page Editor V2               [:5003]
  4) Launch Static Site Publisher        [:5001]
  5) Launch Persona Hub (Profile Manager) [:5004]
  (Ports come from config.json — edit it to change any service's default.)

  l) View recent log for a service
  k) Force-close one running service
  a) Force-close ALL services
  q) Quit menu (services keep running in background)
  x) Quit menu AND stop everything
====================================================================
 Select an option:
```

### Proposed v2 Output (57-Column Hard Ceiling, Unified Positional Table)

Every line—dividers, telemetry strip, unified service table, and 3-column hotkey grid—is locked to **$\le 57$ characters**:

```text
=========================================================
 BEJSON CMS LAUNCHER [v2]     ~/.../launcher.104a.bejson
---------------------------------------------------------
 UP_SVC  HOST_IP       CFG_FILE     LOG_DIR         MODE
 2/5     127.0.0.1     config.json  storage/..logs  BG
---------------------------------------------------------
 ID  STATE   PID    PORT   UPTIME  SERVICE_NAME
 01  UP      14822  5001   12:04   Admin (Dashboard)
 02  STOP    --     5002   --:--   Page Editor (V1)
 03  STOP    --     5003   --:--   Page Editor V2
 04  UP*     14890  5011   03:41   Static Site Publisher
 05  STOP    --     5004   --:--   Persona Hub (Profiles)
=========================================================
 [1-5] Start/Toggle  [R] Restart Svc  [S] Start All
 [K] Kill One Svc    [Z] Kill All     [L] Tail Svc Log
 [P] HTTP Port Probe [O] Open URL     [C] Reload Config
 [E] Export 104a Reg [Q] Quit (Keep)  [X] Quit & Kill All
=========================================================
 [LAST] #04 Publisher bumped 5001->5011 (Admin active)
Action (1-5, R1-R5, K1-K5, L1-L5) >
```

## 3. Core Architectural & UX Improvements in v2

### 3.1 Unified BEJSON Positional Service Table (Eliminates Split Lists)
Instead of rendering a dynamic `status_block()` above a static `1..5` launch menu, v2 merges both into a single **5-row BEJSON Positional Table**:
- **Fixed `Fields` Header**: `ID  STATE   PID    PORT   UPTIME  SERVICE_NAME`
- **Deterministic Row Identity**: Services `01` through `05` never change row position or ID number. Whether a service is `UP`, `UP*` (port-bumped via collision avoidance), `WAIT`, or `STOP`, its telemetry appears in-place on its dedicated row.
- **Collision Indicator (`UP*`)**: When Admin and Publisher are both active and one is bumped to `5011`, the `STATE` column displays `UP*` and `PORT` displays the live bound port (`5011`), immediately visible without scrolling.

### 3.2 Direct Compound Command Grammar (Zero Sub-Menu Prompts)
In v1, killing or tailing a service requires a multi-step prompt (`k` $\rightarrow$ read re-indexed list $\rightarrow$ type number $\rightarrow$ press `Enter` to continue).
In v2, the command parser accepts **compound shorthand commands** directly at the main prompt alongside single-key interactive prompts:
- **Launch / Toggle (`1`–`5`)**: Starts the service if `STOP`, or displays quick actions if already `UP`.
- **Direct Kill (`k1`–`k5`)**: Immediately terminates service `1`–`5` by its fixed ID (eliminating the `_pick_running_service()` re-indexing bug). Typing bare `k` still prompts for `1-5`.
- **Direct Restart (`r1`–`r5`)**: Gracefully stops and relaunches service `1`–`5` in one command.
- **Direct Log Tail (`l1`–`l5`)**: Prints the last 20 lines of service `1`–`5`'s log file without an intermediate selection menu.

### 3.3 Replacing Blocking `input("Press [Enter]...")` with a 1-Line Status Ticker
In v1, every action prints `[System] ...` and halts on `input("Press [Enter] to continue...")`, requiring extra keystrokes after every launch or stop.
- **Proposed Change**: Reserve a dedicated 1-line `[LAST]` status ticker immediately above the `Action >` prompt (e.g., `[LAST] #04 Publisher started (PID 14890, Port 5011)`).
- Only log tailing (`[L]`) and port probe reports (`[P]`) pause for `[Enter]`; launching, restarting, and killing update the table and `[LAST]` ticker instantaneously.
- **Typewriter Discipline**: Run `typewrite()` only once on initial cold boot of the launcher—never inside the `print_menu()` refresh loop.

### 3.4 Missing Operational Controls Added to the 3-Column Grid
1. **`[R] Restart Svc (`r1`-`r5`)`**: Single-step `SIGTERM` $\rightarrow$ wait $\rightarrow$ `Popen` cycle for rapid code/template iteration.
2. **`[S] Start All`**: Boots all 5 CMS services concurrently (automatically resolving the Admin/Publisher `5001 -> 5011` collision). Renamed destructive "Close All" from `a` to `z` (`[Z] Kill All`) so `a`/`s` isn't accidentally pressed expecting "Start All".
3. **`[P] HTTP Port Probe`**: Uses `socket.create_connection(("127.0.0.1", port), timeout=0.4)` to verify whether each `UP` process is actively accepting TCP connections on its assigned port (`LISTEN` vs. `BOOTING` vs. `DEAD`).
4. **`[O] Open URL (`o1`-`o5`)`**: Dispatches `termux-open-url http://127.0.0.1:<port>` (when running in Termux) or `webbrowser.open()` on desktop Linux/macOS.
5. **`[C] Reload Config`**: Re-reads `config.json` via `CMSPorts.get_port()` and updates default ports for any stopped services without restarting the launcher.

### 3.5 Migrating `launcher_registry.json` to Atomic BEJSON 104a
Replace `storage/tmp/launcher_registry.json` with `storage/tmp/launcher_registry.104a.bejson` written atomically via temporary file + `os.replace()`:

```json
{
  "Format": "BEJSON",
  "Format_Version": "104a",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": "CMS_Service_Registry",
  "Fields": [
    {"name": "service_key", "type": "string"},
    {"name": "pid", "type": "integer"},
    {"name": "port", "type": "integer"},
    {"name": "port_bumped", "type": "boolean"},
    {"name": "started_iso", "type": "string"},
    {"name": "log_file", "type": "string"}
  ],
  "Values": [
    ["admin", 14822, 5001, false, "2026-10-22T20:10:00", "BEJSON_CMS_Admin.py.log"],
    ["publisher", 14890, 5011, true, "2026-10-22T20:18:23", "BEJSON_CMS_Publisher.py.log"]
  ]
}
```

## 4. Proposed Reference Implementation (`print_menu` & Command Loop)

```python
DIV_MAIN = "=" * 57
DIV_SUB  = "-" * 57

def render_menu(last_msg: str = "Ready."):
    os.system("clear" if os.name != "nt" else "cls")
    with _lock:
        snapshot = dict(_running)

    up_count = sum(1 for v in snapshot.values() if _pid_alive(v["pid"]))

    line(DIV_MAIN, RED)
    line(f" {'BEJSON CMS LAUNCHER [v2]':<28} {'~/.../launcher.104a.bejson':>26}", RED)
    line(DIV_SUB, DIM)

    # Band 1: Launcher Telemetry Strip (Fields -> Values)
    line(f" {'UP_SVC':<7} {'HOST_IP':<13} {'CFG_FILE':<12} {'LOG_DIR':<15} {'MODE':<4}", BOLD)
    line(f" {f'{up_count}/{len(SERVICES)}':<7} {'127.0.0.1':<13} {'config.json':<12} {'storage/..logs':<15} {'BG':<4}", WHITE)
    line(DIV_SUB, DIM)

    # Band 2: Unified Positional Service Table (Fields -> Values)
    line(f" {'ID':<3} {'STATE':<7} {'PID':<6} {'PORT':<6} {'UPTIME':<7} {'SERVICE_NAME':<22}", BOLD)
    for num, entry in SERVICES.items():
        info = snapshot.get(entry["key"])
        cfg_port = CMSPorts.get_port(str(CONFIG_PATH), entry["setting_name"], entry["port_env"])
        if info and _pid_alive(info["pid"]):
            uptime = int((datetime.now() - datetime.fromisoformat(info["started"])).total_seconds())
            mins, secs = divmod(uptime, 60)
            state_str = "UP*" if info["port"] != cfg_port else "UP"
            state_col = f"{GREEN}{state_str:<7}{RESET}"
            pid_str = f"{info['pid']:<6}"
            port_str = f"{info['port']:<6}"
            up_str = f"{mins:02d}:{secs:02d}  "
        else:
            state_col = f"{DIM}{'STOP':<7}{RESET}"
            pid_str = f"{DIM}{'--':<6}{RESET}"
            port_str = f"{cfg_port:<6}"
            up_str = f"{DIM}{'--:--':<7}{RESET}"

        short_label = entry["label"][:22]
        with _print_lock:
            print(f" {WHITE}{int(num):02d}  {state_col} {WHITE}{pid_str} {port_str} {up_str} {short_label:<22}{RESET}")

    line(DIV_MAIN, RED)
    # Band 3: 3-Column Action Grid (19 + 18 + 18 = 55 chars + leading space)
    line(f" {'[1-5] Start/Toggle':<19} {'[R] Restart Svc':<18} {'[S] Start All':<18}", WHITE)
    line(f" {'[K] Kill One Svc':<19} {'[Z] Kill All':<18} {'[L] Tail Svc Log':<18}", WHITE)
    line(f" {'[P] HTTP Port Probe':<19} {'[O] Open URL':<18} {'[C] Reload Config':<18}", WHITE)
    line(f" {'[E] Export 104a Reg':<19} {'[Q] Quit (Keep)':<18} {'[X] Quit & Kill':<18}", WHITE)
    line(DIV_MAIN, RED)
    line(f" [LAST] {last_msg[:48]}", DIM)
```

## 5. Implementation Roadmap

1. **Phase 1 — Persist State as BEJSON 104a**: Upgrade `_load_registry()` and `_save_registry()` to read/write `launcher_registry.104a.bejson` atomically via `.tmp` swap, maintaining backward-compatible fallback migration if an older `launcher_registry.json` exists on disk.
2. **Phase 2 — Replace `status_block()` + `print_menu()` with `render_menu()`**: Lock all borders and rows to 57 columns, unify the status and launch lists into the 5-row positional table, and move `typewrite()` out of the redraw loop to initial startup only.
3. **Phase 3 — Upgrade Command Dispatcher**: Support both single-letter interactive flows (`k`, `r`, `l`, `o`) and direct compound commands (`k1`–`k5`, `r1`–`r5`, `l1`–`l5`, `o1`–`o5`) using fixed service IDs `1..5` so service indices never shift dynamically.
4. **Phase 4 — Add Port Readiness Probe (`[P]`) & Batch Start (`[S]`)**: Add non-blocking TCP socket probes to verify Flask startup health and a one-key stack launcher.
