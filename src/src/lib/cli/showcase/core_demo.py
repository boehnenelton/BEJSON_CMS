#!/usr/bin/env python3
"""
Name: core_demo.py
Description: Logic & State Navigation showcase using 'blessed'.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-core-001
"""

import os
import time

def run(term, console):
    RED_ANSI = "\033[38;2;222;38;38m"
    RESET_ANSI = "\033[0m"
    
    state = "HOME"
    
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Persistent Header
            print(term.move_y(0) + term.black_on_red(term.center(f" CORE LOGIC ENGINE | STATE: {state} ")))
            
            # Persistent Footer
            footer_text = " [ 0 ] Return to Master | [ 1-3 ] Change State "
            print(term.move_y(term.height - 1) + term.black_on_red(term.center(footer_text)))
            
            print(term.move_y(3))
            if state == "HOME":
                print(f"{term.center('Welcome to the Core Logic Demonstration.')}")
                print(f"\n{term.center('This module shows how to maintain UI state')}")
                print(f"{term.center('without using arrow keys or complex libraries.')}")
            elif state == "RESOURCES":
                print(f"{term.center(RED_ANSI + '--- RESOURCE MONITOR ---' + RESET_ANSI)}")
                print(f"\n{term.center('CPU: [||||||    ] 60%')}")
                print(f"{term.center('RAM: [||||||||  ] 80%')}")
            elif state == "SECURITY":
                print(f"{term.center(RED_ANSI + '!!! SECURITY BOUNDARY ALERT !!!' + RESET_ANSI)}")
                print(f"\n{term.center('Restrictions injected into 14 entities.')}")
                print(f"{term.center('Atomic sync status: ACTIVE')}")
            
            val = term.inkey()
            if val == '0':
                break
            elif val == '1':
                state = "HOME"
            elif val == '2':
                state = "RESOURCES"
            elif val == '3':
                state = "SECURITY"
