#!/usr/bin/env python3
"""
Name: brand_demo.py
Description: ASCII Art & Typography showcase using 'art'.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-brand-001
"""

import os
from art import tprint, art
from rich.panel import Panel

def run(term, console):
    RED_ANSI = "\033[38;2;222;38;38m"
    RESET_ANSI = "\033[0m"
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print(Panel("[bold white]BRAND MODULE: VISUAL IDENTITY[/bold white]", border_style="#DE2626"))
        
        print("\n[ 1 ] Block (GEMINI)")
        print("[ 2 ] Bulbhead (BEJSON)")
        print("[ 3 ] Script (Core)")
        print("[ 4 ] Random Art")
        print("[ 0 ] Return")
        
        with term.cbreak():
            choice = term.inkey()
            if choice == '0':
                break
            
            print(f"\n{RED_ANSI}")
            if choice == '1':
                tprint("GEMINI", font="block")
            elif choice == '2':
                tprint("BEJSON", font="bulbhead")
            elif choice == '3':
                tprint("Core", font="script")
            elif choice == '4':
                print(art("coffee"))
            
            print(f"{RESET_ANSI}")
            if choice in ['1', '2', '3', '4']:
                print(f"\n\033[38;2;222;38;38mPress any key to clear...\033[0m")
                term.inkey()
