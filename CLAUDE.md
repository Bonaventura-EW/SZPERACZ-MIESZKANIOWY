# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Autonomiczny agent monitorujący ogłoszenia mieszkań na wynajem w Lublinie (OLX). Scrape'uje OLX codziennie przez GitHub Actions, śledzi zmiany cen/reaktywacje/promocje, generuje interaktywny dashboard (GitHub Pages) i tygodniowy raport email.

**Dashboard:** https://bonaventura-ew.github.io/SZPERACZ-MIESZKANIOWY/
**Monitorowany URL:** https://www.olx.pl/nieruchomosci/mieszkania/wynajem/lublin/

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run scan manually
python main.py --scan

# Run scraper directly (without writing scan_status.json)
python scraper.py

# Send weekly email report
python email_report.py
```

No test suite, linter, or formatter is configured.

## Architecture

```
main.py → scraper.run_scan() → OLX (HTTP + BeautifulSoup)
                              ↓
              data/dashboard_data.json   (dashboard state)
              data/szperacz_mieszkaniowy.xlsx
              data/scan_status.json      (API: last scan result)
              data/scan_history.json     (API: last 50 scans)
                              ↓
              docs/index.html  (static dashboard, GitHub Pages)
              email_report.py  (weekly HTML email via Gmail SMTP)
