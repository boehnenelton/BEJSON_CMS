#!/usr/bin/env python3
"""
Name: engine_demo.py
Description: UX Feedback & Timers showcase using 'rich.progress'.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-engine-001
"""

import os
import time
import random
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.live import Live

def run(term, console):
    RED_ACCENT = "#DE2626"
    
    os.system('cls' if os.name == 'nt' else 'clear')
    console.print(Panel("[bold white]ENGINE MODULE: KINETIC FEEDBACK[/bold white]", border_style="#DE2626"))
    
    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {RED_ACCENT}"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, complete_style=RED_ACCENT, finished_style=RED_ACCENT),
        TaskProgressColumn(),
        console=console,
        transient=False
    ) as progress:
        t1 = progress.add_task("Synchronizing MFDB...", total=100)
        t2 = progress.add_task("Injecting Restrictions...", total=100)
        t3 = progress.add_task("Validating Credentials...", total=100)
        
        while not progress.finished:
            progress.update(t1, advance=random.uniform(0.5, 2))
            if progress.tasks[0].completed > 20:
                progress.update(t2, advance=random.uniform(1, 3))
            if progress.tasks[1].completed > 50:
                progress.update(t3, advance=random.uniform(2, 5))
            time.sleep(0.05)

    console.print("\n[bold green]COMPLETED:[/bold green] Kinetic Sync Successful.")
    console.print(f"\n\033[38;2;222;38;38mPress [ 0 ] to return...\033[0m")
    
    while True:
        with term.cbreak():
            if term.inkey() == '0':
                break
