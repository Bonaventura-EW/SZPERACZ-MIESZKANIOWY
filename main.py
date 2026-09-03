#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Punkt wejścia.
Uruchamia scan i zapisuje status API do data/scan_status.json i data/scan_history.json.
"""

import sys
import json
import os
import argparse
import traceback
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATUS_PATH  = os.path.join(DATA_DIR, "scan_status.json")
HISTORY_PATH = os.path.join(DATA_DIR, "scan_history.json")
API_PATH     = os.path.join(DATA_DIR, "api.json")

MAX_HISTORY_ENTRIES = 50
API_SCAN_ENTRIES    = 3


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


def save_api(status_data, history_data):
    """Generuje uproszczony plik api.json: łączna liczba ogłoszeń + 3 ostatnie scany."""
    profile_key = "mieszkania_lublin"

    def _extract_scan(entry):
        profiles = {p["key"]: p for p in entry.get("profiles", [])}
        p = profiles.get(profile_key, {})
        added   = p.get("listings_new")
        removed = p.get("listings_removed")
        return {
            "date":           entry["timestamp"][:10],
            "timestamp":      entry["timestamp"],
            "total_listings": p.get("listings_total") or entry.get("listings_total"),
            "active_listings": p.get("listings_active") or entry.get("listings_active"),
            "added":          added,
            "removed":        removed,
        }

    # Bierzemy ostatnie 3 udane scany z historii (najnowszy ostatni → odwróć do newest-first)
    successful = [s for s in history_data.get("scans", []) if s.get("status") == "success"]
    last_three = [_extract_scan(s) for s in successful[-API_SCAN_ENTRIES:]]
    last_three.reverse()

    # Bieżący total z właśnie zakończonego scanu
    current_profiles = {p["key"]: p for p in status_data.get("profiles", [])}
    cp = current_profiles.get(profile_key, {})
    total_now = cp.get("listings_total") or status_data.get("listings_total")

    api_data = {
        "last_updated":   status_data["timestamp"],
        "total_listings": total_now,
        # Oferty uznane za żywe: znalezione w sweepie + potwierdzone bezpośrednio po URL-u.
        # total_listings zostaje surowym wynikiem sweepu (kompatybilność wstecz).
        "active_listings": cp.get("listings_active") or status_data.get("listings_active") or total_now,
        "scans":          last_three,
    }
    # Niepełny scan (masowy "missing") — wystawiamy ostrzeżenie w publicznym API.
    if status_data.get("warning"):
        api_data["warning"] = status_data["warning"]

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(API_PATH, "w", encoding="utf-8") as f:
        json.dump(api_data, f, ensure_ascii=False, indent=2)


def build_profiles_summary(results):
    """
    Buduje listę per-profil z polami:
      key, label, listings_total, listings_new, listings_removed, crosscheck
    Dane bierze z results[pk]["flow"] — wstrzykniętego przez scraper.generate_dashboard_json.
    """
    profiles = []
    for pk, r in results.items():
        flow = r.get("flow", {})
        entry = {
            "key":              pk,
            "label":            flow.get("label", pk),
            "listings_total":   flow.get("listings_total", r.get("count")),
            # listings_active = oferty uznane za żywe (sweep + potwierdzone po URL-u).
            # listings_total zostaje "ile znalazł sweep" — semantyka publicznego API bez zmian.
            "listings_active":  flow.get("listings_active"),
            "listings_new":     flow.get("listings_new"),
            "listings_removed": flow.get("listings_removed"),
            "crosscheck":       flow.get("crosscheck", r.get("crosscheck")),
            "verified_alive":   flow.get("verified_alive"),
            "verified_dead":    flow.get("verified_dead"),
            "verified_unknown": flow.get("verified_unknown"),
            "pages_scraped":    flow.get("pages_scraped"),
            "pages_expected":   flow.get("pages_expected"),
            "header_count":     flow.get("header_count"),
        }
        if flow.get("verification_skipped"):
            entry["verification_skipped"] = flow["verification_skipped"]
        # Przy anomalii flow jest pusty (profil pominięty w generate_dashboard_json) —
        # powody odrzucenia siedzą bezpośrednio w wyniku scrapera.
        if r.get("anomaly_reasons"):
            entry["anomaly_reasons"] = r["anomaly_reasons"]
        if r.get("previous_good_count") is not None:
            entry["previous_good_count"] = r["previous_good_count"]
        # Ostrzeżenie o niepełnym scanie (masowy "missing") — surfaced przez API.
        if flow.get("partial_scan_warning"):
            entry["partial_scan_warning"] = flow["partial_scan_warning"]
        profiles.append(entry)
    return profiles


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SZPERACZ MIESZKANIOWY — uruchamia scan OLX i zapisuje status API.")
    parser.add_argument("--scan", action="store_true",
                        help="Uruchom scan (działanie domyślne — wywołanie bez argumentów też skanuje).")
    parser.parse_args()  # walidacja argumentów; --scan to jedyny/domyślny tryb

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
        "listings_active":  None,
        "listings_new":     None,
        "listings_removed": None,
        "scan_number":      scan_number,
        "profiles":         [],
        "error":            None,
        "error_detail":     None,
        "warning":          None,
    }

    try:
        from scraper import run_scan
        results = run_scan()

        scan_end  = datetime.now(timezone.utc)
        duration  = int((scan_end - scan_start).total_seconds())
        profiles  = build_profiles_summary(results)

        listings_total   = sum(p["listings_total"]   or 0 for p in profiles)
        listings_active  = sum(p.get("listings_active") or p["listings_total"] or 0 for p in profiles)
        listings_new     = sum(p["listings_new"]     or 0 for p in profiles if p["listings_new"]     is not None)
        listings_removed = sum(p["listings_removed"] or 0 for p in profiles if p["listings_removed"] is not None)

        # Jeśli żaden profil nie miał danych flow (np. pierwszy scan) — ustaw None
        has_flow = any(p["listings_new"] is not None for p in profiles)

        # Wykryj anomaly_detected — jeśli WSZYSTKIE profile są anomalią → status: anomaly_detected
        anomaly_profiles = [p for p in profiles if p.get("crosscheck") == "anomaly_detected"]
        scan_status = "success"
        if anomaly_profiles and len(anomaly_profiles) == len(profiles):
            scan_status = "anomaly_detected"
        elif anomaly_profiles:
            scan_status = "partial_anomaly"

        # Ostrzeżenie o niepełnym scanie (masowy "missing" w jednym scanie).
        # Dane SĄ zapisane (znalezione oferty są realne), ale sygnalizujemy ryzyko
        # — przy drugim niepełnym scanie z rzędu grozi masowa archiwizacja.
        partial_scan_profiles = [p for p in profiles if p.get("partial_scan_warning")]
        scan_warning = None
        if partial_scan_profiles:
            scan_warning = "; ".join(
                f"[{p['key']}] {p['partial_scan_warning']['message']}"
                for p in partial_scan_profiles
            )
            if scan_status == "success":
                scan_status = "partial_scan"

        # Komunikat dla API gdy zadziałał mechanizm anomalii (sanity check) —
        # bez tego pola error/error_detail zostawały None i nie było widać, czemu scan padł.
        anomaly_error = None
        anomaly_detail = None
        if anomaly_profiles:
            parts = []
            for p in anomaly_profiles:
                reasons = p.get("anomaly_reasons") or []
                rtxt = " | ".join(reasons) if reasons else "sanity check nie przeszedł"
                parts.append(f"[{p['key']}] {rtxt}")
            anomaly_detail = "; ".join(parts)
            if scan_status == "anomaly_detected":
                anomaly_error = ("Scan odrzucony przez mechanizm anomalii (sanity check) — "
                                 "dane NIE zostały zaktualizowane")
            else:
                anomaly_error = ("Część profili odrzucona przez mechanizm anomalii (sanity check) — "
                                 "dane tych profili NIE zostały zaktualizowane")

        status.update({
            "status":           scan_status,
            "duration_seconds": duration,
            "listings_total":   listings_total,
            "listings_active":  listings_active,
            "listings_new":     listings_new     if has_flow else None,
            "listings_removed": listings_removed if has_flow else None,
            "profiles":         profiles,
            "error":            anomaly_error,
            "error_detail":     anomaly_detail,
            "warning":          scan_warning,
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
        "listings_active":  status.get("listings_active"),
        "listings_new":     status["listings_new"],
        "listings_removed": status["listings_removed"],
        "scan_number":      status["scan_number"],
        "profiles":         status.get("profiles", []),
        "error":            status.get("error"),
        "warning":          status.get("warning"),
    }
    history["scans"].append(history_entry)
    history["total_scans"] = scan_number

    if len(history["scans"]) > MAX_HISTORY_ENTRIES:
        history["scans"] = history["scans"][-MAX_HISTORY_ENTRIES:]

    save_history(history)
    save_api(status, history)

    # Wynik w logach GitHub Actions
    if status["status"] in ("success", "partial_scan"):
        icon = "✅" if status["status"] == "success" else "⚠️ "
        print(f"{icon} Scan #{scan_number} OK — {status['listings_active']} aktywnych ofert"
              f" (sweep: {status['listings_total']})"
              f" | nowe: {status['listings_new']} | usunięte: {status['listings_removed']}"
              f" | czas: {status['duration_seconds']}s")
        for p in status.get("profiles", []):
            print(f"   [{p['key']}] {p['label']}: "
                  f"active={p.get('listings_active')} "
                  f"sweep={p['listings_total']} "
                  f"stron={p.get('pages_scraped')}/{p.get('pages_expected')} "
                  f"header={p.get('header_count')} "
                  f"weryfikacja(żywe/martwe/?)={p.get('verified_alive')}/{p.get('verified_dead')}/{p.get('verified_unknown')} "
                  f"new={p['listings_new']} "
                  f"removed={p['listings_removed']} "
                  f"crosscheck={p['crosscheck']}")
            if p.get("verification_skipped"):
                print(f"      weryfikacja pominięta: {p['verification_skipped']}")
        if status.get("warning"):
            print(f"⚠️  OSTRZEŻENIE (niepełny scan): {status['warning']}")
    elif status["status"] in ("anomaly_detected", "partial_anomaly"):
        print(f"⚠️  Scan #{scan_number} ANOMALY — {status['error']}")
        if status.get("error_detail"):
            print(f"   powód: {status['error_detail']}")
        sys.exit(1)
    else:
        print(f"❌ Scan #{scan_number} FAILED — {status['error']}")
        sys.exit(1)
