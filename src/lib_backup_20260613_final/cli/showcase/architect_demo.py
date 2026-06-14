#!/usr/bin/env python3
"""
Name: architect_demo.py
Description: UI Structural Mastery showcase using 'rich' layouts.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-architect-001
"""

import os
import time
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["main"].split_row(
        Layout(name="sidebar", side="left", size=30),
        Layout(name="body", ratio=1),
    )
    return layout

def run(term, console):
    layout = make_layout()
    
    # Header
    layout["header"].update(Panel("[bold white]ARCHITECT MODULE: SYSTEM TOPOLOGY[/bold white]", border_style="#DE2626"))
    
    # Sidebar (Registry Simulation)
    table = Table(title="Live Registry", border_style="#DE2626", expand=True)
    table.add_column("Key", style="cyan")
    table.add_column("Val", justify="right")
    table.add_row("CPU", "12%")
    table.add_row("MEM", "4.2GB")
    table.add_row("OS", "Android")
    layout["sidebar"].update(Panel(table, border_style="#DE2626"))
    
    # Body (Documentation Simulation)
    doc_text = """
# GEMINI CLI ARCHITECTURE
The system operates on a **Registry-First Discovery** mandate.
All paths are resolved via the `Paths` entity.

- **Master**: Termux / Home
- **Slave**: Admin / External
- **Federation**: Atomic Sync
    """
    layout["body"].update(Panel(Markdown(doc_text), border_style="#DE2626", title="System Docs"))
    
    # Footer
    layout["footer"].update(Panel("[bold #DE2626]0.[/bold #DE2626] Return | [bold #DE2626]1.[/bold #DE2626] Toggle Layout", border_style="#DE2626"))

    with console.screen():
        while True:
            console.print(layout)
            with term.cbreak():
                val = term.inkey()
                if val == '0':
                    break
                if val == '1':
                    # Toggle visibility logic simulation
                    layout["sidebar"].visible = not layout["sidebar"].visible
            os.system('cls' if os.name == 'nt' else 'clear')
