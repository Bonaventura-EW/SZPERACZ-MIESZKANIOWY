#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Autonomiczny agent monitorujący ogłoszenia mieszkań na OLX Lublin.
Scrape'uje kategorie, śledzi ceny, zapisuje do Excela i generuje JSON dla dashboardu.
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

# ─── Configuration ───────────────────────────────────────────────────────────

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
JSON_PATH = os.path.join(DATA_DIR, "dashboard_data.json")

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
    ua = random.choice(USER_AGENTS)
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


# ─── Parsing Helpers ─────────────────────────────────────────────────────────

def parse_price(text):
    if not text:
        return None
    cleaned = text.replace(" ", "").replace("\xa0", "")
    cleaned = re.sub(r"[^\d]", "", cleaned.split("zł")[0] if "zł" in cleaned else cleaned)
    if cleaned:
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def parse_date_text(text):
    if not text:
        return None, None
    text = text.strip()
    today = datetime.now().strftime("%Y-%m-%d")
    refreshed = None
    published = None

    if "Odświeżono" in text or "odświeżono" in text:
        refreshed = _extract_date(text)
    elif "Dzisiaj" in text or "dzisiaj" in text:
        refreshed = today
        published = today
    else:
        published = _extract_date(text)

    return published, refreshed


def _extract_date(text):
    months_pl = {
        "stycznia": "01", "lutego": "02", "marca": "03", "kwietnia": "04",
        "maja": "05", "czerwca": "06", "lipca": "07", "sierpnia": "08",
        "września": "09", "października": "10", "listopada": "11", "grudnia": "12",
    }
    today = datetime.now()
    if "dzisiaj" in text.lower():
        return today.strftime("%Y-%m-%d")
    if "wczoraj" in text.lower():
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    for month_pl, month_num in months_pl.items():
        if month_pl in text.lower():
            match = re.search(r"(\d{1,2})\s+" + month_pl + r"\s+(\d{4})", text.lower())
            if match:
                return f"{match.group(2)}-{month_num}-{match.group(1).zfill(2)}"
            match = re.search(r"(\d{1,2})\s+" + month_pl, text.lower())
            if match:
                return f"{today.year}-{month_num}-{match.group(1).zfill(2)}"
    return None


def extract_listing_id(url):
    match = re.search(r"ID([a-zA-Z0-9]+)\.html", url)
    if match:
        return match.group(1)
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url


# ─── Card Parsing ────────────────────────────────────────────────────────────

DATE_KEYWORDS = [
    "odświeżono", "dzisiaj", "wczoraj",
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]


def parse_card(card):
    """Parse a single OLX listing card."""
    title = ""
    href = ""
    for link in card.select('a[href*="/d/oferta/"]'):
        txt = link.get_text(strip=True)
        if txt and len(txt) > 3:
            title = txt
            href = link.get("href", "")
            break
        elif not href:
            href = link.get("href", "")

    if not href:
        return None

    full_url = href if href.startswith("http") else f"https://www.olx.pl{href}"

    if not title:
        url_match = re.search(r"/oferta/(.+?)-CID", href)
        if url_match:
            title = url_match.group(1).replace("-", " ").title()

    if not title:
        return None

    price_text = ""
    price_el = card.select_one('[data-testid="ad-price"]')
    if price_el:
        price_text = price_el.get_text(strip=True)

    date_text = ""
    location_text = ""

    for el in card.find_all(["p", "span"]):
        txt = el.get_text(strip=True)
        if not txt or len(txt) > 120:
            continue
        txt_lower = txt.lower()
        if any(kw in txt_lower for kw in DATE_KEYWORDS):
            if " - " in txt:
                parts = txt.split(" - ", 1)
                location_text = parts[0].strip()
                date_text = parts[1].strip()
            elif not date_text:
                date_text = txt
        elif txt in ["Lublin", "Lublin, lubelskie"] and not location_text:
            location_text = txt

    img = card.select_one("img")
    image_url = img.get("src", "") if img else ""

    return {
        "title": title,
        "price_text": price_text,
        "price": parse_price(price_text),
        "date_text": date_text,
        "location": location_text,
        "url": full_url,
        "listing_id": extract_listing_id(full_url),
        "image_url": image_url,
    }


