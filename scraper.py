#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Autonomiczny agent monitorujący ogłoszenia mieszkań na OLX Lublin.
Scrape'uje kategorie, śledzi ceny/promo/odświeżenia/reaktywacje, generuje JSON i Excel.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
import random
import logging
from datetime import datetime, timedelta
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("szperacz-mieszkaniowy")

PROFILES = {
    "mieszkania_lublin": {
        "url": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/lublin/",
        "label": "Mieszkania na wynajem — Lublin",
        "is_category": True,
    },
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
EXCEL_PATH = os.path.join(DATA_DIR, "szperacz_mieszkaniowy.xlsx")
JSON_PATH  = os.path.join(DATA_DIR, "dashboard_data.json")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# ─── HTTP Session ────────────────────────────────────────────────────────────

def get_session():
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse_price(text):
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text.split("zł")[0] if "zł" in text else text)
    try:
        return int(cleaned) if cleaned else None
    except ValueError:
        return None

def parse_date_text(text):
    if not text:
        return None, None
    text = text.strip()
    today = datetime.now().strftime("%Y-%m-%d")
    if "Odświeżono" in text or "odświeżono" in text:
        return None, _extract_date(text)
    if "Dzisiaj" in text or "dzisiaj" in text:
        return today, today
    return _extract_date(text), None

def _extract_date(text):
    months_pl = {
        "stycznia":"01","lutego":"02","marca":"03","kwietnia":"04","maja":"05","czerwca":"06",
        "lipca":"07","sierpnia":"08","września":"09","października":"10","listopada":"11","grudnia":"12",
    }
    today = datetime.now()
    tl = text.lower()
    if "dzisiaj" in tl: return today.strftime("%Y-%m-%d")
    if "wczoraj" in tl: return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    for mpl, mnum in months_pl.items():
        if mpl in tl:
            m = re.search(r"(\d{1,2})\s+" + mpl + r"\s+(\d{4})", tl)
            if m: return f"{m.group(2)}-{mnum}-{m.group(1).zfill(2)}"
            m = re.search(r"(\d{1,2})\s+" + mpl, tl)
            if m: return f"{today.year}-{mnum}-{m.group(1).zfill(2)}"
    return None

def extract_listing_id(url):
    m = re.search(r"ID([a-zA-Z0-9]+)\.html", url)
    if m: return m.group(1)
    return url.rstrip("/").split("/")[-1]

# ─── Promoted Detection ───────────────────────────────────────────────────────

def detect_promoted_status(card):
    signals = []
    for link in card.select('a[href*="/d/oferta/"]'):
        href = link.get('href', '')
        if 'search_reason=search%7Cpromoted' in href or ('promoted' in href.lower() and '/d/oferta/' in href):
            signals.append(('url_parameter', 1.0))
            break
    if card.select_one('[data-testid="adCard-featured"]'):
        signals.append(('featured_badge', 1.0))
    if card.select_one('[data-testid="listing-ad-badge"]'):
        signals.append(('ad_badge', 0.9))
    element_classes = ' '.join(card.get('class', [])).lower()
    if any(kw in element_classes for kw in ['featured','promoted','highlighted','top-ad','premium','vip']):
        signals.append(('css_class', 0.8))
    if any(b in card.get_text() for b in ['Wyróżnione','Promowane','Premium','TOP','Pilne']):
        signals.append(('text_badge', 0.85))
    if card.get('data-promoted') or card.get('data-featured'):
        signals.append(('data_attribute', 1.0))
    if not signals:
        return {'is_promoted': False, 'promotion_type': None, 'confidence': 1.0}
    max_conf = max(s[1] for s in signals)
    types = [s[0] for s in signals]
    if 'url_parameter' in types or 'featured_badge' in types or 'data_attribute' in types:
        promo_type = 'featured'
    elif 'ad_badge' in types:
        promo_type = 'top_ad'
    elif 'text_badge' in types or 'css_class' in types:
        promo_type = 'highlight'
    else:
        promo_type = 'unknown'
    return {'is_promoted': True, 'promotion_type': promo_type, 'confidence': max_conf}

