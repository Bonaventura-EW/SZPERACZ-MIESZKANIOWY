# Changelog — SZPERACZ MIESZKANIOWY

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/)

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
