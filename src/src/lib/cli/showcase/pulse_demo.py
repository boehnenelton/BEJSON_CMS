#!/usr/bin/env python3
"""
Name: pulse_demo.py
Description: Data Visualization showcase using 'plotext'.
Version: 1.0.0
Date Created: 2026-06-12
Author: Elton Boehnen
Relational ID: gcli-showcase-pulse-001
"""

import os
import time
import plotext as plt
from rich.panel import Panel

def run(term, console):
    RED_ACCENT = "#DE2626"
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print(Panel("[bold white]PULSE MODULE: NEURAL FREQUENCIES[/bold white]", border_style="#DE2626"))
        
        print("\n[ 1 ] Sine Wave (Neural Frequency)")
        print("[ 2 ] Bar Chart (Resource Allocation)")
        print("[ 3 ] Scatter Plot (Entity Density)")
        print("[ 0 ] Return")
        
        with term.cbreak():
            choice = term.inkey()
            if choice == '0':
                break
            
            plt.clf()
            plt.theme("dark")
            
            if choice == '1':
                y = plt.sin()
                plt.plot(y, color=RED_ACCENT)
                plt.title("Neural Sine Frequency")
                plt.show()
            elif choice == '2':
                data = [10, 20, 35, 12, 45]
                labels = ["CPU", "MEM", "DSK", "NET", "GPU"]
                plt.bar(labels, data, color=RED_ACCENT)
                plt.title("Resource Distribution")
                plt.show()
            elif choice == '3':
                x = plt.sin(100, 1)
                y = plt.sin(100, 2)
                plt.scatter(x, y, color=RED_ACCENT)
                plt.title("Entity Clustering")
                plt.show()
            
            if choice in ['1', '2', '3']:
                print(f"\n\033[38;2;222;38;38mPress any key to clear graph...\033[0m")
                term.inkey()
