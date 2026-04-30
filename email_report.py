#!/usr/bin/env python3
"""
SZPERACZ MIESZKANIOWY — Weekly email report.
Sends summary + Excel attachment every Monday.
"""

import smtplib
import json
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("szperacz-mieszkaniowy-email")

SENDER_EMAIL = "slowholidays00@gmail.com"
RECEIVER_EMAIL = "malczarski@gmail.com"
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
JSON_PATH = os.path.join(DATA_DIR, "dashboard_data.json")
EXCEL_PATH = os.path.join(DATA_DIR, "szperacz_mieszkaniowy.xlsx")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def build_report_html():
    if not os.path.exists(JSON_PATH):
        return "<p>Brak danych — plik JSON nie istnieje.</p>"

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    today = datetime.now()
    week_ago = today - timedelta(days=7)
    week_ago_str = week_ago.strftime("%Y-%m-%d")
    last_scan = data.get("last_scan", "Brak danych")

    html = f"""
    <html><head><style>
        body {{ font-family: Arial, sans-serif; color: #333; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1A3A6B; border-bottom: 3px solid #FFD700; padding-bottom: 10px; }}
        h2 {{ color: #1A3A6B; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th {{ background: #1A3A6B; color: #FFD700; padding: 10px 12px; text-align: left; font-size: 13px; }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #e0e0e0; font-size: 13px; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .up {{ color: #00B050; font-weight: bold; }}
        .down {{ color: #FF0000; font-weight: bold; }}
        .neutral {{ color: #666; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #888; font-size: 12px; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
        .badge-up {{ background: #e6f9ee; color: #00B050; }}
        .badge-down {{ background: #fde8e8; color: #FF0000; }}
        .badge-same {{ background: #f0f0f0; color: #666; }}
    </style></head><body><div class="container">
        <h1>🏠 SZPERACZ MIESZKANIOWY — Raport tygodniowy</h1>
        <p><strong>Okres:</strong> {week_ago.strftime('%d.%m.%Y')} – {today.strftime('%d.%m.%Y')}</p>
        <p><strong>Ostatni scan:</strong> {last_scan}</p>
        <h2>📊 Podsumowanie</h2>
        <table><tr><th>Profil</th><th>Aktualna liczba</th><th>Zmiana (7 dni)</th><th>Min</th><th>Max</th></tr>
    """

    for pk, pd in data.get("profiles", {}).items():
        label = pd.get("label", pk)
        dc = pd.get("daily_counts", [])
        week = [d for d in dc if d["date"] >= week_ago_str]

        current = week[-1]["count"] if week else 0
        first = week[0]["count"] if week else 0
        change = current - first
        vals = [d["count"] for d in week] if week else [0]

        if change > 0:
            ch_html = f'<span class="badge badge-up">+{change} ↑</span>'
        elif change < 0:
            ch_html = f'<span class="badge badge-down">{change} ↓</span>'
        else:
            ch_html = '<span class="badge badge-same">0 =</span>'

        html += f"<tr><td><strong>{label}</strong></td><td>{current}</td><td>{ch_html}</td><td>{min(vals)}</td><td>{max(vals)}</td></tr>"

    html += "</table>"

    for pk, pd in data.get("profiles", {}).items():
        label = pd.get("label", pk)
        listings = sorted(pd.get("current_listings", []), key=lambda x: x.get("first_seen", ""), reverse=True)

        html += f'<h2>🏠 {label} ({len(listings)} ogłoszeń)</h2>'
        html += '<table><tr><th>Tytuł</th><th>Cena</th><th>Zmiana ceny</th><th>Data publ.</th><th>Odświeżone</th></tr>'

        for l in listings[:50]:  # top 50
            price = f"{l['price']} zł" if l.get("price") else "—"
            pc = l.get("price_change")
            if pc and pc > 0:
                pc_html = f'<span class="up">+{pc} zł</span>'
            elif pc and pc < 0:
                pc_html = f'<span class="down">{pc} zł</span>'
            else:
                pc_html = '<span class="neutral">—</span>'

            url = l.get("url", "#")
            title = l.get("title", "—")
            pub = l.get("published", "—") or "—"
            ref = l.get("refreshed", "—") or "—"

            html += f'<tr><td><a href="{url}">{title}</a></td><td>{price}</td><td>{pc_html}</td><td>{pub}</td><td>{ref}</td></tr>'

        html += "</table>"

    html += f"""<div class="footer">
        <p>Wygenerowano automatycznie przez SZPERACZ MIESZKANIOWY • {today.strftime('%d.%m.%Y %H:%M')}</p>
        <p>W załączniku plik Excel z pełnymi danymi.</p>
    </div></div></body></html>"""

    return html


def send_report():
    if not EMAIL_PASSWORD:
        log.error("EMAIL_PASSWORD not set!")
        return False

    today = datetime.now()
    subject = f"🏠 SZPERACZ MIESZKANIOWY — Raport tygodniowy ({today.strftime('%d.%m.%Y')})"

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(build_report_html(), "html", "utf-8"))

    if os.path.exists(EXCEL_PATH):
        try:
            with open(EXCEL_PATH, "rb") as f:
                part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="szperacz_mieszkaniowy_{today.strftime("%Y%m%d")}.xlsx"')
                msg.attach(part)
            log.info("Excel attached.")
        except Exception as e:
            log.warning(f"Could not attach Excel: {e}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SENDER_EMAIL, EMAIL_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        log.info(f"Email sent to {RECEIVER_EMAIL}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP auth failed. Check EMAIL_PASSWORD (App Password required).")
        return False
    except Exception as e:
        log.error(f"Email failed: {e}")
        return False


if __name__ == "__main__":
    send_report()