```

### scraper.py — kluczowa logika

**PROFILES** (top of file) — słownik konfiguracji źródeł do scrapowania. Jedyne miejsce do dodawania nowych URL-i.

**MAX_PRICE = 10000** — oferty droższe są odrzucane cicho na etapie parsowania. Oferty bez ceny (`None`) przechodzą.

**Pipeline scanu:**
1. `scrape_with_crosscheck()` — scrape + sanity check + ewentualny retry po 90s cooldown
2. `generate_dashboard_json()` — merge z istniejącym stanem (śledzi nowe/usunięte/reakt./odświeżenia/promocje)
3. `update_excel()` — musi być wywołany PO `generate_dashboard_json()` (czyta z JSON refresh_count)

**Sanity checks (zapora przed fałszywymi scanami):**
- `SANITY_MIN_COUNT = 50` — poniżej tej liczby = podejrzenie CAPTCHA/błędu
- `SANITY_MIN_HEADER = 10` — jeśli nagłówek OLX zwraca <10 = strona się nie załadowała
- `SANITY_MIN_DURATION_S = 30` — scan szybszy niż 30s = redirect/CAPTCHA
- `SANITY_MAX_DROP_RATIO = 0.40` — spadek >40% vs ostatni udany scan = czerwona flaga
- Przy anomalii: `crosscheck = "anomaly_detected"` → `generate_dashboard_json()` NIE modyfikuje danych

**Mechanizm archiwizacji (2-scan confirmation):**
- Ogłoszenie nieznalezione w scanie: `missing_count += 1`, zostaje w `current_listings`
- Dopiero przy `missing_count >= 2` (dwie nieobecności z rzędu) → przeniesienie do `archived_listings`
- Zabezpiecza przed masową fałszywą archiwizacją gdy OLX zwróci niekompletne wyniki

**Paginacja:**
- Standardowo: `[data-testid="pagination-forward"]`
- Fallback gdy OLX ukryje przycisk przed końcem: szuka max `page=N` w linkach paginacji
- Ochrona przed zapętleniem: jeśli kolejna strona zwraca te same ID → koniec

**Parsowanie kart OLX (`[data-cy="l-card"]`):**
- Każda karta ma WIELE linków `/d/oferta/`. Pierwszy owija obraz (pusty tekst) — iteruj wszystkie
- Detekcja promocji: 5 typów sygnałów (URL params, data-testid, data-*, tekst badge, CSS klasy)

**Nagłówki HTTP — KRYTYCZNE:**
Nie dodawaj: `Accept-Encoding: gzip` (solo), `DNT`, `Cache-Control`, `Referer` — triggerują bot detection lub strip response.

**Warstwa HTTP — impersonacja TLS (`get_session()`):**
- Domyślnie `curl_cffi` z `impersonate="chrome"` — podszywa się pod fingerprint TLS/JA3 prawdziwego Chrome'a (obchodzi blokady WAF, które reagują na pythonowy TLS `requests` mimo poprawnych nagłówków).
- `requests` = automatyczny fallback (gdy `curl_cffi` niedostępny, flaga `_HAS_CURL_CFFI`).
- Przy `impersonate` NIE nadpisuj `User-Agent` — biblioteka dostarcza spójny UA + nagłówki `sec-*` pasujące do TLS. Chrome-TLS + obcy UA = bardziej podejrzane niż samo `requests`.
- Łap błędy sieciowe przez `NETWORK_ERRORS` (tuple obejmujący oba backendy), nie `requests.RequestException`.
- Retry + rotacja (`_http_get()` w `scrape_profile()`): 429/5xx i błędy transportu są ponawiane z backoffem wykładniczym; przy 403 profil impersonacji jest rotowany z `IMPERSONATE_PROFILES` (`_available_impersonate_profiles()` filtruje do wspieranych przez zainstalowany `curl_cffi`). 404/410 przechodzą bez ponawiania. Gdy padną wszystkie profile/próby → wyjątek HTTP (403 nie jest cichy), a sanity check łapie anomalię.

### data/dashboard_data.json — struktura stanu

```json
{
  "last_scan": "2026-04-29 09:00:00",
  "profiles": {
    "mieszkania_lublin": {
      "daily_counts": [{"date", "count", "change", "median_price", "promoted_count", ...}],
      "current_listings": [{"id", "title", "price", "first_seen", "last_seen",
                            "missing_count", "refresh_count", "refresh_history",
                            "reactivation_count", "reactivation_history",
                            "is_promoted", "promoted_days_current", ...}],
      "archived_listings": [...],
      "price_history": {"listing_id": [{"date", "old_price", "new_price", "change"}]},
      "promotion_history": {}
    }
  }
}
```

`median_price` w `daily_counts` = mediana cen NOWYCH ogłoszeń z danego dnia (nie wszystkich). `None` = brak nowych → prawidłowe zachowanie.

### main.py

Tylko orkiestracja: inicjalizuje status, wywołuje `run_scan()`, zapisuje `scan_status.json` i `scan_history.json`. Wykrywa `anomaly_detected` na poziomie profili i ustawia odpowiedni `scan_status` (`success` / `partial_anomaly` / `anomaly_detected`).

### docs/index.html

Zero zewnętrznych zależności (czysty HTML+CSS+JS). Ładuje dane z GitHub Raw (`dashboard_data.json`). Zmienne do edycji na początku pliku: `GITHUB_OWNER`, `GITHUB_REPO`. Auto-refresh co 5 minut, cache-bust przez `?t=Date.now()`.

### GitHub Actions

| Workflow | Harmonogram | Uprawnienia |
|----------|-------------|-------------|
| `scan.yml` | `0 7 * * *` (9:00 CET) | `contents: write` |
| `weekly_report.yml` | `30 7 * * 1` (pon. 9:30 CET) | `contents: read` |
| `failsafe.yml` | `0 11 * * *` (sprawdza, czy scan był) | `contents: write, actions: write` |

Git commit po scanie: `git add data/` (nie `git add -A` — docs/ i kod nie mają być nadpisywane).

## Pułapki i nieoczywiste szczegóły

- `openpyxl`: `Font(color="inherit")` → błąd. Używaj hex lub pomiń parametr.
- Liczniki muszą być spójne: `refresh_count == len(refresh_history)`, `reactivation_count == len(reactivation_history)`.
- OLX miesza ~38% kart Otodom w wynikach kategorii → tolerancja crosschecka = 50% header_count.
- `scan_status.json` zawiera `error_detail` (traceback); `scan_history.json` go nie zawiera (za ciężkie).
- Dodając nowy profil do `PROFILES` — dodaj też konfigurację w `docs/index.html` jeśli dashboard ma go wyświetlać.

## GitHub Secrets

- `EMAIL_PASSWORD` — App Password Gmail (nie hasło konta), używany przez `email_report.py`

## Zasady pracy z gałęziami

Po zakończeniu zestawu zmian zawsze pytam: **"Czy mam zmergować do main?"** — nie merguj samodzielnie bez potwierdzenia.

## Dokumentacja projektu

- `JAK_DZIALA_SYSTEM.md` — pełna dokumentacja architektury (używana też jako szablon dla nowych instancji)
- `API.md` — dokumentacja publicznych endpointów JSON (scan_status, scan_history)
- `CHANGELOG.md` — format Keep a Changelog; **aktualizuj przy każdej zmianie kodu** — bez wyjątku. Emoji prefix: 📧 Email, 🐛 Fix, ✨ Feature, 📊 Chart, ⚙️ Workflow, 🛡️ Guard/Safety. Każdy commit dotyczący kodu musi mieć odpowiadający wpis w CHANGELOG.md.

## Propagacja zmian między repo-braćmi

To repo jest częścią rodziny podobnych projektów i czasem warto przenieść nasze
ulepszenia do rodzeństwa. Dlatego kiedy skończysz istotną zmianę — nową funkcję,
refactor, poprawę wydajności albo dostępności, ważną aktualizację zależności —
zostaw krótką notatkę dla repo-braci: co i dlaczego zmieniłeś. Zapisz ją w
`.propagation/changes/` według wzoru z `_TEMPLATE.md` i zacommituj razem ze
zmianą. Pomijaj to przy drobiazgach: literówkach, formatowaniu, rzeczach
istotnych tylko u nas.

Oceniaj uczciwie, na ile zmiana jest przenośna (pole `generality`). Jeśli coś
jest celowo lokalne i ma nas ODRÓŻNIAĆ od braci — tak to oznacz i dopisz dlaczego.
Rozjazd między projektami bywa zamierzony i system ma go szanować, nie zasypywać.

Plików `.propagation/decisions.jsonl` i `.propagation/state/` nie ruszaj ręcznie —
zarządzają nimi automatyczne przebiegi w tle.
