# 📡 SZPERACZ MIESZKANIOWY — API Documentation

Dane są udostępniane jako **statyczny JSON** hostowany na GitHub Raw.
Nie wymaga autentykacji. Polling co X minut.

---

## Endpoints

### 1. Status ostatniego scanu

```
GET https://raw.githubusercontent.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/main/data/scan_status.json
```

Aktualizowany automatycznie po każdym scanie (codziennie ~9:00 CET, lub ręcznie).

#### Odpowiedź — sukces

```json
{
  "status": "success",
  "timestamp": "2026-04-30T09:00:47Z",
  "timestamp_local": "2026-04-30 11:00:47",
  "duration_seconds": 47,
  "listings_total": 124,
  "listings_new": 8,
  "listings_removed": 3,
  "scan_number": 12,
  "profiles": [
    {
      "key": "mieszkania_lublin",
      "label": "Mieszkania na wynajem — Lublin",
      "listings_total": 124,
      "listings_new": 8,
      "listings_removed": 3,
      "crosscheck": "passed"
    }
  ],
  "error": null,
  "error_detail": null
}
```

#### Odpowiedź — błąd

```json
{
  "status": "error",
  "timestamp": "2026-04-30T09:00:12Z",
  "timestamp_local": "2026-04-30 11:00:12",
  "duration_seconds": 12,
  "listings_total": null,
  "listings_new": null,
  "listings_removed": null,
  "scan_number": 13,
  "profiles": [],
  "error": "ConnectionTimeout: HTTPSConnectionPool(host='www.olx.pl'...)",
  "error_detail": "Traceback (most recent call last):\n  File ...\nrequests.exceptions.ConnectTimeout: ..."
}
```

#### Odpowiedź — anomalia (zadziałał mechanizm sanity check)

Gdy scraper wykryje anomalię (np. spadek liczby ogłoszeń >40% vs ostatni udany scan,
zbyt mała liczba wyników, podejrzenie CAPTCHA) — **dane NIE są aktualizowane**, a status
przyjmuje wartość `"anomaly_detected"` (wszystkie profile) lub `"partial_anomaly"` (część profili).

```json
{
  "status": "anomaly_detected",
  "timestamp": "2026-06-03T11:59:27Z",
  "timestamp_local": "2026-06-03 13:59:27",
  "duration_seconds": 219,
  "listings_total": 286,
  "listings_new": null,
  "listings_removed": null,
  "scan_number": 40,
  "profiles": [
    {
      "key": "mieszkania_lublin",
      "label": "Mieszkania na wynajem — Lublin",
      "listings_total": 286,
      "crosscheck": "anomaly_detected",
      "anomaly_reasons": ["spadek 52.6% vs poprzedni count=604"],
      "previous_good_count": 604
    }
  ],
  "error": "Scan odrzucony przez mechanizm anomalii (sanity check) — dane NIE zostały zaktualizowane",
  "error_detail": "[mieszkania_lublin] spadek 52.6% vs poprzedni count=604"
}
```

> Przy `anomaly_detected` / `partial_anomaly` poprzednie poprawne dane (`dashboard_data.json`)
> pozostają nienaruszone. Konsument API powinien traktować taki scan jako nieudany i nie podmieniać liczb.

#### Odpowiedź — niepełny scan (ostrzeżenie)

Gdy w **jednym scanie** zniknie nadmiernie duża część bazy (>25% — pole `missing_ratio`), to
prawie zawsze niepełny scrape OLX, a nie realny odpływ ofert. Taki ubytek bywa **poniżej** progu
anomalii (40% spadku total), bo „missing" ≠ „removed" (archiwizacja wymaga 2 nieobecności z rzędu).
Status przyjmuje wówczas wartość `"partial_scan"`, a w polu `warning` (oraz per-profil
`partial_scan_warning`) pojawia się opis. **Dane SĄ zapisane** (znalezione oferty są realne) —
to ostrzeżenie, nie odrzucenie: sygnalizuje ryzyko masowej archiwizacji przy drugim niepełnym scanie z rzędu.

