# Changelog — SZPERACZ MIESZKANIOWY

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/)

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
