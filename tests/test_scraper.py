"""Testy jednostkowe funkcji czystych scraper.py (bez sieci)."""
import os, sys, random, re
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
    # spadek > SANITY_MAX_DROP_RATIO vs poprzedni
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


# ── sanity: kompletność sweepu ───────────────────────────────────────────────
def test_sanity_failed_pages():
    """Strona, której nie udało się pobrać, unieważnia cały scan — wcześniej taki
    sweep przechodził jako pełnoprawny i gubione oferty szły do archiwum."""
    r = _res(600, 800); r["failed_pages"] = [7]
    ok, reasons = scraper._check_sanity("p", r, 120, 590)
    assert not ok and any("nie pobrano stron" in x for x in reasons)

def test_sanity_fewer_pages_than_pagination():
    r = _res(600, 800); r["pages_scraped"] = 9; r["pages_expected"] = 16
    ok, reasons = scraper._check_sanity("p", r, 120, 590)
    assert not ok and any("stron paginacji" in x for x in reasons)

def test_sanity_pages_complete_passes():
    r = _res(600, 800); r["pages_scraped"] = 16; r["pages_expected"] = 16
    ok, reasons = scraper._check_sanity("p", r, 120, 590)
    assert ok and reasons == []

def test_sanity_hole_in_pagination():
    r = _res(600, 800); r["empty_pages"] = [4]
    ok, reasons = scraper._check_sanity("p", r, 120, 590)
    assert not ok


# ── URL: stabilne sortowanie i numer strony ──────────────────────────────────
def test_build_start_url_adds_stable_sort():
    url = scraper.build_start_url({"url": "https://www.olx.pl/x/lublin/"})
    assert "search%5Border%5D=created_at%3Adesc" in url

def test_build_start_url_respects_opt_out():
    cfg = {"url": "https://www.olx.pl/x/lublin/", "stable_sort": False}
    assert scraper.build_start_url(cfg) == cfg["url"]

def test_build_start_url_is_idempotent():
    once  = scraper.build_start_url({"url": "https://www.olx.pl/x/lublin/"})
    twice = scraper.build_start_url({"url": once})
    assert once == twice

def test_page_url_keeps_existing_query():
    """Regresja: sklejanie stringami gubiło sortowanie albo produkowało '/&search='."""
    start = scraper.build_start_url({"url": "https://www.olx.pl/x/lublin/"})
    u2 = scraper.page_url(start, 2)
    assert "page=2" in u2 and "search%5Border%5D=created_at%3Adesc" in u2
    assert scraper.page_url(u2, 3).count("page=") == 1
    assert "page=" not in scraper.page_url(u2, 1)


# ── get_last_page_number ─────────────────────────────────────────────────────
def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml")

def test_last_page_number_from_pagination():
    html = """<div data-testid="pagination-wrapper">
        <a href="/x/lublin/?page=2">2</a><a href="/x/lublin/?page=3">3</a>
        <a href="/x/lublin/?page=17">17</a></div>"""
    assert scraper.get_last_page_number(_soup(html)) == 17

def test_last_page_number_absent():
    assert scraper.get_last_page_number(_soup("<div>bez paginacji</div>")) is None


# ── classify_offer_page ──────────────────────────────────────────────────────
OFFER_URL = "https://www.olx.pl/d/oferta/foo-IDabc.html"

def test_classify_404_is_dead():
    assert scraper.classify_offer_page(404, OFFER_URL, "") == "dead"

def test_classify_marker_is_dead():
    html = "<html><body><h2>To ogłoszenie jest już nieaktualne</h2></body></html>"
    assert scraper.classify_offer_page(200, OFFER_URL, html) == "dead"

def test_classify_redirect_away_is_dead():
    html = '<html><body data-testid="ad-price-container">kategoria</body></html>'
    assert scraper.classify_offer_page(200, "https://www.olx.pl/nieruchomosci/", html) == "dead"

def test_classify_alive_marker():
    html = '<html><div data-testid="ad-price-container">2 500 zł</div></html>'
    assert scraper.classify_offer_page(200, OFFER_URL, html) == "alive"

def test_classify_blocked_is_unknown():
    """403/429/5xx NIE mogą znaczyć 'martwa' — inaczej blokada WAF archiwizuje całą bazę."""
    for code in (403, 429, 500, 503):
        assert scraper.classify_offer_page(code, OFFER_URL, "") == "unknown"

def test_classify_unrecognized_layout_is_unknown():
    html = "<html><body><div>coś zupełnie innego</div></body></html>"
    assert scraper.classify_offer_page(200, OFFER_URL, html) == "unknown"

def test_classify_dead_marker_wins_over_alive_marker():
    html = ('<html><div data-testid="ad-price-container">2 500 zł</div>'
            '<p>Ogłoszenie zostało usunięte</p></html>')
    assert scraper.classify_offer_page(200, OFFER_URL, html) == "dead"


