#!/usr/bin/env python3
"""
Name: gemini_showcase_intro.py
Description: Cinematic terminal showcase for Gemini CLI ecosystem.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-001
"""

import os
import sys
import time
import random
from pathlib import Path
from datetime import datetime

# Mandatory Portability Logic
def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()
VERSION = "1.0.0"

# Branding Constants
RED_ACCENT = "#DE2626"
RED_ANSI = "\033[38;2;222;38;38m"
RESET_ANSI = "\033[0m"

try:
    from art import tprint, art
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    import plotext as plt
    import questionary
    from blessed import Terminal
except ImportError as e:
    print(f"{RED_ANSI}Error: Missing library - {e}{RESET_ANSI}")
    print("Please run: pip install rich plotext questionary blessed art")
    sys.exit(1)

console = Console()
term = Terminal()

def cinematic_startup():
    """Phase 1: Cinematic Startup Sequence"""
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # 1. Banners (art)
    print(RED_ANSI)
    tprint("GEMINI", font="block")
    print(RESET_ANSI)
    
    # 2. Boot Sequence (rich)
    with Progress(
        SpinnerColumn(style=f"bold {RED_ACCENT}"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, complete_style=RED_ACCENT, finished_style=RED_ACCENT),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        t1 = progress.add_task("Initializing Core...", total=100)
        t2 = progress.add_task("Mapping Registry...", total=100)
        t3 = progress.add_task("Securing Boundaries...", total=100)
        
        while not progress.finished:
            progress.update(t1, advance=random.uniform(1, 5))
            if progress.tasks[0].completed > 30:
                progress.update(t2, advance=random.uniform(2, 8))
            if progress.tasks[1].completed > 60:
                progress.update(t3, advance=random.uniform(5, 15))
            time.sleep(0.05)

    console.print(Panel("[bold white]SYSTEM READY[/bold white]", border_style=RED_ACCENT, expand=False))
    time.sleep(1)

def draw_header(term):
    """Draw a persistent header using blessed"""
    now = datetime.now().strftime("%H:%M:%S")
    header_text = f" GEMINI CORE | VERSION {VERSION} | {now} "
    print(term.move_y(0) + term.black_on_red(term.center(header_text)))

def run_graph_demo():
    """Plotext Graphing Demo"""
    plt.clf()
    plt.theme("dark")
    y = plt.sin()
    plt.plot(y, color=RED_ACCENT)
    plt.title("Core Pulse (Neural Frequency)")
    plt.show()

def run_data_demo():
    """Rich Table Demo"""
    table = Table(title="Registry Preview", border_style=RED_ACCENT, title_style=f"bold {RED_ACCENT}")
    table.add_column("Entity", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Last Sync", style="magenta")
    
    table.add_row("User_Registry", "[green]Online[/green]", "2026-06-12 08:00")
    table.add_row("MFDB_Manifest", "[green]Online[/green]", "2026-06-12 08:05")
    table.add_row("Security_Vault", "[red]Locked[/red]", "N/A")
    
    console.print(table)

def main_loop():
    """Phase 2: Interactive TUI Dashboard"""
    cinematic_startup()
    
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            draw_header(term)
            
            # Using questionary for the menu
            # Since questionary takes over the terminal, we'll run it in a way that returns
            print(term.move_y(2))
            choice = questionary.select(
                "Core Command Center",
                choices=[
                    "1. View Core Pulse (Graphing)",
                    "2. View Registry Status (Data)",
                    "3. System Info (Art/Text)",
                    "4. Exit"
                ],
                style=questionary.Style([
                    ('qmark', f'fg:{RED_ACCENT} bold'),
                    ('question', 'bold'),
                    ('pointer', f'fg:{RED_ACCENT} bold'),
                    ('highlighted', f'fg:{RED_ACCENT} bold'),
                    ('selected', 'fg:white'),
                ])
            ).ask()

            if choice == "4. Exit" or choice is None:
                break
            
            os.system('cls' if os.name == 'nt' else 'clear')
            draw_header(term)
            print(term.move_y(2))
            
            if "1." in choice:
                run_graph_demo()
            elif "2." in choice:
                run_data_demo()
            elif "3." in choice:
                tprint("SYSTEM", font="small")
                console.print(f"[bold {RED_ACCENT}]OS:[/bold {RED_ACCENT}] Android (Termux)")
                console.print(f"[bold {RED_ACCENT}]Platform:[/bold {RED_ACCENT}] ARM64")
                console.print(f"[bold {RED_ACCENT}]Security:[/bold {RED_ACCENT}] ACTIVE")
            
            print(f"\n{RED_ANSI}Press any key to return to menu...{RESET_ANSI}")
            term.inkey()
            os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{RED_ANSI}GEMINI Session Terminated.{RESET_ANSI}")
