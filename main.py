#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Punkt wejścia.
"""

import sys
from scraper import run_scan

if __name__ == "__main__":
    if "--scan" in sys.argv or True:
        run_scan()