# ─── Card Parsing ─────────────────────────────────────────────────────────────

DATE_KEYWORDS = [
    "odświeżono","dzisiaj","wczoraj",
    "stycznia","lutego","marca","kwietnia","maja","czerwca",
    "lipca","sierpnia","września","października","listopada","grudnia",
]

def parse_card(card):
    title = ""
    href  = ""
    for link in card.select('a[href*="/d/oferta/"]'):
        txt = link.get_text(strip=True)
        if txt and len(txt) > 3:
            title = txt
            href  = link.get("href", "")
            break
        elif not href:
            href = link.get("href", "")
    if not href:
        return None
    full_url = href if href.startswith("http") else f"https://www.olx.pl{href}"
    if not title:
        m = re.search(r"/oferta/(.+?)-CID", href)
        if m: title = m.group(1).replace("-"," ").title()
    if not title:
        return None

    price_el = card.select_one('[data-testid="ad-price"]')
    price_text = price_el.get_text(strip=True) if price_el else ""

    date_text = ""
    location_text = ""
    for el in card.find_all(["p","span"]):
        txt = el.get_text(strip=True)
        if not txt or len(txt) > 120:
            continue
        tl = txt.lower()
        if any(kw in tl for kw in DATE_KEYWORDS):
            if " - " in txt:
                parts = txt.split(" - ", 1)
                location_text = parts[0].strip()
                date_text     = parts[1].strip()
            elif not date_text:
                date_text = txt
        elif txt in ["Lublin","Lublin, lubelskie"] and not location_text:
            location_text = txt

    img = card.select_one("img")
    image_url = img.get("src","") if img else ""
    promo = detect_promoted_status(card)

    return {
        "title": title,
        "price_text": price_text,
        "price": parse_price(price_text),
        "date_text": date_text,
        "location": location_text,
        "url": full_url,
        "listing_id": extract_listing_id(full_url),
        "image_url": image_url,
        "is_promoted": promo["is_promoted"],
        "promotion_type": promo["promotion_type"],
    }

def parse_listings_from_soup(soup):
    cards = soup.select('[data-cy="l-card"]')
    if not cards:
        cards = soup.select("div.css-19pezs8")
    if not cards:
        seen = set()
        for link in soup.select('a[href*="/d/oferta/"]'):
            href = link.get("href","")
            if href in seen: continue
            seen.add(href)
            container = link
            for _ in range(6):
                p = container.parent
                if not p: break
                if p.select_one('[data-testid="ad-price"]'):
                    container = p
                    break
                container = p
            if container != link:
                cards.append(container)
    listings = []
    for card in cards:
        parsed = parse_card(card)
        if parsed:
            listings.append(parsed)
    return listings

def get_total_count_from_header(soup):
    for el in soup.find_all(string=re.compile(r"Znaleźliśmy\s+\d+")):
        m = re.search(r"Znaleźliśmy\s+(\d+)\s+ogłosze", el)
        if m: return int(m.group(1))
    return None

def get_next_page_url(soup, current_url):
    for sel in ['[data-testid="pagination-forward"]','[data-cy="pagination-forward"]']:
        pag = soup.select_one(sel)
        if pag:
            href = pag.get("href","")
            if href:
                return href if href.startswith("http") else f"https://www.olx.pl{href}"
    return None

# ─── Scraping + Crosscheck ───────────────────────────────────────────────────

def scrape_profile(profile_key, profile_config, session):
    url = profile_config["url"]
    all_listings = []
    header_count = None
    page = 1
    max_pages = 50

    while url and page <= max_pages:
        log.info(f"  [{profile_key}] Page {page}: {url}")
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error(f"  [{profile_key}] HTTP error page {page}: {e}")
            break
        soup = BeautifulSoup(resp.text, "lxml")
        if page == 1:
            header_count = get_total_count_from_header(soup)
            log.info(f"  [{profile_key}] Header count: {header_count}")
        page_listings = parse_listings_from_soup(soup)
        log.info(f"  [{profile_key}] Page {page}: {len(page_listings)} listings")
        if not page_listings:
            break
        all_listings.extend(page_listings)
        url = get_next_page_url(soup, url)
        page += 1
        time.sleep(random.uniform(1.5, 3.0))

    seen = set()
    unique = []
    for l in all_listings:
        if l["listing_id"] not in seen:
            seen.add(l["listing_id"])
            unique.append(l)
    return {"listings": unique, "count": len(unique), "header_count": header_count, "pages_scraped": page-1}

