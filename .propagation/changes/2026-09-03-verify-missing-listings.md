---
id:          2026-09-03-verify-missing-listings
repo:        Bonaventura-EW/SZPERACZ-MIESZKANIOWY
family:      szperacze
date:        2026-09-03
category:    bugfix
what:        Oferty nieobecne w przeglądzie listingu sprawdzamy bezpośrednio po ich URL-u, zamiast wnioskować z nieobecności, że zniknęły — plus równoległa paginacja i stabilne sortowanie, żeby sweep gubił ich mniej.
why:         Licznik aktywnych ofert był systematycznie zaniżony o ~5–6%, a 20% archiwizacji było fałszywych (609 z 3038 w 90 dniach — oferta wracała, choć nigdy nie zniknęła z serwisu). Źródłem jest paginacja offsetowa po liście, którą serwis przetasowuje w trakcie sweepu.
how:         (1) Po sweepie oferty z bazy, których w nim nie było, są odpytywane pojedynczo swoim URL-em; `classify_offer_page()` zwraca alive/dead/unknown, przy czym do `dead` schodzimy WYŁĄCZNIE na jednoznaczny sygnał (404/410, fraza wygaszonego ogłoszenia, przekierowanie poza ścieżkę oferty) — wszystko inne to `unknown` i stara heurystyka 2-scan. Weryfikacja jest pomijana, gdy zaginionych jest podejrzanie dużo (wtedy zepsuty jest sweep, nie oferty), a bezpiecznik czasowy archiwizuje ofertę trzymaną przy życiu wyłącznie weryfikacją. (2) Strona 1 sekwencyjnie, strony 2..N równolegle (4 wątki, sesja per wątek) + wymuszone sortowanie po dacie — okno na przesunięcie listy spada z ~2 min do ~20 s. (3) Nowa metryka `active_count` obok niezmienionego `count`; sanity check dostał warunki kompletności paginacji zamiast progu czasu trwania.
surface:     scraper.py, main.py, docs/index.html, docs/trend.html, tests/test_scraper.py, API.md
generality:  family
propagate:   yes
commit:      15ae8e8
---

# Kontekst dla brata-ewaluatora

**Diagnoza przed zmianą — warto powtórzyć u siebie.** Sygnał, który wskazał problem,
siedzi w danych, nie w kodzie: udział reaktywacji w archiwizacjach (`reactivated_count`
vs `removed` w `daily_counts`). U nas było to 20% — czyli co piąta archiwizacja była
fałszywa. Jeśli u brata ten wskaźnik jest podobny, ma ten sam błąd. Drugi objaw:
dashboard pokazujący w dwóch miejscach dwie różne liczby aktywnych (u nas 797 vs 881).

**Co jest przenośne bez zmian:** klasyfikacja strony oferty (alive/dead/unknown) wraz
z zasadą „blokada ≠ martwa oferta" — to jest sedno i to działa w każdym serwisie
ogłoszeniowym, w którym oferta ma własny URL. Tak samo warunki kompletności paginacji
w sanity checku.

**Co wymaga kalibracji u siebie:**
- `DEAD_PAGE_MARKERS` / `ALIVE_PAGE_MARKERS` to frazy i atrybuty konkretnego serwisu —
  przy innym źródle trzeba je zmierzyć na żywo, nie przepisać.
- Parametr stabilnego sortowania (`search[order]=created_at:desc`) jest specyficzny dla OLX.
- `PAGE_WORKERS = 4` to kompromis: wyżej nie wchodziliśmy, bo seria równoległych żądań
  to dokładnie ten wzorzec, na który reagują WAF-y. Jeśli brat ma inne źródło lub
  ostrzejsze limity, to jest pierwsza liczba do obniżenia.
- Jeżeli sweep u brata trwa krótko (mało stron), zrównoleglenie da mało — sama
  weryfikacja po URL-u daje wtedy prawie cały zysk i jest wyraźnie mniej ryzykowna.

**Czego świadomie NIE zrobiliśmy:** nie zmieniliśmy semantyki `listings_total` /
`total_listings` w publicznym API — nowa liczba weszła jako osobne pole
(`listings_active` / `active_listings`). Podmiana znaczenia istniejącego pola
po cichu zepsułaby konsumentów.

**Pułapka przy wdrożeniu:** przy zrównolegleniu trzeba jednocześnie ruszyć próg
„scan trwał za krótko" w sanity checku — inaczej każdy szybki (czyli poprawny)
scan zacznie być odrzucany jako anomalia.
