# SZPERACZ MIESZKANIOWY — Dokumentacja systemu

> Kompletny przewodnik po architekturze, logice i implementacji systemu monitorowania ogłoszeń.
> Ten dokument służy jako punkt startowy do tworzenia nowych instancji projektu.

---

## 1. Cel projektu

System autonomicznie monitoruje ogłoszenia nieruchomości (mieszkań/pokoi) na OLX, śledzi zmiany cen, archiwizuje znikające ogłoszenia, generuje raporty i prezentuje dane na dashboardzie w GitHub Pages.

**Link do monitorowania:** _(uzupełnij dla nowego projektu)_
```
https://www.olx.pl/nieruchomosci/mieszkania/wynajem/lublin/
```

---

## 2. Architektura systemu

```
GitHub Actions (scheduler)
        │
        ▼
    main.py  ──── scraper.py ──► OLX (HTTP requests + BeautifulSoup)
        │
        ├──► data/szperacz_olx.xlsx     (historia Excel)
        ├──► data/dashboard_data.json   (dane dla dashboardu)
        │
        ▼
    GitHub Pages ──► docs/index.html   (dashboard interaktywny)
        │
        ▼
    email_report.py ──► Gmail SMTP ──► malczarski@gmail.com
```

### Kluczowe pliki

| Plik | Rola |
|------|------|
| `scraper.py` | Scraping OLX, parsowanie, zapis do Excel i JSON |
| `email_report.py` | Tygodniowy raport HTML via Gmail SMTP |
| `main.py` | Punkt wejścia (uruchamia scraper) |
| `docs/index.html` | Dashboard (GitHub Pages, czysty HTML+JS) |
| `data/dashboard_data.json` | Dane dla dashboardu (commitowane do repo) |
| `data/szperacz_olx.xlsx` | Pełna historia w Excelu |
| `.github/workflows/scan.yml` | Codzienny scan (GitHub Actions) |
| `.github/workflows/weekly_report.yml` | Tygodniowy email (GitHub Actions) |

---

## 3. Scraping — logika

### 3.1 Rodzaje profili

System obsługuje dwa typy źródeł:

**a) Strony kategorii** (`is_category: True`)
- Przykład: `https://www.olx.pl/nieruchomosci/mieszkania/wynajem/lublin/`
- Renderowane server-side, parsowane przez BeautifulSoup
- Paginacja przez `[data-testid="pagination-forward"]`
- Nagłówek z liczbą wyników: `Znaleźliśmy X ogłoszeń`

**b) Profile użytkowników** (`is_category: False`)
- Przykład: `https://www.olx.pl/oferty/uzytkownik/XXXXX/`
- Paginacja przez SVG-ikony z `href="?page=N"`

### 3.2 Parsowanie karty ogłoszenia

Każda karta (`[data-cy="l-card"]`) zawiera:
- **Tytuł**: link `<a href*="/d/oferta/">` — pierwszy z niepustym tekstem (>3 znaki)
- **Cena**: element `[data-testid="ad-price"]`
- **Data**: text zawierający słowa kluczowe (odświeżono, dzisiaj, wczoraj, nazwa miesiąca)
- **Lokalizacja**: tekst przed ` - ` w elemencie z datą
- **URL**: href linka do ogłoszenia → zawsze `https://www.olx.pl` + href
- **ID ogłoszenia**: z URL via regex `ID([a-zA-Z0-9]+)\.html`

```python
# WAŻNE: Każda karta ma WIELE linków <a href*="/d/oferta/">
# Pierwszy link owijA obraz (pusty tekst), drugi ma tytuł
# Zawsze iteruj wszystkie linki, nie break na pierwszym
for link in card.select('a[href*="/d/oferta/"]'):
    txt = link.get_text(strip=True)
    if txt and len(txt) > 3:
        title = txt
        href = link.get("href", "")
        break
    elif not href:
        href = link.get("href", "")
```

### 3.3 Parsowanie dat

OLX używa polskich nazw miesięcy i skrótów:
- `"Dzisiaj o 12:34"` → published = today, refreshed = today
- `"Odświeżono dnia 15 marca 2026"` → refreshed = "2026-03-15"
- `"12 marca 2026"` → published = "2026-03-15"
- `"Wczoraj o 10:00"` → published = yesterday

### 3.4 Crosscheck — weryfikacja wyników

Aby unikać fałszywych danych (OLX często zwraca niekompletne odpowiedzi):

