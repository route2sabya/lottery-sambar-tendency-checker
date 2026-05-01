"""
Fetches new lottery result PDFs from lotterysambadresult.in that are not yet
recorded in input_history/index.csv, parses them, and appends new rows to
input_history/results.csv.

Standalone:   python update_data.py
Import:       from update_data import run_update; rows_added = run_update()
"""
import csv
import sys
import warnings
from pathlib import Path

import requests

warnings.filterwarnings("ignore")

from scrape_history import (
    extract_entries, download_pdf, HEADERS,
    INDEX_URL, PDF_DIR, INDEX_CSV,
)
from parse_pdfs import pdf_to_rows, OUT_CSV

_RESULT_FIELDS = [
    "date", "draw_time", "lottery_name", "draw_number",
    "draw_date_pdf", "series", "prize_rank", "prize_label",
    "winning_number", "digit_length", "prize_category", "source_pdf",
]
_INDEX_FIELDS = ["date", "draw_time", "pdf_url", "local_file", "status"]


def _load_known_filenames() -> set:
    """Match by filename so domain changes don't cause re-downloads."""
    if not INDEX_CSV.exists():
        return set()
    with open(INDEX_CSV) as f:
        return {row["local_file"].split("/")[-1] for row in csv.DictReader(f)}


def _append(path: Path, rows: list, fields: list):
    mode = "a" if path.exists() else "w"
    with open(path, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if mode == "w":
            w.writeheader()
        w.writerows(rows)


def run_update(verbose: bool = True) -> int:
    """
    Scrape the results page, download any PDFs not already in index.csv,
    parse them, and append to results.csv + index.csv.

    Returns the number of new result rows appended (0 = nothing new).
    """
    def log(*a):
        if verbose:
            print(*a, flush=True)

    log("Checking for new draws …")
    try:
        r = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        log(f"  ERROR fetching index page: {exc}")
        return 0

    entries = extract_entries(r.text)
    if not entries:
        log("  No entries found — page structure may have changed.")
        return 0

    known = _load_known_filenames()
    new   = [e for e in entries if e["pdf_url"].split("/")[-1] not in known]

    if not new:
        log("  Already up to date.")
        return 0

    log(f"  {len(new)} new draw(s) to fetch.")
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    session     = requests.Session()
    index_rows  = []
    result_rows = []

    for e in new:
        filename = e["pdf_url"].split("/")[-1]
        dest     = PDF_DIR / filename
        status   = download_pdf(e["pdf_url"], dest, session)

        index_rows.append({**e, "local_file": f"pdfs/{filename}", "status": status})

        if status != "ok":
            log(f"  ✗  {e['date']}  {e['draw_time']}  [{status}]")
            continue

        rows, ps = pdf_to_rows(dest, e["date"], e["draw_time"])
        if ps != "ok":
            log(f"  ✗  {e['date']}  {e['draw_time']}  parse error: {ps}")
        else:
            result_rows.extend(rows)
            log(f"  ✓  {e['date']}  {e['draw_time']}  +{len(rows)} rows")

    if result_rows:
        _append(OUT_CSV,    result_rows, _RESULT_FIELDS)
    if index_rows:
        _append(INDEX_CSV,  index_rows,  _INDEX_FIELDS)

    log(f"Done — {len(result_rows)} new result rows added.")
    return len(result_rows)


if __name__ == "__main__":
    sys.exit(0 if run_update() >= 0 else 1)
