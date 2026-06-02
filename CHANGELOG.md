# Changelog — SZPERACZ MIESZKANIOWY

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/)

## [1.5.1] — 2026-06-02

### 🐛 Fix: „Znikło" (API + dashboard) liczone z potwierdzonych usunięć
- `flow_removed` w `generate_dashboard_json()` liczył wcześniej KAŻDĄ pojedynczą nieobecność oferty w danym scanie (`old_ids - current_ids_new`), co przy niekompletnych wynikach OLX (mix Otodom) zawyżało wartość do kilkudziesięciu (np. 58, 75) mimo że realnie znikało 1–9 ofert.
- Teraz `flow_removed` liczy wyłącznie oferty **potwierdzone jako usunięte** — te, które przechodzą do `archived_listings` w tym scanie (drugą nieobecność z rzędu, `missing_count >= 2`). To samo kryterium co mechanizm archiwizacji 2-scan.
- Wpływa na: `listings_removed` w `scan_status.json` / `scan_history.json` (kolumna „Znikło" w API) oraz pole `removed` w `daily_counts` (wykres „Przybyło/Zniknęło" i kafelek „Zniknęło" na dashboardzie). `added` bez zmian (nowa oferta jest realnie nowa od razu).

## [1.5.0] — 2026-06-01

### 📊 Dashboard: Historia ceny pojedynczej oferty (sparkline + modal)
- Nowa kolumna **📈 Cena** w tabeli ofert — mini-sparkline (SVG) pokazujący trajektorię ceny dla każdej oferty z `price_history`; zielony punkt = spadek, czerwony = wzrost. Oferty bez zmian ceny: „—".
- Klik w sparkline otwiera **modal z wykresem (Chart.js, linia + markery)**: etykiety delt nad punktami (własny inline-plugin, bez dodatkowych zależności), tooltipy (cena + Δ), badge sumaryczny „▼ −X zł (−Y%) od publikacji" i kafelki (start / teraz / liczba zmian / mediana zmiany).
- Reużyto istniejącą infrastrukturę modala (zwolnioną po usunięciu modala scanu). Zweryfikowano runtime w jsdom (render tabeli, otwarcie/zamknięcie modala, plugin delt — bez wyjątków).

### 🛡️ Dashboard: Self-host bibliotek + usunięcie przycisku scanu
- Biblioteki Chart.js, hammer.js i chartjs-plugin-zoom przeniesione z zewnętrznego CDN do `docs/vendor/` — dashboard nie zależy już od cdnjs (wykresy działają nawet gdy CDN padnie). Pliki same-origin, więc SRI zbędne.
- Usunięto przycisk „Scan teraz" wraz z modalem PAT — token GitHub (scope `repo`) nie jest już wpisywany ani przechowywany w `localStorage` przeglądarki (eliminacja ryzyka wycieku). Scan i tak działa automatycznie codziennie (`scan.yml`) + failsafe.

## [1.4.0] — 2026-06-01

### 🛡️ Refactor/Test: Testy jednostkowe + uproszczenie histogramu cen
- `build_price_distribution()` wyciągnięta z `generate_dashboard_json()` na poziom modułu (testowalna).
- Usunięto martwy blok „last price edge case" — dowiedziono, że po pętli `s > mx`, więc dodawał zawsze `0`. Test własnościowy (500 losowych zestawów) potwierdza niezmiennik: suma liczników słupków == liczba ofert z ceną.
- Dodano `tests/test_scraper.py` (17 testów, bez sieci): `parse_price`, `parse_date_text`, `extract_listing_id`, `_check_sanity` (wszystkie 5 zapór), `build_price_distribution`.

### ⚙️ Workflow/Config: Hardening
- Ujednolicono wersję Pythona we wszystkich workflowach na **3.12** (`weekly_report.yml` używał 3.11).
- `scan.yml`: doprecyzowano komentarz cron — `07:00 UTC` = 9:00 latem (CEST) / 8:00 zimą (CET); pominięty scan łapie `failsafe.yml`.
- Rozszerzono `.gitignore` (`.venv`, `.pytest_cache`, `*.pyc`, pliki tymczasowe Excela `~$*.xlsx` itd.).
- `requirements.txt`: komentarz wyjaśniający rolę `brotli` (dekodowanie `br`).

## [1.3.0] — 2026-06-01

### 🛡️ Fix: Zatrzymanie niekontrolowanego wzrostu plików danych (Excel/JSON)
- `update_excel()` przebudowany: arkusz profilu trzyma teraz **pełną serię liczników** (1 wiersz/scan, limit `MAX_SUMMARY_ROWS = 365`) oraz **snapshot bieżących ogłoszeń przebudowywany co scan** zamiast kumulowania ~600 wierszy przy każdym uruchomieniu.
- Arkusz `historia_cen` odbudowywany z `price_history` (JSON = źródło prawdy) — rejestruje wyłącznie realne zmiany ceny, nie powiela wszystkich ofert co scan.
- Skutek: rozmiar Excela spadł z **4,06 MB → 95 KB**; przy symulacji 20 scanów arkusze są stabilne (~634 / 237 wierszy zamiast >12 000).
- `generate_dashboard_json()`: dodano **trymowanie `price_history` do 90 dni** (analogicznie do `daily_counts` i `scan_history`).
- Jednorazowa regeneracja `data/szperacz_mieszkaniowy.xlsx` — odchudzenie istniejącego pliku; `dashboard_data.json` nietknięty.

### 🐛 Fix: Usunięcie martwej struktury `promotion_history` (top-level) — przeciek pamięci
- Pole `pd_["promotion_history"]` na poziomie profilu tworzyło pustą listę dla każdego ID ogłoszenia, ale **nigdy do niej nie zapisywało** (realna historia promocji żyje w `nl["promotion_history"]` per-ogłoszenie). Rosło bez końca (1206 pustych kluczy).
- Usunięto inicjalizację, blok backward-compat i zapis pustych list w `generate_dashboard_json()`. Historia promocji per-ogłoszenie pozostaje nietknięta.
- Migracja danych: wyczyszczono 1206 pustych kluczy z `data/dashboard_data.json` (niepuste klucze byłyby zachowane — żadnych nie było).

### 📝 Docs/Tooling: Spójność wejścia i dokumentacji
- `main.py`: dodano `argparse` z flagą `--scan` (dotąd flaga była po cichu ignorowana). Nieznane argumenty zwracają teraz czytelny błąd, `--help` działa. Wywołanie bez argumentów nadal skanuje (kompatybilność wsteczna z workflow).
- `JAK_DZIALA_SYSTEM.md`: poprawiono nieaktualną nazwę pliku Excela `szperacz_olx.xlsx` → `szperacz_mieszkaniowy.xlsx`.
- `API.md`: dodano sekcję dokumentującą endpoint `data/api.json` (dotąd opisany tylko w `API_INFO.txt`).

## [1.2.0] — 2026-05-29

### ✨ Feature: Nowy uproszczony endpoint API — data/api.json
- Dodano generowanie `data/api.json` po każdym scanie (w `main.py`).
- Plik zawiera: łączną liczbę ogłoszeń (`total_listings`) oraz 3 ostatnie udane scany z datą, liczbą ogłoszeń, przybyłymi i ubyłymi (`added`, `removed`).
- Scany posortowane od najnowszego; pola `added`/`removed` = null przy pierwszym scanie w historii.
- Dane dotyczą profilu `mieszkania_lublin` (Mieszkania na wynajem — Lublin).
- Dodano `API_INFO.txt` z pełną dokumentacją nowego endpointu.

## [1.1.0] — 2026-05-16

### 🐛 Fix: Paginacja ucinała ostatnie strony OLX
- `get_next_page_url()` zatrzymywała się gdy OLX usuwał `pagination-forward` na przedostatnich stronach (mimo że dalsze strony istniały).
- Dodano fallback: parsowanie wszystkich linków `?page=N` w paginacji i wykrywanie maksymalnego dostępnego numeru strony.
- Dodano ochronę przed zapętleniem — jeśli kolejna strona zwraca te same ID co poprzednia, paginacja kończy się.
- Skutek: scan z 16.05.2026 złapał tylko 17/20 stron i zgubił ~120 aktywnych ogłoszeń.

### 🛡️ Fix: Ochrona przed masową fałszywą archiwizacją
- Wprowadzono mechanizm „2 scany potwierdzenia" przed archiwizacją.
- Każde ogłoszenie nieznalezione w scanie zwiększa `missing_count`; archiwizacja następuje dopiero przy `missing_count >= 2` (dwie nieobecności z rzędu).
- Ogłoszenia z `missing_count == 1` pozostają w `current_listings`, gotowe do reaktywacji w następnym scanie.
- Dodano logi `[MISSING 1×]` i `[ARCHIVED]` dla obserwowalności.

### 🔄 Recovery
- Przywrócono 124 ogłoszenia z dnia 2026-05-16 błędnie wrzucone do archiwum.
- Zaktualizowano `daily_counts` i `scan_history` dla tego dnia.

## [1.0.0] — 2026-04-30

### ✨ Feature: Inicjalna implementacja
- Scraping kategorii mieszkań OLX Lublin (`wynajem/lublin/`)
- Crosscheck wyników (porównanie z nagłówkiem strony)
- Zapis danych do `dashboard_data.json` i Excel
- Ochrona danych: brak archiwizacji przy 0 wynikach
- Śledzenie zmian cen, historia archiwalna

### 📊 Chart: Dashboard żółto-niebieski
- Pojedynczy kafelek hero z licznikiem i statystykami
- Wykres słupkowy (7/14/30 dni) z adaptywną skalą Y
- Tabela ogłoszeń z sortowaniem kolumn
- Badge "NOWE" dla ogłoszeń z ostatnich 24h
- Motyw ciemny / jasny

### 📧 Email: Tygodniowy raport
- Podsumowanie profili z tabelą statystyk
- Top-50 ogłoszeń z cenami i zmianami
- Załącznik Excel

### ⚙️ Workflows
- `scan.yml` — codzienny scan o 9:00 CET
- `weekly_report.yml` — raport w poniedziałek 9:30
- `failsafe.yml` — backup scan o 11:00 UTC jeśli brak scanu