```json
{
  "status": "partial_scan",
  "timestamp": "2026-06-15T13:21:23Z",
  "timestamp_local": "2026-06-15 13:21:23",
  "duration_seconds": 71,
  "listings_total": 429,
  "listings_new": 54,
  "listings_removed": 17,
  "scan_number": 55,
  "profiles": [
    {
      "key": "mieszkania_lublin",
      "label": "Mieszkania na wynajem — Lublin",
      "listings_total": 429,
      "listings_new": 54,
      "listings_removed": 17,
      "crosscheck": "passed",
      "partial_scan_warning": {
        "missing_this_scan": 217,
        "base_count": 593,
        "scanned_count": 429,
        "missing_ratio": 0.366,
        "message": "217 z 593 ofert (36.6%) zniknęło w jednym scanie — prawdopodobnie niepełny scrape OLX, nie realny odpływ"
      }
    }
  ],
  "error": null,
  "error_detail": null,
  "warning": "[mieszkania_lublin] 217 z 593 ofert (36.6%) zniknęło w jednym scanie — prawdopodobnie niepełny scrape OLX, nie realny odpływ"
}
```

#### Odpowiedź — oczekiwanie (przed pierwszym scanem)

```json
{
  "status": "pending",
  "timestamp": null,
  "listings_total": null,
  "scan_number": 0,
  "profiles": [],
  "error": null,
  "error_detail": null
}
```

---

### 2. Historia ostatnich 50 scanów

```
GET https://raw.githubusercontent.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/main/data/scan_history.json
```

#### Odpowiedź

```json
{
  "total_scans": 42,
  "scans": [
    {
      "timestamp": "2026-04-29T09:00:31Z",
      "timestamp_local": "2026-04-29 11:00:31",
      "status": "success",
      "duration_seconds": 52,
      "listings_total": 119,
      "listings_new": 5,
      "listings_removed": 2,
      "scan_number": 41,
      "profiles": [
        {
          "key": "mieszkania_lublin",
          "label": "Mieszkania na wynajem — Lublin",
          "listings_total": 119,
          "listings_new": 5,
          "listings_removed": 2,
          "crosscheck": "passed"
        }
      ],
      "error": null
    }
  ]
}
```

> Historia zawiera maksymalnie **50 ostatnich wpisów**, posortowanych rosnąco (najstarszy pierwszy).

---

### 3. Uproszczone API — `api.json`

```
GET https://raw.githubusercontent.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/main/data/api.json
```

Lekki endpoint dla aplikacji mobilnych/widżetów: łączna liczba ogłoszeń + **3 ostatnie udane scany**. Generowany automatycznie po każdym scanie (`main.py`).

#### Odpowiedź

```json
{
  "last_updated": "2026-05-31T09:48:51Z",
  "total_listings": 590,
  "scans": [
    { "date": "2026-05-31", "timestamp": "2026-05-31T09:48:51Z", "total_listings": 590, "added": 26, "removed": 32 },
    { "date": "2026-05-30", "timestamp": "2026-05-30T09:23:55Z", "total_listings": 585, "added": 10, "removed": 26 },
    { "date": "2026-05-29", "timestamp": "2026-05-29T18:35:46Z", "total_listings": 584, "added": 6,  "removed": 35 }
  ]
}
```

#### Opis pól

| Pole | Typ | Opis |
|------|-----|------|
| `last_updated` | string | Czas ostatniego scanu (UTC, ISO 8601). Równy `scans[0].timestamp`. |
| `total_listings` | int / null | Liczba aktywnych ogłoszeń po ostatnim scanie (profil `mieszkania_lublin`). |
| `scans` | array | Maks. **3 ostatnie udane** scany, od najnowszego (scany z błędem pomijane). |
| `scans[].date` | string | Data scanu `YYYY-MM-DD`. |
| `scans[].timestamp` | string | Dokładny czas scanu (UTC). |
| `scans[].total_listings` | int / null | Liczba ogłoszeń w momencie tego scanu. |
| `scans[].added` | int / null | Nowe ogłoszenia vs poprzedni scan (`null` przy pierwszym scanie w historii). |
| `scans[].removed` | int / null | Ogłoszenia, które zniknęły vs poprzedni scan (`null` przy pierwszym scanie). |
| `warning` | string | (opcjonalne) Obecne tylko gdy ostatni scan był niepełny (`partial_scan`) — opis masowego „missing". |