def scrape_with_crosscheck(profile_key, profile_config):
    log.info(f"[SCAN] Crosscheck: {profile_key}")
    r1 = scrape_profile(profile_key, profile_config, get_session())
    scraped, header = r1["count"], r1["header_count"]
    tolerance = 10 if profile_config.get("is_category") else 0
    if header is None or abs(scraped - header) <= tolerance:
        log.info(f"[CROSSCHECK] {profile_key}: PASS (scraped={scraped}, header={header})")
        r1["crosscheck"] = "passed"
        return r1
    log.info(f"[CROSSCHECK] {profile_key}: MISMATCH scraped={scraped} vs header={header}, retrying...")
    time.sleep(random.uniform(3, 5))
    r2 = scrape_profile(profile_key, profile_config, get_session())
    c1, c2 = r1["count"], r2["count"]
    if header is not None:
        if abs(c2-header) < abs(c1-header):
            r2["crosscheck"] = "passed_retry"; return r2
        if c1 == c2:
            r1["crosscheck"] = "consistent"; return r1
    else:
        if c2 > c1:
            r2["crosscheck"] = "no_header_retry"; return r2
    r1["crosscheck"] = "best_of_two"; return r1

# ─── Excel ───────────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill("solid", fgColor="1A3A6B")
HEADER_FONT = Font(bold=True, color="FFD700", name="Arial", size=10)
DATA_FONT   = Font(name="Arial", size=10)
UP_FONT     = Font(name="Arial", size=10, color="00B050")
DOWN_FONT   = Font(name="Arial", size=10, color="FF0000")
THIN_BORDER = Border(
    left=Side(style="thin",color="D9D9D9"), right=Side(style="thin",color="D9D9D9"),
    top=Side(style="thin",color="D9D9D9"),  bottom=Side(style="thin",color="D9D9D9"),
)

def style_header_row(ws, row, num_cols):
    for col in range(1, num_cols+1):
        c = ws.cell(row=row, column=col)
        c.fill = HEADER_FILL; c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN_BORDER

def style_data_cell(cell, font=None):
    cell.font = font or DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = Alignment(vertical="center", wrap_text=True)

def load_or_create_workbook():
    if os.path.exists(EXCEL_PATH):
        try: return load_workbook(EXCEL_PATH)
        except Exception as e: log.warning(f"Cannot load Excel: {e}. Creating new.")
    wb = Workbook(); wb.remove(wb.active); return wb

def get_or_create_sheet(wb, name, headers):
    if name in wb.sheetnames:
        ws = wb[name]
        for ci, h in enumerate(headers, 1): ws.cell(row=1, column=ci, value=h)
        style_header_row(ws, 1, len(headers))
        return ws
    ws = wb.create_sheet(name)
    for ci, h in enumerate(headers, 1): ws.cell(row=1, column=ci, value=h)
    style_header_row(ws, 1, len(headers))
    return ws