1. Wykonaj scan 1
2. Porównaj `scraped_count` z `header_count` (liczba z nagłówka strony)
3. Tolerancja dla kategorii: ±10 ogłoszeń (różne promocje mogą być niewidoczne)
4. Jeśli mismatch → scan 2 z nową sesją HTTP
5. Zwróć wynik bliższy nagłówkowi, lub spójny (c1==c2)

### 3.5 Nagłówki HTTP

**KRYTYCZNE**: OLX zwraca ~10% odpowiedź przy niektórych nagłówkach:
```python
# NIGDY nie dodawaj tych nagłówków:
# "Accept-Encoding": "gzip"  ← strips response
# "DNT": "1"                 ← triggers bot detection
# "Cache-Control": "..."     ← strips response  
# "Referer": "..."           ← strips response

# Minimalne, działające nagłówki:
headers = {
    "User-Agent": random.choice(USER_AGENTS),
    "Accept": "text/html,application/xhtml+xml,...",
    "Accept-Language": "pl-PL,pl;q=0.9,...",
    "Accept-Encoding": "gzip, deflate, br",  # To jest OK
    "Connection": "keep-alive",
}
```

---

## 4. Przechowywanie danych

### 4.1 dashboard_data.json — struktura

```json
{
  "last_scan": "2026-04-29 09:00:00",
  "profiles": {
    "nazwa_profilu": {
      "label": "Czytelna nazwa",
      "url": "https://...",
      "is_category": true,
      "daily_counts": [
        {
          "date": "2026-04-29",
          "count": 142,
          "change": +5,
          "timestamp": "2026-04-29 09:00:00",
          "median_price": 2500
        }
      ],
      "current_listings": [...],
      "archived_listings": [...],
      "price_history": {
        "listing_id": [
          {"date": "...", "old_price": 2000, "new_price": 2200, "change": 200}
        ]
      }
    }
  },
  "scan_history": [...]
}
```

**Ważna zasada dla `median_price`**: to mediana cen ogłoszeń, których `first_seen` = data danego wpisu daily_counts (nowe ogłoszenia tego dnia). `None` oznacza brak nowych ogłoszeń — to prawidłowe zachowanie.

### 4.2 Śledzenie ogłoszeń

- **Nowe ogłoszenie**: pojawia się w wynikach → dodawane do `current_listings`
- **Istniejące**: aktualizowany `last_seen`, śledzona zmiana ceny
- **Znikające**: przenoszane do `archived_listings` z `archived_date`
- **Powracające** (reactivation): ogłoszenie z `archived_listings` pojawia się ponownie → `reactivation_history[]`
- **Odświeżone** (refresh): zmiana daty `refreshed` przy tej samej cenie → `refresh_history[]`

### 4.3 Excel — struktura arkuszy

| Arkusz | Zawartość |
|--------|-----------|
| `nazwa_profilu` | Każdy scan: liczba ogłoszeń, zmiana, lista tytułów z cenami |
| `historia_cen` | Każda zmiana ceny: stara/nowa/delta |
| `podsumowanie` | Ostatni stan każdego profilu |

Kolumny w arkuszu profilu:
1. Data scanu, 2. Godzina, 3. Liczba ogłoszeń, 4. Zmiana vs poprzedni,
5. Crosscheck, 6. Tytuł, 7. Cena (zł), 8. Zmiana ceny,
9. Data publikacji, 10. Data odświeżenia, 11. URL, 12. ID ogłoszenia,
13. Liczba reaktywacji, 14. Liczba odświeżeń (Liczba odświeżeń @ col 15 w wersji z promoted)

---

## 5. Dashboard (docs/index.html)

Czysty HTML + CSS + JavaScript (zero zależności, działa offline jako statyczny plik).

### 5.1 Ładowanie danych

