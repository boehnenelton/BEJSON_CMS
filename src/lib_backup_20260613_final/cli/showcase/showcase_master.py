#!/usr/bin/env python3
"""
Name: showcase_master.py
Description: Numeric-driven master controller for the GEMINI Python Terminal Showcases.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-master-001
"""

import os
import sys
import time
from pathlib import Path

# Mandatory Portability
def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()
VERSION = "1.0.0"

# BEJSON Red Accent
RED_ANSI = "\033[38;2;222;38;38m"
RESET_ANSI = "\033[0m"

try:
    from art import tprint
    from rich.console import Console
    from rich.panel import Panel
    from blessed import Terminal
except ImportError:
    print(f"{RED_ANSI}Error: Missing dependencies. Run: pip install rich art blessed{RESET_ANSI}")
    sys.exit(1)

console = Console()
term = Terminal()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def draw_header():
    header = f" GEMINI SHOWCASE v{VERSION} | NUMERIC NAVIGATION MODE "
    print(term.move_y(0) + term.black_on_red(term.center(header)))

def main_menu():
    clear_screen()
    draw_header()
    
    print(term.move_y(3))
    print(f"{RED_ANSI}")
    tprint("GEMINI", font="block")
    print(f"{RESET_ANSI}")
    
    menu_text = (
        "[bold white]Select a Showcase Module:[/bold white]\n\n"
        "[bold #DE2626]1.[/bold #DE2626] The Architect (UI Layouts)\n"
        "[bold #DE2626]2.[/bold #DE2626] The Pulse (Graphing/Subplots)\n"
        "[bold #DE2626]3.[/bold #DE2626] The Engine (Progress/Timers)\n"
        "[bold #DE2626]4.[/bold #DE2626] The Brand (ASCII/Typography)\n"
        "[bold #DE2626]5.[/bold #DE2626] The Core (Logic/State)\n\n"
        "[bold #DE2626]0.[/bold #DE2626] Exit Session"
    )
    
    console.print(Panel(menu_text, border_style="#DE2626", expand=False))
    
    while True:
        with term.cbreak():
            val = term.inkey()
            if val == '0':
                return '0'
            if val in ['1', '2', '3', '4', '5']:
                return val

def run_module(choice):
    # Dynamic imports for modules to keep it clean
    try:
        if choice == '1':
            import architect_demo as demo
        elif choice == '2':
            import pulse_demo as demo
        elif choice == '3':
            import engine_demo as demo
        elif choice == '4':
            import brand_demo as demo
        elif choice == '5':
            import core_demo as demo
        
        # Every demo will have a main() function
        demo.run(term, console)
    except ImportError:
        console.print(f"\n[bold red]Error:[/bold red] Module {choice} not yet implemented.")
        time.sleep(2)
    except Exception as e:
        console.print(f"\n[bold red]Runtime Error:[/bold red] {e}")
        time.sleep(2)

if __name__ == "__main__":
    try:
        while True:
            choice = main_menu()
            if choice == '0':
                break
            run_module(choice)
    except KeyboardInterrupt:
        pass
    finally:
        clear_screen()
        print(f"\n{RED_ANSI}GEMINI Session Terminated.{RESET_ANSI}")