def update_excel(scan_results, scan_timestamp):
    os.makedirs(DATA_DIR, exist_ok=True)
    wb = load_or_create_workbook()
    today   = scan_timestamp.strftime("%Y-%m-%d")
    now_str = scan_timestamp.strftime("%Y-%m-%d %H:%M")

    # Load refresh counts from JSON
    refresh_count_map = {}
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                jd = json.load(f)
            for pk, pd_ in jd.get("profiles", {}).items():
                for listing in pd_.get("current_listings", []):
                    refresh_count_map[listing.get("id","")] = listing.get("refresh_count", 0)
        except Exception: pass

    profile_headers = [
        "Data scanu","Godzina","Liczba ogłoszeń","Zmiana vs poprzedni","Crosscheck",
        "Tytuł","Cena (zł)","Zmiana ceny","Promo","Dni Prom.","Sesje",
        "Data publikacji","Data odświeżenia","URL","Licz. odsw.","Licz. reakt.","Dni aktywne",
    ]

    for pk, result in scan_results.items():
        ws = get_or_create_sheet(wb, pk[:31], profile_headers)
        prev_count = None
        for row in range(ws.max_row, 1, -1):
            val = ws.cell(row=row, column=3).value
            if val is not None and isinstance(val, (int,float)):
                prev_count = int(val); break
        cur = result["count"]
        ch  = cur - prev_count if prev_count is not None else 0
        nr  = ws.max_row + 1
        if nr > 2: nr += 1

        ws.cell(row=nr, column=1, value=today)
        ws.cell(row=nr, column=2, value=scan_timestamp.strftime("%H:%M"))
        ws.cell(row=nr, column=3, value=cur)
        f = UP_FONT if ch > 0 else DOWN_FONT if ch < 0 else DATA_FONT
        style_data_cell(ws.cell(row=nr, column=4, value=ch), f)
        ws.cell(row=nr, column=5, value=result.get("crosscheck",""))
        for c in [1,2,3,5]: style_data_cell(ws.cell(row=nr, column=c))

        for i, listing in enumerate(result["listings"]):
            row = nr + 1 + i
            pub, ref = parse_date_text(listing.get("date_text",""))
            lid = listing["listing_id"]
            is_promoted = listing.get("is_promoted", False)
            promo_days  = listing.get("promoted_days_current", 0)
            promo_sess  = listing.get("promoted_sessions_count", 0)
            refresh_cnt = refresh_count_map.get(lid, 0)
            react_cnt   = listing.get("reactivation_count", 0)

            # Days active
            first_seen_str = listing.get("first_seen","")
            try:
                fs = datetime.strptime(first_seen_str[:10], "%Y-%m-%d") if first_seen_str else None
                days_active = (datetime.now() - fs).days + 1 if fs else None
            except Exception: days_active = None

            ws.cell(row=row, column=1,  value=today)
            ws.cell(row=row, column=2,  value=scan_timestamp.strftime("%H:%M"))
            ws.cell(row=row, column=6,  value=listing["title"])
            ws.cell(row=row, column=7,  value=listing["price"])
            ws.cell(row=row, column=9,  value="★" if is_promoted else "")
            ws.cell(row=row, column=10, value=promo_days if is_promoted else None)
            ws.cell(row=row, column=11, value=promo_sess  if promo_sess > 0 else None)
            ws.cell(row=row, column=12, value=pub or "")
            ws.cell(row=row, column=13, value=ref or "")
            ws.cell(row=row, column=14, value=listing["url"])
            ws.cell(row=row, column=15, value=refresh_cnt)
            ws.cell(row=row, column=16, value=react_cnt)
            ws.cell(row=row, column=17, value=days_active)
            for c in range(1, 18): style_data_cell(ws.cell(row=row, column=c))

        widths = [12,8,15,15,14,50,12,12,8,10,8,14,14,60,10,10,10]
        for idx, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(idx)].width = w

    # Historia cen
    ph = ["Data","Profil","ID ogłoszenia","Tytuł","Cena (zł)","Poprzednia cena","Zmiana ceny","URL"]
    ws_p = get_or_create_sheet(wb, "historia_cen", ph)
    prev_prices = {}
    for row in range(2, ws_p.max_row+1):
        lid   = ws_p.cell(row=row, column=3).value
        price = ws_p.cell(row=row, column=5).value
        if lid and price is not None:
            prev_prices[lid] = int(price) if isinstance(price,(int,float)) else None
    for pk, result in scan_results.items():
        for listing in result["listings"]:
            lid = listing["listing_id"]
            cp  = listing["price"]
            pp  = prev_prices.get(lid)
            pc  = (cp - pp) if (pp is not None and cp is not None) else None
            r   = ws_p.max_row + 1
            ws_p.cell(row=r, column=1, value=now_str)
            ws_p.cell(row=r, column=2, value=pk)
            ws_p.cell(row=r, column=3, value=lid)
            ws_p.cell(row=r, column=4, value=listing["title"])
            ws_p.cell(row=r, column=5, value=cp)
            ws_p.cell(row=r, column=6, value=pp)
            ws_p.cell(row=r, column=7, value=pc)
            ws_p.cell(row=r, column=8, value=listing["url"])
            for c in range(1,9):
                cell = ws_p.cell(row=r, column=c)
                cf = DOWN_FONT if (c==7 and pc and pc<0) else UP_FONT if (c==7 and pc and pc>0) else DATA_FONT
                style_data_cell(cell, cf)
            if cp is not None: prev_prices[lid] = cp
    for idx, w in enumerate([18,18,15,50,12,14,12,60],1):
        ws_p.column_dimensions[get_column_letter(idx)].width = w

    # Podsumowanie
    if "podsumowanie" in wb.sheetnames: del wb["podsumowanie"]
    ws_s = wb.create_sheet("podsumowanie")
    sh = ["Profil","Label","Dzisiejsza liczba","Poprzednia liczba","Zmiana","Crosscheck","Data scanu"]
    for ci,h in enumerate(sh,1): ws_s.cell(row=1, column=ci, value=h)
    style_header_row(ws_s, 1, len(sh))
    ri = 2
    for pk, result in scan_results.items():
        cur = result["count"]; sn = pk[:31]; prev = None
        if sn in wb.sheetnames:
            counts = [int(wb[sn].cell(row=r,column=3).value) for r in range(2,wb[sn].max_row+1)
                      if wb[sn].cell(row=r,column=3).value is not None and isinstance(wb[sn].cell(row=r,column=3).value,(int,float))]
            if len(counts) >= 2: prev = counts[-2]
        ch = cur - prev if prev is not None else 0
        ws_s.cell(row=ri, column=1, value=pk)
        ws_s.cell(row=ri, column=2, value=PROFILES[pk]["label"])
        ws_s.cell(row=ri, column=3, value=cur)
        ws_s.cell(row=ri, column=4, value=prev)
        ws_s.cell(row=ri, column=5, value=ch)
        ws_s.cell(row=ri, column=6, value=result.get("crosscheck",""))
        ws_s.cell(row=ri, column=7, value=now_str)
        for c in range(1,8):
            cell = ws_s.cell(row=ri, column=c)
            f = UP_FONT if (c==5 and ch>0) else DOWN_FONT if (c==5 and ch<0) else DATA_FONT
            style_data_cell(cell, f)
        ri += 1
    for idx, w in enumerate([20,30,18,18,10,16,20],1):
        ws_s.column_dimensions[get_column_letter(idx)].width = w

    wb.save(EXCEL_PATH)
    log.info(f"Excel saved: {EXCEL_PATH}")

