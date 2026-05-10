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


def save_status(status_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)


def save_history(history_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)


def build_profiles_summary(results):
    """
    Buduje listę per-profil z polami:
      key, label, listings_total, listings_new, listings_removed, crosscheck
    Dane bierze z results[pk]["flow"] — wstrzykniętego przez scraper.generate_dashboard_json.
    """
    profiles = []
    for pk, r in results.items():
        flow = r.get("flow", {})
        profiles.append({
            "key":              pk,
            "label":            flow.get("label", pk),
            "listings_total":   flow.get("listings_total", r.get("count")),
            "listings_new":     flow.get("listings_new"),
            "listings_removed": flow.get("listings_removed"),
            "crosscheck":       flow.get("crosscheck", r.get("crosscheck")),
        })
    return profiles


if __name__ == "__main__":
    scan_start  = datetime.now(timezone.utc)
    scan_number = 1

    history = load_scan_history()
    if history["scans"]:
        scan_number = history["total_scans"] + 1

    status = {
        "status":           "error",
        "timestamp":        scan_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": None,
        "listings_total":   None,
        "listings_new":     None,
        "listings_removed": None,
        "scan_number":      scan_number,
        "profiles":         [],
        "error":            None,
        "error_detail":     None,
    }

    try:
        from scraper import run_scan
        results = run_scan()

        scan_end  = datetime.now(timezone.utc)
        duration  = int((scan_end - scan_start).total_seconds())
        profiles  = build_profiles_summary(results)

        listings_total   = sum(p["listings_total"]   or 0 for p in profiles)
        listings_new     = sum(p["listings_new"]     or 0 for p in profiles if p["listings_new"]     is not None)
        listings_removed = sum(p["listings_removed"] or 0 for p in profiles if p["listings_removed"] is not None)

        # Jeśli żaden profil nie miał danych flow (np. pierwszy scan) — ustaw None
        has_flow = any(p["listings_new"] is not None for p in profiles)

        status.update({
            "status":           "success",
            "duration_seconds": duration,
            "listings_total":   listings_total,
            "listings_new":     listings_new     if has_flow else None,
            "listings_removed": listings_removed if has_flow else None,
            "profiles":         profiles,
            "error":            None,
            "error_detail":     None,
        })

    except Exception as e:
        scan_end = datetime.now(timezone.utc)
        duration = int((scan_end - scan_start).total_seconds())
        tb = traceback.format_exc()
        error_detail = tb[-800:].strip() if len(tb) > 800 else tb.strip()

        status.update({
            "status":           "error",
            "duration_seconds": duration,
            "error":            type(e).__name__ + ": " + str(e)[:200],
            "error_detail":     error_detail,
        })

    # Zapisz aktualny status
    save_status(status)

    # Dodaj do historii (bez error_detail — za ciężkie)
    history_entry = {
        "timestamp":        status["timestamp"],
        "timestamp_local":  status["timestamp_local"],
        "status":           status["status"],
        "duration_seconds": status["duration_seconds"],
        "listings_total":   status["listings_total"],
        "listings_new":     status["listings_new"],
        "listings_removed": status["listings_removed"],
        "scan_number":      status["scan_number"],
        "profiles":         status.get("profiles", []),
        "error":            status.get("error"),
    }
    history["scans"].append(history_entry)
    history["total_scans"] = scan_number

    if len(history["scans"]) > MAX_HISTORY_ENTRIES:
        history["scans"] = history["scans"][-MAX_HISTORY_ENTRIES:]

    save_history(history)

    # Wynik w logach GitHub Actions
    if status["status"] == "success":
        print(f"✅ Scan #{scan_number} OK — {status['listings_total']} ogłoszeń"
              f" | nowe: {status['listings_new']} | usunięte: {status['listings_removed']}"
              f" | czas: {status['duration_seconds']}s")
        for p in status.get("profiles", []):
            print(f"   [{p['key']}] {p['label']}: "
                  f"total={p['listings_total']} "
                  f"new={p['listings_new']} "
                  f"removed={p['listings_removed']} "
                  f"crosscheck={p['crosscheck']}")
    else:
        print(f"❌ Scan #{scan_number} FAILED — {status['error']}")
        sys.exit(1)
