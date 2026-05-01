"""
Scrapes all historical lottery result PDFs from lotterysambadresult.in/oldresult.html.
Downloads every PDF into input_history/pdfs/ and writes a CSV index.

Page structure (confirmed):
  - 11 <table> blocks, one per month
  - Row 0 of each table: header  "1:00 PM | 6:00 PM | 8:00 PM"
  - Rows 1-N: three <td> cells, each containing an <a> link to a PDF
"""
import csv
import re
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")  # suppress LibreSSL warning

INDEX_URL = "https://lotterysambadresult.in/oldresult.html"
OUT_DIR   = Path(__file__).parent / "input_history"
PDF_DIR   = OUT_DIR / "pdfs"
INDEX_CSV = OUT_DIR / "index.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

DRAW_TIMES = ["1:00 PM", "6:00 PM", "8:00 PM"]

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3,    "april": 4,
    "may": 5,      "june": 6,    "july": 7,     "august": 8,
    "september":9, "october":10, "november": 11,"december": 12,
}


_TYPOS = {"feburary": "february", "febuary": "february", "augst": "august"}

def parse_date(text):
    parts = text.strip().split()
    if len(parts) != 3:
        return text.strip()
    p = [_TYPOS.get(x.lower().rstrip(','), x.lower().rstrip(',')) for x in parts]
    # Try "DD Month YYYY"
    try:
        day, month, year = int(p[0]), MONTH_MAP.get(p[1], 0), int(p[2])
        if month:
            return datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    # Try "Month DD YYYY"
    try:
        month, day, year = MONTH_MAP.get(p[0], 0), int(p[1]), int(p[2])
        if month:
            return datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return text.strip()


def extract_entries(html):
    soup    = BeautifulSoup(html, "html.parser")
    entries = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            # Skip header rows
            row_text = row.get_text(strip=True)
            if re.search(r"1:00\s*PM", row_text, re.I):
                continue

            for col_idx, cell in enumerate(cells[:3]):
                a = cell.find("a", href=re.compile(r"\.pdf$"))
                if not a:
                    continue
                entries.append({
                    "date":      parse_date(a.get_text(strip=True)),
                    "draw_time": DRAW_TIMES[col_idx],
                    "pdf_url":   a["href"].strip(),
                })

    return entries


def download_pdf(url, dest, session):
    if dest.exists():
        return "skip"
    try:
        r = session.get(url, headers=HEADERS, timeout=30, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        time.sleep(0.3)
        return "ok"
    except Exception as e:
        return f"error: {e}"


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching index page …")
    r = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    entries = extract_entries(r.text)
    if not entries:
        print("ERROR: No entries extracted — page structure may have changed.")
        sys.exit(1)

    print(f"Extracted {len(entries)} result entries across {len(entries)//3} dates (approx).")
    print(f"Downloading PDFs to {PDF_DIR} …\n")

    session = requests.Session()
    rows    = []

    for i, e in enumerate(entries, 1):
        filename = e["pdf_url"].split("/")[-1]
        dest     = PDF_DIR / filename
        status   = download_pdf(e["pdf_url"], dest, session)

        rows.append({
            "date":       e["date"],
            "draw_time":  e["draw_time"],
            "pdf_url":    e["pdf_url"],
            "local_file": f"pdfs/{filename}",
            "status":     status,
        })

        if i % 30 == 0 or i == len(entries):
            print(f"  [{i:4d}/{len(entries)}]  {e['date']}  {e['draw_time']}  → {status}")

    with open(INDEX_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "draw_time", "pdf_url", "local_file", "status"]
        )
        writer.writeheader()
        writer.writerows(rows)

    ok    = sum(1 for r in rows if r["status"] == "ok")
    skip  = sum(1 for r in rows if r["status"] == "skip")
    error = sum(1 for r in rows if r["status"].startswith("error"))
    print(f"\n{'─'*50}")
    print(f"Downloaded : {ok}")
    print(f"Skipped    : {skip}  (already existed)")
    print(f"Errors     : {error}")
    print(f"Index CSV  : {INDEX_CSV}")


if __name__ == "__main__":
    main()