def parse_listings_from_soup(soup):
    """Parse all listings from page."""
    listings = []

    cards = soup.select('[data-cy="l-card"]')

    if not cards:
        cards = soup.select("div.css-19pezs8")

    if not cards:
        seen = set()
        for link in soup.select('a[href*="/d/oferta/"]'):
            href = link.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            container = link
            for _ in range(6):
                p = container.parent
                if not p:
                    break
                if p.select_one('[data-testid="ad-price"]'):
                    container = p
                    break
                container = p
            if container != link:
                cards.append(container)

    for card in cards:
        parsed = parse_card(card)
        if parsed:
            listings.append(parsed)

    return listings


def get_total_count_from_header(soup):
    for el in soup.find_all(string=re.compile(r"Znaleźliśmy\s+\d+")):
        match = re.search(r"Znaleźliśmy\s+(\d+)\s+ogłosze", el)
        if match:
            return int(match.group(1))
    return None


def get_next_page_url(soup, current_url):
    for selector in ['[data-testid="pagination-forward"]', '[data-cy="pagination-forward"]']:
        pag = soup.select_one(selector)
        if pag:
            href = pag.get("href", "")
            if href:
                return href if href.startswith("http") else f"https://www.olx.pl{href}"
    return None


# ─── Scraping with Crosscheck ───────────────────────────────────────────────

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

    seen_ids = set()
    unique = []
    for listing in all_listings:
        lid = listing["listing_id"]
        if lid not in seen_ids:
            seen_ids.add(lid)
            unique.append(listing)

    return {
        "listings": unique,
        "count": len(unique),
        "header_count": header_count,
        "pages_scraped": page - 1,
    }


def scrape_with_crosscheck(profile_key, profile_config):
    log.info(f"[SCAN] Crosscheck: {profile_key}")

    session1 = get_session()
    result1 = scrape_profile(profile_key, profile_config, session1)

    scraped = result1["count"]
    header = result1["header_count"]

    tolerance = 10 if profile_config.get("is_category") else 0
    header_match = header is None or abs(scraped - header) <= tolerance

    if header_match:
        log.info(f"[CROSSCHECK] {profile_key}: PASS (scraped={scraped}, header={header})")
        result1["crosscheck"] = "passed"
        result1["crosscheck_detail"] = f"scraped={scraped}, header={header}"
        return result1

    log.info(f"[CROSSCHECK] {profile_key}: MISMATCH scraped={scraped} vs header={header}, retrying...")
    time.sleep(random.uniform(3, 5))

    session2 = get_session()
    result2 = scrape_profile(profile_key, profile_config, session2)
    c1, c2 = result1["count"], result2["count"]

    if header is not None:
        d1 = abs(c1 - header)
        d2 = abs(c2 - header)
        if d2 < d1:
            result2["crosscheck"] = "passed_retry"
            result2["crosscheck_detail"] = f"1st={c1}, 2nd={c2}, header={header}"
            return result2
        if c1 == c2:
            result1["crosscheck"] = "consistent"
            result1["crosscheck_detail"] = f"both={c1}, header={header}"
            return result1
    else:
        if c2 > c1:
            result2["crosscheck"] = "no_header_retry"
            result2["crosscheck_detail"] = f"1st={c1}, 2nd={c2}"
            return result2

    result1["crosscheck"] = "best_of_two"
    result1["crosscheck_detail"] = f"1st={c1}, 2nd={c2}, header={header}"
    return result1


# ─── Excel Operations ────────────────────────────────────────────────────────

HEADER_FILL = PatternFill("solid", fgColor="1A3A6B")
HEADER_FONT = Font(bold=True, color="FFD700", name="Arial", size=10)
DATA_FONT = Font(name="Arial", size=10)
UP_FONT = Font(name="Arial", size=10, color="00B050")
DOWN_FONT = Font(name="Arial", size=10, color="FF0000")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)


def style_header_row(ws, row, num_cols):
    for col in range(1, num_cols + 1):
        c = ws.cell(row=row, column=col)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN_BORDER


def style_data_cell(cell, font=None):
    cell.font = font or DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = Alignment(vertical="center", wrap_text=True)