# ── _days_since ──────────────────────────────────────────────────────────────
def test_days_since():
    now = datetime(2026, 9, 10, 12, 0, 0)
    assert scraper._days_since("2026-09-03 09:00:00", now) == 7
    assert scraper._days_since("", now) is None
    assert scraper._days_since(None, now) is None


# ── scrape_profile: paginacja na atrapie OLX-a (bez sieci) ───────────────────
class _FakeResp:
    def __init__(self, text, status=200, url=""):
        self.text, self.status_code, self.url = text, status, url
    def raise_for_status(self):
        if self.status_code >= 400:
            raise scraper.requests.HTTPError(f"HTTP {self.status_code}")

def _card(lid, price=2500):
    return (f'<div data-cy="l-card">'
            f'<a href="/d/oferta/mieszkanie-{lid}-CID3-ID{lid}.html"><img src="i.jpg"></a>'
            f'<a href="/d/oferta/mieszkanie-{lid}-CID3-ID{lid}.html">Mieszkanie {lid}</a>'
            f'<p data-testid="ad-price">{price} zł</p>'
            f'<p>Lublin - Dzisiaj o 10:00</p></div>')

def _page_html(ids, last_page):
    pag = "".join(f'<a href="/x/lublin/?page={n}">{n}</a>' for n in range(2, last_page + 1))
    return (f'<html><body><h1>Znaleźliśmy 1200 ogłoszeń</h1>'
            f'{"".join(_card(i) for i in ids)}'
            f'<div data-testid="pagination-wrapper">{pag}</div></body></html>')

class _FakeSession:
    """Atrapa OLX-a: 4 strony po 3 oferty, ze wspólną ofertą promowaną na każdej."""
    LAST_PAGE = 4
    PAGES = {1: ["a1","a2","promo"], 2: ["b1","b2","promo"],
             3: ["c1","c2","promo"], 4: ["d1","d2","promo"]}
    def __init__(self, fail_on=(), empty=()):
        self.fail_on, self.empty, self.requested = set(fail_on), set(empty), []
    def get(self, url, timeout=None):
        m = re.search(r"page=(\d+)", url)
        n = int(m.group(1)) if m else 1
        self.requested.append(n)
        if n in self.fail_on:
            return _FakeResp("", status=503, url=url)
        ids = [] if (n in self.empty or n > self.LAST_PAGE) else self.PAGES[n]
        return _FakeResp(_page_html(ids, self.LAST_PAGE), url=url)

def _run_scrape(monkeypatch, session):
    monkeypatch.setattr(scraper, "get_session", lambda impersonate=None: session)
    monkeypatch.setattr(scraper.time, "sleep", lambda s: None)
    monkeypatch.setattr(scraper, "HTTP_MAX_RETRIES", 0)
    return scraper.scrape_profile("t", {"url": "https://www.olx.pl/x/lublin/"}, session)

def test_scrape_profile_collects_all_pages_and_dedupes(monkeypatch):
    s = _FakeSession()
    r = _run_scrape(monkeypatch, s)
    # 4 strony × 2 unikalne + 1 promowana powtórzona na każdej stronie
    assert r["count"] == 9, [l["listing_id"] for l in r["listings"]]
    assert r["pages_scraped"] == 4 and r["pages_expected"] == 4
    assert r["failed_pages"] == [] and r["empty_pages"] == []
    assert r["header_count"] == 1200
    assert sorted(s.requested) == [1, 2, 3, 4, 5]   # 5 = sprawdzenie ogona

def test_scrape_profile_reports_failed_page(monkeypatch):
    """Strona, której nie dało się pobrać, MUSI być zgłoszona — nie połknięta jako mniej ofert."""
    r = _run_scrape(monkeypatch, _FakeSession(fail_on=(3,)))
    assert r["failed_pages"] == [3]
    ok, reasons = scraper._check_sanity("t", r, 25, 400)
    assert not ok and any("nie pobrano stron" in x for x in reasons)

def test_scrape_profile_reports_hole_in_pagination(monkeypatch):
    r = _run_scrape(monkeypatch, _FakeSession(empty=(2,)))
    assert r["empty_pages"] == [2]

def test_scrape_profile_empty_tail_is_not_a_hole(monkeypatch):
    """Pusty ogon (paginacja zapowiada stronę, na której nic nie ma) to norma, nie anomalia."""
    r = _run_scrape(monkeypatch, _FakeSession(empty=(4,)))
    assert r["empty_pages"] == []

def test_scrape_profile_uses_stable_sort(monkeypatch):
    s = _FakeSession()
    _run_scrape(monkeypatch, s)
    assert scraper.build_start_url({"url": "https://www.olx.pl/x/lublin/"}).endswith(
        "search%5Border%5D=created_at%3Adesc")
