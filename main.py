#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Punkt wejścia.
Uruchamia scan i zapisuje status API do data/scan_status.json i data/scan_history.json.
"""

import sys
import json
import os
import traceback
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATUS_PATH  = os.path.join(DATA_DIR, "scan_status.json")
HISTORY_PATH = os.path.join(DATA_DIR, "scan_history.json")

MAX_HISTORY_ENTRIES = 50


def load_scan_history():
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"scans": [], "total_scans": 0}


def load_previous_status():
    if os.path.exists(STATUS_PATH):
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_status(status_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)


def save_history(history_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)


def compute_new_listings(results, previous_status):
    """Porównuje aktualny scan z poprzednim — liczy nowe i usunięte ogłoszenia."""
    if not results or not previous_status:
        return None, None

    prev_total = previous_status.get("listings_total")
    curr_total = sum(r.get("count", 0) for r in results.values())

    if prev_total is None:
        return None, None

    delta = curr_total - prev_total
    new_count     = max(0, delta)
    removed_count = max(0, -delta)
    return new_count, removed_count


if __name__ == "__main__":
    scan_start = datetime.now(timezone.utc)
    scan_number = 1

    history = load_scan_history()
    previous_status = load_previous_status()

    if history["scans"]:
        scan_number = history["total_scans"] + 1

    status = {
        "status": "error",
        "timestamp": scan_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": None,
        "listings_total": None,
        "listings_new": None,
        "listings_removed": None,
        "scan_number": scan_number,
        "error": None,
        "error_detail": None,
        "crosscheck": None,
    }

    try:
        from scraper import run_scan
        results = run_scan()

        scan_end = datetime.now(timezone.utc)
        duration = int((scan_end - scan_start).total_seconds())

        total = sum(r.get("count", 0) for r in results.values())
        new_count, removed_count = compute_new_listings(results, previous_status)

        # Crosscheck summary (np. "passed", "passed_retry", "error")
        crosschecks = [r.get("crosscheck", "") for r in results.values()]
        crosscheck_summary = crosschecks[0] if len(crosschecks) == 1 else ", ".join(crosschecks)

        status.update({
            "status": "success",
            "duration_seconds": duration,
            "listings_total": total,
            "listings_new": new_count,
            "listings_removed": removed_count,
            "crosscheck": crosscheck_summary,
            "error": None,
            "error_detail": None,
        })

    except Exception as e:
        scan_end = datetime.now(timezone.utc)
        duration = int((scan_end - scan_start).total_seconds())
        tb = traceback.format_exc()
        # Skróć traceback do ostatnich 800 znaków — wystarczy do diagnostyki
        error_detail = tb[-800:].strip() if len(tb) > 800 else tb.strip()

        status.update({
            "status": "error",
            "duration_seconds": duration,
            "error": type(e).__name__ + ": " + str(e)[:200],
            "error_detail": error_detail,
        })

    # Zapisz aktualny status
    save_status(status)

    # Dodaj do historii
    history_entry = {
        "timestamp":        status["timestamp"],
        "timestamp_local":  status["timestamp_local"],
        "status":           status["status"],
        "duration_seconds": status["duration_seconds"],
        "listings_total":   status["listings_total"],
        "listings_new":     status["listings_new"],
        "listings_removed": status["listings_removed"],
        "scan_number":      status["scan_number"],
        "crosscheck":       status.get("crosscheck"),
        "error":            status.get("error"),
    }
    history["scans"].append(history_entry)
    history["total_scans"] = scan_number

    # Zachowaj tylko ostatnie N wpisów
    if len(history["scans"]) > MAX_HISTORY_ENTRIES:
        history["scans"] = history["scans"][-MAX_HISTORY_ENTRIES:]

    save_history(history)

    # Wynik w logach GitHub Actions
    if status["status"] == "success":
        print(f"✅ Scan #{scan_number} OK — {status['listings_total']} ogłoszeń"
              f" | nowe: {status['listings_new']} | usunięte: {status['listings_removed']}"
              f" | czas: {status['duration_seconds']}s")
    else:
        print(f"❌ Scan #{scan_number} FAILED — {status['error']}")
        sys.exit(1)