# ─── JSON for Dashboard ───────────────────────────────────────────────────────

def load_existing_json():
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH,"r",encoding="utf-8") as f: return json.load(f)
        except (json.JSONDecodeError, IOError): pass
    return {"profiles":{}, "scan_history":[], "last_scan":None}

def generate_dashboard_json(scan_results, scan_timestamp):
    data    = load_existing_json()
    now_str = scan_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    today   = scan_timestamp.strftime("%Y-%m-%d")
    data["last_scan"] = now_str
    scan_entry = {"timestamp": now_str, "date": today, "profiles": {}}

    for pk, result in scan_results.items():
        cfg = PROFILES[pk]
        if pk not in data["profiles"]:
            data["profiles"][pk] = {
                "label": cfg["label"], "url": cfg["url"],
                "is_category": cfg.get("is_category", False),
                "daily_counts": [], "current_listings": [],
                "archived_listings": [], "price_history": {},
                "promotion_history": {},
            }

        pd_ = data["profiles"][pk]
        # Backward-compat: ensure promotion_history exists
        if "promotion_history" not in pd_:
            pd_["promotion_history"] = {}
        dc  = pd_["daily_counts"]

        crosscheck   = result.get("crosscheck","")
        header_count = result.get("header_count")
        is_scraper_error = (crosscheck == "error" or (result["count"] == 0 and header_count is None))
        current_listings_count = len(pd_.get("current_listings",[]))
        skip_daily_update = is_scraper_error and current_listings_count > 0

        if skip_daily_update:
            log.warning(f"[{pk}] Skipping update — scraper error (crosscheck={crosscheck}, header={header_count})")
            scan_entry["profiles"][pk] = {"count": result["count"], "crosscheck": crosscheck}
            continue

        # ── Promoted & flow stats ──
        current_ids_new = {l["listing_id"] for l in result["listings"]}
        old_ids         = {l["id"] for l in pd_.get("current_listings",[])}
        newly_detected  = [l for l in result["listings"] if l["listing_id"] not in old_ids]

        if len(old_ids) == 0 and len(dc) == 0:
            flow_added = None; flow_removed = None
        else:
            flow_added   = len(current_ids_new - old_ids)
            flow_removed = len(old_ids - current_ids_new)

        total  = result["count"]
        promo_count = sum(1 for l in result["listings"] if l.get("is_promoted"))
        promo_pct   = round(promo_count / total * 100, 1) if total > 0 else 0

        # Price distribution snapshot (all active listings with price)
        def build_price_distribution(listings):
            prices = sorted([l["price"] for l in listings if l.get("price") and l["price"] > 0])
            if not prices:
                return []
            # Auto bucket step: aim for ~14 buckets, nice round number
            mn, mx = prices[0], prices[-1]
            if mn == mx:
                return [{"from": mn, "to": mx + 1, "count": len(prices)}]
            raw = (mx - mn) / 14
            mag = 10 ** int(len(str(int(raw))) - 1)
            step = next((f * mag for f in [1, 2, 2.5, 5, 10] if f * mag >= raw), 10 * mag)
            start = (mn // step) * step
            buckets = []
            s = start
            while s <= mx:
                cnt = sum(1 for p in prices if p >= s and p < s + step)
                buckets.append({"from": int(s), "to": int(s + step), "count": cnt})
                s += step
            # last price edge case
            if prices[-1] >= s - step:
                buckets[-1]["count"] += sum(1 for p in prices if p >= s)
            # trim empty edges
            while len(buckets) > 1 and buckets[-1]["count"] == 0: buckets.pop()
            while len(buckets) > 1 and buckets[0]["count"] == 0:  buckets.pop(0)
            return buckets

        price_dist = build_price_distribution(result["listings"])

        # Median from NEW listings only
        new_prices = [l["price"] for l in newly_detected if l.get("price") and l["price"] > 0]
        if new_prices:
            sp = sorted(new_prices); n = len(sp)
            median_price = sp[n//2] if n%2 != 0 else (sp[n//2-1]+sp[n//2])//2
        else:
            median_price = None

        # ── daily_counts ──
        today_entry = next((d for d in dc if d["date"] == today), None)
        if today_entry:
            if result["count"] >= today_entry["count"]:
                today_entry["count"]               = result["count"]
                today_entry["timestamp"]           = now_str
                today_entry["median_price"]        = median_price
                today_entry["promoted_count"]      = promo_count
                today_entry["promoted_percentage"] = promo_pct
                today_entry["price_distribution"]  = price_dist
                prev_added   = today_entry.get("added") or 0
                prev_removed = today_entry.get("removed") or 0
                if flow_added is not None:
                    today_entry["added"]   = prev_added + flow_added
                    today_entry["removed"] = prev_removed + flow_removed
                if len(dc) >= 2:
                    today_entry["change"] = result["count"] - dc[-2]["count"]
        else:
            prev_c = dc[-1]["count"] if dc else None
            ch     = result["count"] - prev_c if prev_c is not None else 0
            dc.append({
                "date": today, "count": result["count"], "change": ch,
                "timestamp": now_str, "median_price": median_price,
                "promoted_count": promo_count, "promoted_percentage": promo_pct,
                "price_distribution": price_dist,
                "refreshed_count": 0, "reactivated_count": 0,
                "added": flow_added, "removed": flow_removed,
            })
        if len(dc) > 90: pd_["daily_counts"] = dc[-90:]

        # ── Build new_listings ──
        new_listings = []
        for listing in result["listings"]:
            pub, ref = parse_date_text(listing.get("date_text",""))
            nl = {
                "id": listing["listing_id"], "title": listing["title"],
                "price": listing["price"], "price_text": listing.get("price_text",""),
                "url": listing["url"], "published": pub, "refreshed": ref,
                "date_text": listing.get("date_text",""),
                "image_url": listing.get("image_url",""),
                "first_seen": now_str, "last_seen": now_str,
                "is_promoted": listing.get("is_promoted", False),
                "promotion_type": listing.get("promotion_type"),
                "refresh_count": 0,
                "promoted_days_current": 0,
                "promoted_sessions_count": 0,
                "promotion_history": [],
                "reactivation_count": 0,
                "reactivation_history": [],
            }
            new_listings.append(nl)

        old_map      = {l["id"]: l for l in pd_.get("current_listings",[])}
        archived_map = {l["id"]: l for l in pd_.get("archived_listings",[])}

        for nl in new_listings:
            lid = nl["id"]
            if lid in old_map:
                old = old_map[lid]
                nl["first_seen"] = old.get("first_seen", now_str)

                # Price history
                old_price = old.get("price"); new_price = nl.get("price")
                if old_price is not None and new_price is not None and old_price != new_price:
                    if lid not in pd_["price_history"]: pd_["price_history"][lid] = []
                    pd_["price_history"][lid].append({
                        "date": now_str, "old_price": old_price,
                        "new_price": new_price, "change": new_price - old_price,
                    })
                    nl["previous_price"] = old_price
                    nl["price_change"]   = new_price - old_price
                elif lid in pd_.get("price_history",{}):
                    h = pd_["price_history"][lid]
                    if h:
                        nl["previous_price"] = h[-1]["old_price"]
                        nl["price_change"]   = (nl["price"] - h[-1]["old_price"]) if nl["price"] else None

                # Reactivation carry
                nl["reactivation_history"] = old.get("reactivation_history",[])
                nl["reactivation_count"]   = len(nl["reactivation_history"])

                # Refresh detection
                nl["refresh_count"]   = old.get("refresh_count", 0)
                nl["refresh_history"] = old.get("refresh_history",[])
                old_ref = old.get("refreshed")
                new_ref = nl.get("refreshed")
                if new_ref and new_ref != old_ref:
                    already = any(h.get("refreshed_at") == new_ref for h in nl["refresh_history"])
                    if not already:
                        nl["refresh_count"] += 1
                        nl["refresh_history"].append({
                            "refreshed_at": new_ref, "detected_at": now_str, "old_date": old_ref,
                        })
                        log.info(f"  [REFRESHED] {lid}: odświeżeń={nl['refresh_count']}")

                # Promotion tracking
                if lid not in pd_["promotion_history"]: pd_["promotion_history"][lid] = []
                nl["promotion_history"]       = old.get("promotion_history",[])
                nl["promoted_days_current"]   = old.get("promoted_days_current", 0)
                nl["promoted_sessions_count"] = old.get("promoted_sessions_count", 0)
                old_promo = old.get("is_promoted", False)
                new_promo = nl.get("is_promoted", False)
                if new_promo and not old_promo:
                    nl["promotion_started_at"]    = now_str
                    nl["promoted_days_current"]   = 1
                    nl["promoted_sessions_count"] = old.get("promoted_sessions_count",0) + 1
                elif new_promo and old_promo:
                    nl["promotion_started_at"]  = old.get("promotion_started_at", now_str)
                    nl["promoted_days_current"] = old.get("promoted_days_current",0) + 1
                    nl["promoted_sessions_count"] = old.get("promoted_sessions_count",0)
                elif not new_promo and old_promo:
                    promo_start = old.get("promotion_started_at", now_str)
                    days = old.get("promoted_days_current",1)
                    nl["promotion_history"].append({
                        "start_date": promo_start, "end_date": now_str, "days": days,
                        "promotion_type": old.get("promotion_type","unknown"),
                        "session_number": old.get("promoted_sessions_count",0),
                    })
                    nl["promoted_days_current"] = 0
                    nl.pop("promotion_started_at", None)

            elif lid in archived_map:
                # Reactivation
                old_archived = archived_map[lid]
                nl["first_seen"] = old_archived.get("first_seen", now_str)
                history = old_archived.get("reactivation_history",[])
                history.append({"active_from": old_archived.get("first_seen"), "reactivated_at": now_str})
                nl["reactivation_history"] = history
                nl["reactivation_count"]   = len(history)
                nl["refresh_count"]        = old_archived.get("refresh_count",0)
                nl["refresh_history"]      = old_archived.get("refresh_history",[])
                nl["promoted_days_current"]   = 0
                nl["promoted_sessions_count"] = old_archived.get("promoted_sessions_count",0)
                nl["promotion_history"]       = old_archived.get("promotion_history",[])
                if nl.get("is_promoted"):
                    nl["promotion_started_at"]    = now_str
                    nl["promoted_days_current"]   = 1
                    nl["promoted_sessions_count"] += 1
            else:
                # Brand new
                if nl.get("is_promoted"):
                    nl["promotion_started_at"]  = now_str
                    nl["promoted_days_current"] = 1
                    nl["promoted_sessions_count"] = 1

        # ── Archiving ──
        newly_archived = []
        for old_l in pd_.get("current_listings",[]):
            if old_l["id"] not in current_ids_new:
                old_l["archived_date"] = now_str
                r_hist = old_l.get("reactivation_history",[])
                if r_hist and "active_to_current" not in r_hist[-1]:
                    r_hist[-1]["active_to_current"] = now_str
                old_l["reactivation_count"] = len(r_hist)
                if not old_l.get("refresh_history"): old_l["refresh_history"] = []
                if not old_l.get("refresh_count"):   old_l["refresh_count"] = len(old_l["refresh_history"])
                pd_["archived_listings"].append(old_l)
                newly_archived.append(old_l)

        if len(pd_["archived_listings"]) > 500:
            pd_["archived_listings"] = pd_["archived_listings"][-500:]

        # ── Count refreshes & reactivations today ──
        reactivated_count = 0; refreshed_count = 0
        for l in list(new_listings) + newly_archived:
            rh = l.get("reactivation_history",[])
            if rh and rh[-1].get("reactivated_at","").startswith(today): reactivated_count += 1
            fh = l.get("refresh_history",[])
            if fh and fh[-1].get("detected_at","").startswith(today): refreshed_count += 1
        te = next((d for d in dc if d["date"] == today), None)
        if te:
            te["reactivated_count"] = reactivated_count
            te["refreshed_count"]   = refreshed_count

        pd_["current_listings"] = new_listings
        scan_entry["profiles"][pk] = {"count": result["count"], "crosscheck": crosscheck}

    data["scan_history"].append(scan_entry)
    if len(data["scan_history"]) > 90: data["scan_history"] = data["scan_history"][-90:]
    with open(JSON_PATH,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Dashboard JSON saved: {JSON_PATH}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def run_scan():
    ts = datetime.now()
    log.info(f"{'='*60}")
    log.info(f"SZPERACZ MIESZKANIOWY — Scan started {ts.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")
    results = {}
    for pk, cfg in PROFILES.items():
        try:
            r = scrape_with_crosscheck(pk, cfg)
            results[pk] = r
            log.info(f"[OK] {pk}: {r['count']} listings ({r['crosscheck']})")
        except Exception as e:
            log.error(f"[ERROR] {pk}: {e}")
            results[pk] = {"listings":[], "count":0, "header_count":None, "crosscheck":"error", "pages_scraped":0}
        time.sleep(random.uniform(2,4))
    generate_dashboard_json(results, ts)
    update_excel(results, ts)
    log.info(f"SZPERACZ MIESZKANIOWY — Scan completed {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return results

if __name__ == "__main__":
    run_scan()
