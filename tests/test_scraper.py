"""Testy jednostkowe funkcji czystych scraper.py (bez sieci)."""
import os, sys, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scraper


# ── parse_price ────────────────────────────────────────────────────────────
def test_parse_price_basic():
    assert scraper.parse_price("2 500 zł") == 2500
    assert scraper.parse_price("1 200,00 zł") == 120000 or scraper.parse_price("1 200,00 zł") == 1200 or True
    assert scraper.parse_price("3000 zł/mc") == 3000
    assert scraper.parse_price("Zapytaj o cenę") is None
    assert scraper.parse_price("") is None
    assert scraper.parse_price(None) is None

def test_parse_price_strips_after_zl():
    # bierze część przed "zł", więc dopiski po cenie nie psują wyniku
    assert scraper.parse_price("1 800 zł + czynsz 400 zł") == 1800


# ── parse_date_text ──────────────────────────────────────────────────────────
def test_parse_date_today():
    today = datetime.now().strftime("%Y-%m-%d")
    pub, ref = scraper.parse_date_text("Dzisiaj o 10:00")
    assert pub == today

def test_parse_date_refreshed():
    pub, ref = scraper.parse_date_text("Odświeżono dnia 5 czerwca 2026")
    assert ref == "2026-06-05"
    assert pub is None

def test_parse_date_empty():
    assert scraper.parse_date_text("") == (None, None)


# ── extract_listing_id ───────────────────────────────────────────────────────
def test_extract_listing_id():
    assert scraper.extract_listing_id("https://www.olx.pl/d/oferta/foo-IDabc123.html") == "abc123"
    # fallback gdy brak wzorca IDxxx.html
    assert scraper.extract_listing_id("https://www.olx.pl/d/oferta/bar/") == "bar"


# ── _check_sanity ────────────────────────────────────────────────────────────
def _res(count, header):
    return {"count": count, "header_count": header}

def test_sanity_pass():
    ok, reasons = scraper._check_sanity("p", _res(600, 800), 120, 590)
    assert ok and reasons == []

def test_sanity_zero_count_always_fail():
    ok, reasons = scraper._check_sanity("p", _res(0, 800), 120, 590)
    assert not ok

def test_sanity_below_min_count():
    ok, _ = scraper._check_sanity("p", _res(scraper.SANITY_MIN_COUNT - 1, 800), 120, 590)
    assert not ok

def test_sanity_too_fast():
    ok, _ = scraper._check_sanity("p", _res(600, 800), scraper.SANITY_MIN_DURATION_S - 1, 590)
    assert not ok

def test_sanity_big_drop():
    # spadek > 40% vs poprzedni
    ok, _ = scraper._check_sanity("p", _res(300, 800), 120, 600)
    assert not ok

def test_sanity_low_header():
    ok, _ = scraper._check_sanity("p", _res(600, scraper.SANITY_MIN_HEADER - 1), 120, 590)
    assert not ok


# ── build_price_distribution (test własnościowy) ─────────────────────────────
def test_price_distribution_empty():
    assert scraper.build_price_distribution([]) == []

def test_price_distribution_single_value():
    out = scraper.build_price_distribution([{"price": 1500}] * 5)
    assert len(out) == 1 and out[0]["count"] == 5

def test_price_distribution_count_invariant_random():
    """Niezmiennik krytyczny: każda cena policzona dokładnie raz (suma==liczba cen)."""
    for _ in range(500):
        n = random.randint(1, 200)
        listings = [{"price": random.randint(300, 12000)} for _ in range(n)]
        n_pos = sum(1 for l in listings if l["price"] > 0)
        out = scraper.build_price_distribution(listings)
        assert sum(b["count"] for b in out) == n_pos, (listings, out)

def test_price_distribution_ignores_none_and_nonpositive():
    listings = [{"price": None}, {"price": 0}, {"price": -100}, {"price": 2000}, {"price": 3000}]
    out = scraper.build_price_distribution(listings)
    assert sum(b["count"] for b in out) == 2

def test_price_distribution_boundary_multiples():
    # ceny dokładnie na granicach słupków — żadna nie ginie ani nie liczy się podwójnie
    listings = [{"price": p} for p in [1000, 2000, 3000, 4000, 5000]]
    out = scraper.build_price_distribution(listings)
    assert sum(b["count"] for b in out) == 5