```javascript
const DATA_URL = `https://raw.githubusercontent.com/OWNER/REPO/main/data/dashboard_data.json`;
// Cache-bust: ?t=Date.now()
// Auto-refresh co 5 minut
```

### 5.2 Komponenty

- **Topbar**: logo, przycisk "Scan teraz", toggle motywu
- **Scan info bar**: ostatni scan, następny scan, countdown
- **Profile cards**: kafelki z licznikiem ogłoszeń i badge zmiana
- **Detail panel**: statystyki, wykres słupkowy, tabela ogłoszeń (aktualne/archiwum)

### 5.3 Wykres słupkowy

- Domyślnie 14 ostatnich dni (toggle 7/14/30)
- Adaptywna szerokość słupków
- Skalowanie osi Y od minimum wartości (nie od 0)
- Animowane SVG favicon (pulsujące kółko)

### 5.4 Tabela ogłoszeń

- Sortowalne kolumny (klik w nagłówek)
- Zakładki: Aktualne / Archiwum
- Badge: zmiana ceny (góra/dół)
- Link do ogłoszenia OLX

### 5.5 Scan z dashboardu

Przycisk "Scan teraz" → modal z PAT GitHub → `POST /repos/.../actions/workflows/scan.yml/dispatches`
- Wymaga PAT z uprawnieniem `workflow` lub `repo`
- HTTP 204 = sukces, auto-refresh po 3 minutach

---

## 6. Email tygodniowy

Plik: `email_report.py`
SMTP: `smtp.gmail.com:587` (STARTTLS)
Nadawca: `slowholidays00@gmail.com`
Odbiorca: `malczarski@gmail.com`
Hasło: z `os.environ["EMAIL_PASSWORD"]` (GitHub Secret)

### 6.1 Zawartość raportu HTML

- Grid statystyk (liczba ogłoszeń, zmiany, min/max cena)
- Top-10 ogłoszeń (sortowane po `first_seen`)
- Tabela zmian cen z ostatniego tygodnia
- Wykresy matplotlib → Base64 → inline w HTML

### 6.2 Format HTML

Używa **table-based layout** (nie CSS Grid) — wymóg kompatybilności z klientami email.

---

## 7. GitHub Actions — workflows

### scan.yml (codzienny)
```yaml
schedule: '0 7 * * *'   # 09:00 CET (7:00 UTC w lecie)
permissions: contents: write
timeout-minutes: 30
```
Kroki: checkout → setup Python → install deps → `python main.py --scan` → git commit & push

### weekly_report.yml (tygodniowy)
```yaml
schedule: '30 7 * * 1'  # Poniedziałek 09:30 CET
permissions: contents: read
timeout-minutes: 5
```
Kroki: checkout → setup Python → install deps → `python email_report.py`

### failsafe.yml (opcjonalny)
Sprawdza o 11:00 UTC czy scan z danego dnia już był. Jeśli nie — uruchamia backup scan.

### keepalive.yml (opcjonalny)
Zapobiega wyłączeniu scheduled workflows przez GitHub po 60 dniach bezczynności.

---

## 8. Konfiguracja nowego projektu

### 8.1 GitHub Secrets (Settings → Secrets → Actions)
- `EMAIL_PASSWORD` — App Password Gmail (nie hasło konta!)

### 8.2 GitHub Pages (Settings → Pages)
- Source: `Deploy from branch`
- Branch: `main`, folder: `/docs`

### 8.3 Zmienne do dostosowania w scraper.py

```python
PROFILES = {
    "nazwa_klucza": {
        "url": "WSTAW_URL_DO_MONITOROWANIA",  # ← tu wklej link OLX
        "label": "Czytelna nazwa dla dashboardu",
        "is_category": True,  # True = strona kategorii OLX
    },
}
```

### 8.4 Zmienne w email_report.py

```python
SENDER_EMAIL = "twoj-sender@gmail.com"
RECEIVER_EMAIL = "twoj-odbiorca@gmail.com"
```

### 8.5 Zmienne w docs/index.html

```javascript
const GITHUB_OWNER = 'TwojNazwaUzytkownika';
const GITHUB_REPO = 'NazwaRepo';
```

---

## 9. Wzorce i pułapki

### openpyxl
- `Font(color="inherit")` → BŁĄD; używaj hex lub pomiń parametr
- Gdy `get_or_create_sheet()` zwraca istniejący arkusz, nagłówki NIE są automatycznie aktualizowane
- `update_excel()` musi być wywołany PO `generate_dashboard_json()` (nie przed)

### Synchronizacja liczników
- `refresh_count` musi być zawsze równy `len(refresh_history)`
- `reactivation_count` musi być zawsze równy `len(reactivation_history)`

### Git w Actions
```bash
git config user.name "Bot Name"
git config user.email "bot@users.noreply.github.com"
git add data/
git diff --cached --quiet || git commit -m "🔍 Scan: $(date)"
git push
```

### Ochrona danych
Jeśli scan zwraca 0 wyników → NIE archiwizuj ogłoszeń (to błąd scrapingu, nie prawdziwy stan).

---

## 10. Changelog i dokumentacja

- `CHANGELOG.md` — Keep a Changelog, emoji prefixes: 📧 Email, 🐛 Fix, ✨ Feature, 📊 Chart
- `README.md` — opis projektu, instrukcja setup
- Każda zmiana kodu → aktualizacja obu plików

---

*Wygenerowano automatycznie jako szablon dla nowych instancji SZPERACZ.*
