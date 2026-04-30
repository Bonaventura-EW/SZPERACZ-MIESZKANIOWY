# 🏠 SZPERACZ MIESZKANIOWY

Autonomiczny agent monitorujący ogłoszenia mieszkań na wynajem w Lublinie (OLX).

[![Daily Scan](https://github.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/actions/workflows/scan.yml/badge.svg)](https://github.com/Bonaventura-EW/SZPERACZ-MIESZKANIOWY/actions/workflows/scan.yml)

## 🔗 Dashboard

**[→ Otwórz dashboard](https://bonaventura-ew.github.io/SZPERACZ-MIESZKANIOWY/)**

## 📋 Co monitoruje

| Źródło | URL |
|--------|-----|
| Mieszkania na wynajem — Lublin | [olx.pl/nieruchomosci/mieszkania/wynajem/lublin/](https://www.olx.pl/nieruchomosci/mieszkania/wynajem/lublin/) |

## ⚙️ Jak działa

1. **GitHub Actions** uruchamia scan codziennie o **9:00 CET**
2. **scraper.py** pobiera ogłoszenia z OLX (BeautifulSoup)
3. Dane trafiają do **data/dashboard_data.json** i **data/szperacz_mieszkaniowy.xlsx**
4. **GitHub Pages** serwuje dashboard z pliku `docs/index.html`
5. Tygodniowy raport emailowy wysyłany w **poniedziałek o 9:30**

## 🛠️ Setup

### 1. GitHub Secrets
Dodaj w `Settings → Secrets → Actions`:
- `EMAIL_PASSWORD` — App Password Gmail

### 2. GitHub Pages
`Settings → Pages → Source: Deploy from branch → main → /docs`

### 3. Ręczny scan
Kliknij **"Scan teraz"** na dashboardzie (wymaga GitHub PAT z uprawnieniem `workflow`).

## 📁 Struktura projektu

```
SZPERACZ-MIESZKANIOWY/
├── scraper.py              # Logika scrapingu OLX
├── email_report.py         # Tygodniowy raport email
├── main.py                 # Punkt wejścia
├── requirements.txt        # Zależności Python
├── JAK_DZIALA_SYSTEM.md    # Pełna dokumentacja systemu
├── data/
│   ├── dashboard_data.json # Dane dla dashboardu
│   └── szperacz_mieszkaniowy.xlsx
├── docs/
│   └── index.html          # Dashboard (GitHub Pages)
└── .github/workflows/
    ├── scan.yml            # Codzienny scan
    ├── weekly_report.yml   # Tygodniowy email
    └── failsafe.yml        # Backup scan o 11:00
```

## 📖 Dokumentacja

Pełna dokumentacja architektury i logiki systemu: **[JAK_DZIALA_SYSTEM.md](JAK_DZIALA_SYSTEM.md)**

---
*Projekt oparty na SZPERACZ OLX — zmodyfikowany dla rynku mieszkań.*