> Pełna dokumentacja tego endpointu również w `API_INFO.txt`. Dane dotyczą wyłącznie profilu **Mieszkania na wynajem — Lublin**.

---

## Opis pól

### Pola główne

| Pole | Typ | Opis |
|------|-----|------|
| `status` | string | `"success"` / `"partial_scan"` / `"error"` / `"anomaly_detected"` / `"partial_anomaly"` / `"pending"` |
| `timestamp` | string / null | Czas UTC w formacie ISO 8601 |
| `timestamp_local` | string / null | Czas lokalny (CET/CEST) |
| `duration_seconds` | int / null | Czas trwania scanu w sekundach |
| `scan_number` | int | Numer kolejny scanu (rośnie od 1) |
| `listings_total` | int / null | Łączna liczba ogłoszeń (suma profili) |
| `listings_new` | int / null | Łączna liczba nowych ogłoszeń |
| `listings_removed` | int / null | Łączna liczba usuniętych ogłoszeń |
| `profiles` | array | Szczegóły per profil (patrz niżej) |
| `error` | string / null | Krótki opis błędu (max 200 znaków). Przy anomalii: komunikat o odrzuceniu scanu przez sanity check |
| `error_detail` | string / null | Ostatnie 800 znaków traceback (tylko w `scan_status.json`). Przy anomalii: powody odrzucenia per profil |
| `warning` | string / null | Ostrzeżenie o niepełnym scanie (status `partial_scan`). `null` gdy brak. Dane są zapisane — to nie błąd |

### Pola obiektu `profiles[]`

| Pole | Typ | Opis |
|------|-----|------|
| `key` | string | Identyfikator profilu, np. `"mieszkania_lublin"` |
| `label` | string | Czytelna nazwa profilu |
| `listings_total` | int / null | Liczba ogłoszeń w tym profilu |
| `listings_new` | int / null | Nowe ogłoszenia w tym profilu (null przy pierwszym scanie) |
| `listings_removed` | int / null | Usunięte ogłoszenia w tym profilu (null przy pierwszym scanie) |
| `crosscheck` | string / null | Wynik weryfikacji: `"passed"`, `"passed_retry"`, `"consistent"`, `"best_of_two"`, `"anomaly_detected"`, `"error"` |
| `anomaly_reasons` | array | (tylko przy anomalii) Lista powodów odrzucenia scanu przez sanity check |
| `previous_good_count` | int / null | (tylko przy anomalii) Liczba ogłoszeń z ostatniego udanego scanu — punkt odniesienia |
| `partial_scan_warning` | object | (tylko przy niepełnym scanie) `{missing_this_scan, base_count, scanned_count, missing_ratio, message}` — masowy „missing" w jednym scanie |

> `listings_new` i `listings_removed` są liczone na podstawie porównania **ID ogłoszeń** (nie różnicy liczb),
> więc są dokładne nawet gdy OLX zmienia kolejność wyników.

---

## Polling — zalecenia

- **Częstotliwość**: co 15–30 minut — dane zmieniają się raz dziennie o ~9:00 CET
- **Cache busting**: dodaj `?t=<unix_timestamp>` do URL żeby uniknąć cache
- **Wykrywanie nowego scanu**: porównuj pole `scan_number` lub `timestamp`

```
https://raw.githubusercontent.com/.../scan_status.json?t=1746000000
```

---

## Harmonogram scanów

| Scan | Czas (CET) | Workflow |
|------|-----------|---------|
| Codzienny | 9:00 | `scan.yml` |
| Ręczny | dowolny | GitHub Actions → workflow_dispatch |

---

## Dodatkowe dane (dashboard webowy)

Pełne dane ogłoszeń:
```
GET https://raw.githubusercontent.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/main/data/dashboard_data.json
```
> Plik może ważyć kilkaset KB — **nie używać w aplikacji mobilnej przy każdym pollingu**.

---

*Dokumentacja wygenerowana automatycznie — SZPERACZ MIESZKANIOWY © 2026*
