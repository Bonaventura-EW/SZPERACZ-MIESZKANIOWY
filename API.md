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
  "crosscheck": "passed",
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
  "crosscheck": null,
  "error": "ConnectionTimeout: HTTPSConnectionPool(host='www.olx.pl'...",
  "error_detail": "Traceback (most recent call last):\n  File ...\nrequests.exceptions.ConnectTimeout: ..."
}
```

#### Odpowiedź — oczekiwanie (przed pierwszym scanem)

```json
{
  "status": "pending",
  "timestamp": null,
  "listings_total": null,
  "scan_number": 0,
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
      "crosscheck": "passed",
      "error": null
    },
    {
      "timestamp": "2026-04-30T09:00:47Z",
      "timestamp_local": "2026-04-30 11:00:47",
      "status": "error",
      "duration_seconds": 12,
      "listings_total": null,
      "listings_new": null,
      "listings_removed": null,
      "scan_number": 42,
      "crosscheck": null,
      "error": "ConnectionTimeout: ..."
    }
  ]
}
```

> Historia zawiera maksymalnie **50 ostatnich wpisów**, posortowanych rosnąco (najstarszy pierwszy).

---

## Opis pól

### Pola wspólne

| Pole | Typ | Opis |
|------|-----|------|
| `status` | string | `"success"` / `"error"` / `"pending"` |
| `timestamp` | string / null | Czas UTC w formacie ISO 8601 |
| `timestamp_local` | string / null | Czas lokalny (CET/CEST) |
| `duration_seconds` | int / null | Czas trwania scanu w sekundach |
| `scan_number` | int | Numer kolejny scanu (rośnie od 1) |

### Pola statusu

| Pole | Typ | Opis |
|------|-----|------|
| `listings_total` | int / null | Liczba ogłoszeń po scanie |
| `listings_new` | int / null | Nowe ogłoszenia względem poprzedniego scanu |
| `listings_removed` | int / null | Usunięte ogłoszenia względem poprzedniego scanu |
| `crosscheck` | string / null | Wynik weryfikacji: `"passed"`, `"passed_retry"`, `"consistent"`, `"error"` |
| `error` | string / null | Krótki opis błędu (max 200 znaków) |
| `error_detail` | string / null | Ostatnie 800 znaków traceback (tylko w `scan_status.json`) |

---

## Polling — zalecenia

- **Częstotliwość**: co 15–30 minut — dane zmieniają się raz dziennie o ~9:00 CET
- **Cache busting**: dodaj `?t=<timestamp>` do URL żeby uniknąć cache przeglądarki
- **Wykrywanie nowego scanu**: porównuj pole `scan_number` lub `timestamp`

```
https://raw.githubusercontent.com/.../scan_status.json?t=1746000000
```

---

## Harmonogram scanów

| Scan | Czas (CET) | Workflow |
|------|-----------|---------|
| Codzienny | 9:00 | `scan.yml` |
| Backup | 11:00 | `failsafe.yml` |
| Ręczny | dowolny | przycisk "Scan teraz" w dashboardzie |

---

## Dodatkowe dane (dashboard)

Pełne dane ogłoszeń (dla dashboardu webowego):
```
GET https://raw.githubusercontent.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/main/data/dashboard_data.json
```
> Plik może ważyć kilkaset KB — **nie używać w aplikacji mobilnej przy każdym pollingu**.

---

*Dokumentacja wygenerowana automatycznie — SZPERACZ MIESZKANIOWY © 2026*