def load_or_create_workbook():
    if os.path.exists(EXCEL_PATH):
        try:
            return load_workbook(EXCEL_PATH)
        except Exception as e:
            log.warning(f"Cannot load Excel: {e}. Creating new.")
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def get_or_create_sheet(wb, name, headers):
    if name in wb.sheetnames:
        ws = wb[name]
        # Ensure headers are up to date
        for ci, h in enumerate(headers, 1):
            ws.cell(row=1, column=ci, value=h)
        style_header_row(ws, 1, len(headers))
        return ws
    ws = wb.create_sheet(name)
    for ci, h in enumerate(headers, 1):
        ws.cell(row=1, column=ci, value=h)
    style_header_row(ws, 1, len(headers))
    return ws


def update_excel(scan_results, scan_timestamp):
    os.makedirs(DATA_DIR, exist_ok=True)
    wb = load_or_create_workbook()
    today = scan_timestamp.strftime("%Y-%m-%d")
    now_str = scan_timestamp.strftime("%Y-%m-%d %H:%M")

    profile_headers = [
        "Data scanu", "Godzina", "Liczba ogłoszeń", "Zmiana vs poprzedni",
        "Crosscheck", "Tytuł", "Cena (zł)", "Zmiana ceny",
        "Data publikacji", "Data odświeżenia", "URL", "ID ogłoszenia"
    ]

    for pk, result in scan_results.items():
        ws = get_or_create_sheet(wb, pk[:31], profile_headers)

        prev_count = None
        for row in range(ws.max_row, 1, -1):
            val = ws.cell(row=row, column=3).value
            if val is not None and isinstance(val, (int, float)):
                prev_count = int(val)
                break

        cur = result["count"]
        ch = cur - prev_count if prev_count is not None else 0

        nr = ws.max_row + 1
        if nr > 2:
            nr += 1

        ws.cell(row=nr, column=1, value=today)
        ws.cell(row=nr, column=2, value=scan_timestamp.strftime("%H:%M"))
        ws.cell(row=nr, column=3, value=cur)
        change_cell = ws.cell(row=nr, column=4, value=ch)
        f = UP_FONT if ch > 0 else DOWN_FONT if ch < 0 else DATA_FONT
        style_data_cell(change_cell, f)
        ws.cell(row=nr, column=5, value=result.get("crosscheck", ""))
        for c in [1, 2, 3, 5]:
            style_data_cell(ws.cell(row=nr, column=c))

        for i, listing in enumerate(result["listings"]):
            row = nr + 1 + i
            pub, ref = parse_date_text(listing.get("date_text", ""))
            ws.cell(row=row, column=1, value=today)
            ws.cell(row=row, column=2, value=scan_timestamp.strftime("%H:%M"))
            ws.cell(row=row, column=6, value=listing["title"])
            ws.cell(row=row, column=7, value=listing["price"])
            ws.cell(row=row, column=9, value=pub or "")
            ws.cell(row=row, column=10, value=ref or "")
            ws.cell(row=row, column=11, value=listing["url"])
            ws.cell(row=row, column=12, value=listing["listing_id"])
            for c in range(1, 13):
                style_data_cell(ws.cell(row=row, column=c))

        for idx, w in enumerate([12, 8, 15, 15, 14, 50, 12, 12, 14, 14, 60, 15], 1):
            ws.column_dimensions[get_column_letter(idx)].width = w

    # Historia cen
    ph = ["Data", "Profil", "ID ogłoszenia", "Tytuł", "Cena (zł)", "Poprzednia cena", "Zmiana ceny", "URL"]
    ws_p = get_or_create_sheet(wb, "historia_cen", ph)

    prev_prices = {}
    for row in range(2, ws_p.max_row + 1):
        lid = ws_p.cell(row=row, column=3).value
        price = ws_p.cell(row=row, column=5).value
        if lid and price is not None:
            prev_prices[lid] = int(price) if isinstance(price, (int, float)) else None

    for pk, result in scan_results.items():
        for listing in result["listings"]:
            lid = listing["listing_id"]
            cp = listing["price"]
            pp = prev_prices.get(lid)
            pc = (cp - pp) if (pp is not None and cp is not None) else None

            r = ws_p.max_row + 1
            ws_p.cell(row=r, column=1, value=now_str)
            ws_p.cell(row=r, column=2, value=pk)
            ws_p.cell(row=r, column=3, value=lid)
            ws_p.cell(row=r, column=4, value=listing["title"])
            ws_p.cell(row=r, column=5, value=cp)
            ws_p.cell(row=r, column=6, value=pp)
            ws_p.cell(row=r, column=7, value=pc)
            ws_p.cell(row=r, column=8, value=listing["url"])
            for c in range(1, 9):
                cell = ws_p.cell(row=r, column=c)
                cf = DOWN_FONT if (c == 7 and pc and pc < 0) else UP_FONT if (c == 7 and pc and pc > 0) else DATA_FONT
                style_data_cell(cell, cf)
            if cp is not None:
                prev_prices[lid] = cp

    for idx, w in enumerate([18, 18, 15, 50, 12, 14, 12, 60], 1):
        ws_p.column_dimensions[get_column_letter(idx)].width = w

    # Podsumowanie
    if "podsumowanie" in wb.sheetnames:
        del wb["podsumowanie"]
    ws_s = wb.create_sheet("podsumowanie")
    sh = ["Profil", "Label", "Dzisiejsza liczba", "Poprzednia liczba", "Zmiana", "Crosscheck", "Data scanu"]
    for ci, h in enumerate(sh, 1):
        ws_s.cell(row=1, column=ci, value=h)
    style_header_row(ws_s, 1, len(sh))

    ri = 2
    for pk, result in scan_results.items():
        cur = result["count"]
        sn = pk[:31]
        prev = None
        if sn in wb.sheetnames:
            counts = []
            for r in range(2, wb[sn].max_row + 1):
                v = wb[sn].cell(row=r, column=3).value
                if v is not None and isinstance(v, (int, float)):
                    counts.append(int(v))
            if len(counts) >= 2:
                prev = counts[-2]

        ch = cur - prev if prev is not None else 0
        ws_s.cell(row=ri, column=1, value=pk)
        ws_s.cell(row=ri, column=2, value=PROFILES[pk]["label"])
        ws_s.cell(row=ri, column=3, value=cur)
        ws_s.cell(row=ri, column=4, value=prev)
        ws_s.cell(row=ri, column=5, value=ch)
        ws_s.cell(row=ri, column=6, value=result.get("crosscheck", ""))
        ws_s.cell(row=ri, column=7, value=now_str)
        for c in range(1, 8):
            cell = ws_s.cell(row=ri, column=c)
            f = UP_FONT if (c == 5 and ch > 0) else DOWN_FONT if (c == 5 and ch < 0) else DATA_FONT
            style_data_cell(cell, f)
        ri += 1

    for idx, w in enumerate([20, 30, 18, 18, 10, 16, 20], 1):
        ws_s.column_dimensions[get_column_letter(idx)].width = w

    wb.save(EXCEL_PATH)
    log.info(f"Excel saved: {EXCEL_PATH}")


