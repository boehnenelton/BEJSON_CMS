"""
Library:      lib_bejson_server.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-06
Description:  API server implementation for BEJSON data distribution.
REMEDIATED:   Import Isolation and Fallback Stubs (Phase 8.1).
"""
import os
import socket
import random
import subprocess
import sys
import json
import time
import shutil
from pathlib import Path
from datetime import datetime

# --- Sibling Path Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.dirname(LIB_DIR) # Core/
if CORE_DIR not in sys.path: sys.path.insert(0, CORE_DIR)

try:
    from lib_bejson_env import resolve_path
    from lib_bejson_core import ResilientPIDLock, bejson_core_atomic_write
except ImportError:
    def resolve_path(p): 
        return p.replace("{HOME}", os.environ.get("HOME", "/data/data/com.termux/files/home"))
    def bejson_core_atomic_write(path, data):
        try:
            with open(path, 'w') as f: json.dump(data, f, indent=2)
            return True
        except Exception: return False
    class ResilientPIDLock:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def acquire(self): return True
        def release(self): pass

def copy_to_clipboard(text):
    """Portable clipboard copy."""
    try:
        if sys.platform == 'linux' and shutil.which('termux-clipboard-set'):
            subprocess.run(["termux-clipboard-set", text], check=False)
        elif sys.platform == 'darwin':
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=False)
        elif sys.platform == 'win32':
            subprocess.run(['clip'], input=text.encode('utf-8'), check=False)
    except Exception:
        pass

def open_url(url):
    """Portable URL open."""
    try:
        if sys.platform == 'linux' and shutil.which('termux-open-url'):
            subprocess.run(['termux-open-url', url], check=False)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        pass

def is_port_in_use(port):
    """Checks if a port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_random_available_port(start=5001, end=5020):
    ports = list(range(start, end + 1))
    random.shuffle(ports)
    for port in ports:
        if not is_port_in_use(port):
            return port
    return None


def register_server(name, port):
    reg_path = resolve_path("{HOME}/Registry/Environment_Registry.bejson.json")
    if not os.path.exists(reg_path): return
    
    with ResilientPIDLock(reg_path, timeout_seconds=10):
        try:
            with open(reg_path, 'r') as f:
                data = json.load(f)
            
            data['Values'] = [v for v in data['Values'] if not (v[0] == 'Running_Server' and v[3] == name)]
            now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            url = f"http://localhost:{port}"
            record = ['Running_Server', now, 'ServerLib', name, url, None, None, str(port), 'ONLINE', 'Global']
            data['Values'].append(record)
            
            # Atomic write via library standard
            bejson_core_atomic_write(reg_path, data)
            
            print(f" [ServerLib] REGISTERED: {name} on {url}")
        except Exception as e:
            print(f" [ServerLib] Registration Error: {e}")

def unregister_server(name):
    reg_path = resolve_path("{HOME}/Registry/Environment_Registry.bejson.json")
    if not os.path.exists(reg_path): return
    
    with ResilientPIDLock(reg_path, timeout_seconds=10):
        try:
            with open(reg_path, 'r') as f:
                data = json.load(f)
            
            data['Values'] = [v for v in data['Values'] if not (v[0] == 'Running_Server' and v[3] == name)]
            
            bejson_core_atomic_write(reg_path, data)
            
            print(f" [ServerLib] UNREGISTERED: {name}")
        except Exception as e:
            print(f" [ServerLib] Unregistration Error: {e}")

def start_flask_server_random(app_path, name=None, debug=False, host='127.0.0.1'):
    """Starts a Flask server on a random port. Default host is 127.0.0.1 for security."""
    port = get_random_available_port()
    if port is None:
        print("FAIL | No available ports.")
        return False

    app_name = name or os.path.splitext(os.path.basename(app_path))[0]
    register_server(app_name, port)
    
    url = f"http://localhost:{port}"
    print(f"--- BEJSON SERVER STARTER ---")
    print(f"Name: {app_name}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"OPEN_URL:{url}")

    copy_to_clipboard(url)
    print(" [ServerLib] URL copied to clipboard.")

    open_url(url)

    env = os.environ.copy()
    env['FLASK_APP'] = app_path
    env['FLASK_DEBUG'] = '1' if debug else '0'
    
    try:
        # Secure default: host=127.0.0.1
        subprocess.run(['flask', 'run', '--host', host, '--port', str(port)], env=env)
    finally:
        unregister_server(app_name)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        start_flask_server_random(sys.argv[1])
    else:
        print("Usage: python3 lib_bejson_server.py <app_path>")