# ─── JSON for Dashboard ─────────────────────────────────────────────────────

def load_existing_json():
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"profiles": {}, "scan_history": [], "last_scan": None}


def generate_dashboard_json(scan_results, scan_timestamp):
    data = load_existing_json()
    now_str = scan_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    today = scan_timestamp.strftime("%Y-%m-%d")
    data["last_scan"] = now_str

    scan_entry = {"timestamp": now_str, "date": today, "profiles": {}}

    for pk, result in scan_results.items():
        cfg = PROFILES[pk]
        if pk not in data["profiles"]:
            data["profiles"][pk] = {
                "label": cfg["label"],
                "url": cfg["url"],
                "is_category": cfg.get("is_category", False),
                "daily_counts": [],
                "current_listings": [],
                "archived_listings": [],
                "price_history": {},
            }

        pd_ = data["profiles"][pk]
        dc = pd_["daily_counts"]

        # Guard: don't archive if scan returned 0
        if result["count"] == 0:
            log.warning(f"[GUARD] {pk}: 0 listings returned, skipping archival")
            scan_entry["profiles"][pk] = {"count": 0, "crosscheck": result.get("crosscheck", "zero_guard")}
            continue

        today_entry = next((d for d in dc if d["date"] == today), None)
        if today_entry:
            if result["count"] >= today_entry["count"]:
                today_entry["count"] = result["count"]
                today_entry["timestamp"] = now_str
        else:
            prev_c = dc[-1]["count"] if dc else None
            ch = result["count"] - prev_c if prev_c is not None else 0

            # Median price of NEW listings today
            new_prices = []
            now_listings_map = {l["listing_id"]: l for l in result["listings"]}
            old_ids = {l["id"] for l in pd_.get("current_listings", [])}
            for listing in result["listings"]:
                if listing["listing_id"] not in old_ids and listing.get("price"):
                    new_prices.append(listing["price"])
            median_price = None
            if new_prices:
                new_prices.sort()
                mid = len(new_prices) // 2
                median_price = new_prices[mid] if len(new_prices) % 2 != 0 else (new_prices[mid - 1] + new_prices[mid]) // 2

            dc.append({
                "date": today,
                "count": result["count"],
                "change": ch,
                "timestamp": now_str,
                "median_price": median_price,
            })

        if len(dc) > 90:
            pd_["daily_counts"] = dc[-90:]

        current_ids = set()
        new_listings = []
        for listing in result["listings"]:
            pub, ref = parse_date_text(listing.get("date_text", ""))
            nl = {
                "id": listing["listing_id"],
                "title": listing["title"],
                "price": listing["price"],
                "price_text": listing.get("price_text", ""),
                "url": listing["url"],
                "published": pub,
                "refreshed": ref,
                "date_text": listing.get("date_text", ""),
                "image_url": listing.get("image_url", ""),
                "first_seen": now_str,
                "last_seen": now_str,
            }
            new_listings.append(nl)
            current_ids.add(listing["listing_id"])

        old_map = {l["id"]: l for l in pd_.get("current_listings", [])}
        for nl in new_listings:
            lid = nl["id"]
            if lid in old_map:
                old = old_map[lid]
                nl["first_seen"] = old.get("first_seen", now_str)
                old_price = old.get("price")
                new_price = nl.get("price")
                if old_price is not None and new_price is not None and old_price != new_price:
                    if lid not in pd_["price_history"]:
                        pd_["price_history"][lid] = []
                    pd_["price_history"][lid].append({
                        "date": now_str,
                        "old_price": old_price,
                        "new_price": new_price,
                        "change": new_price - old_price,
                    })
                    nl["previous_price"] = old_price
                    nl["price_change"] = new_price - old_price
                elif lid in pd_.get("price_history", {}):
                    h = pd_["price_history"][lid]
                    if h:
                        nl["previous_price"] = h[-1]["old_price"]
                        nl["price_change"] = (nl["price"] - h[-1]["old_price"]) if nl["price"] else None

        for old_l in pd_.get("current_listings", []):
            if old_l["id"] not in current_ids:
                old_l["archived_date"] = now_str
                pd_["archived_listings"].append(old_l)

        if len(pd_["archived_listings"]) > 500:
            pd_["archived_listings"] = pd_["archived_listings"][-500:]

        pd_["current_listings"] = new_listings
        scan_entry["profiles"][pk] = {
            "count": result["count"],
            "crosscheck": result.get("crosscheck", ""),
        }

    data["scan_history"].append(scan_entry)
    if len(data["scan_history"]) > 90:
        data["scan_history"] = data["scan_history"][-90:]

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Dashboard JSON saved: {JSON_PATH}")


# ─── Main ────────────────────────────────────────────────────────────────────

def run_scan():
    ts = datetime.now()
    log.info(f"{'='*60}")
    log.info(f"SZPERACZ MIESZKANIOWY — Scan started {ts.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")

    results = {}
    for pk, cfg in PROFILES.items():
        try:
            result = scrape_with_crosscheck(pk, cfg)
            results[pk] = result
            log.info(f"[OK] {pk}: {result['count']} listings ({result['crosscheck']})")
        except Exception as e:
            log.error(f"[ERROR] {pk}: {e}")
            results[pk] = {
                "listings": [], "count": 0, "header_count": None,
                "crosscheck": "error", "crosscheck_detail": str(e), "pages_scraped": 0,
            }
        time.sleep(random.uniform(2, 4))

    generate_dashboard_json(results, ts)
    update_excel(results, ts)

    log.info(f"{'='*60}")
    log.info(f"SZPERACZ MIESZKANIOWY — Scan completed {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")
    return results


if __name__ == "__main__":
    run_scan()
