"""
Parses all PDFs in input_history/pdfs/, extracts winning numbers per prize tier,
and writes input_history/results.csv.

Prize structure (confirmed from PDF inspection):
  1st Prize  : 1 × 5-digit number  (unique ticket with series code, e.g. "83K")
  2nd Prize  : 10 × 5-digit numbers
  3rd Prize  : 10 × 4-digit numbers  (above "5th Prize Amount" line)
  4th Prize  : 10 × 4-digit numbers  (above "5th Prize Amount" line)
  5th Prize  : 100 × 4-digit numbers (below "5th Prize Amount" line)

Classification by digit length:
  5-digit → "High-value" (1st / 2nd prize)
  4-digit → "Standard"   (3rd / 4th / 5th prize)
"""
import csv
import os
import re
import sys
import warnings
from pathlib import Path

import pdfplumber

warnings.filterwarnings("ignore")

PDF_DIR    = Path("input_history/pdfs")
INDEX_CSV  = Path("input_history/index.csv")
OUT_CSV    = Path("input_history/results.csv")

PRIZE_LABELS = {1: "1st Prize", 2: "2nd Prize", 3: "3rd Prize",
                4: "4th Prize", 5: "5th Prize"}
DIGIT_CATEGORY = {5: "High-value (5-digit)", 4: "Standard (4-digit)"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _numbers(text, n):
    """All n-digit standalone numbers in text, preserving order."""
    return re.findall(rf'\b(\d{{{n}}})\b', text)


def _dedupe_ordered(seq):
    """Remove consecutive duplicates while preserving order."""
    out = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def parse_text(text):
    """
    Returns a dict:
      lottery_name, draw_number, draw_date_pdf, series,
      prizes: list of (rank, label, number, digit_len)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ── Lottery name ─────────────────────────────────────────────────────────
    lottery_name = ""
    for i, line in enumerate(lines):
        if re.search(r'\bLOTTERY\b|\bLOTTERIES\b', line, re.I):
            # Include the line before if it looks like a name (no digits)
            if i > 0 and not re.search(r'\d', lines[i - 1]):
                lottery_name = f"{lines[i-1]} {line}".strip()
            else:
                lottery_name = line.strip()
            break

    # ── Draw date and draw number ─────────────────────────────────────────────
    draw_date   = ""
    draw_number = ""
    date_pat = re.compile(r'\b(\d{2}/\d{2}/\d{2})\b')

    for line in lines:
        m = date_pat.search(line)
        if m:
            draw_date = m.group(1)
            # Draw number may be on same line: "30 28/04/26" → "30"
            rest = line[:m.start()].strip()
            if re.fullmatch(r'\d+', rest):
                draw_number = rest
            break

    # If draw number not found yet, look at the line after the date line
    if not draw_number:
        for i, line in enumerate(lines):
            if date_pat.search(line) and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if re.fullmatch(r'\d+', nxt):
                    draw_number = nxt
                break

    # ── Series + 1st prize ────────────────────────────────────────────────────
    series = ""
    series_pat = re.compile(r'\b([A-Z0-9]{2,3})\s+(\d{5})\b')
    for line in lines:
        m = series_pat.search(line)
        if m and not re.search(r'LOTTERY|PRIZE|SELLER|SOLD|TDS|AMOUNT', line, re.I):
            series = m.group(1)
            break

    # ── Split text at "5th Prize Amount" marker ───────────────────────────────
    marker_match = re.search(r'5th\s+Prize', text, re.I)
    if marker_match:
        text_high = text[:marker_match.start()]
        text_low  = text[marker_match.end():]
    else:
        text_high = text
        text_low  = ""

    # Trim footer (TDS notice, date stamps) from the 5th-prize block
    tds_cut = re.search(r'\bTDS\b|\bw\.e\.f\b', text_low, re.I)
    if tds_cut:
        text_low = text_low[:tds_cut.start()]

    # ── Extract numbers ───────────────────────────────────────────────────────
    five_digit  = _dedupe_ordered(_numbers(text_high, 5))
    four_high   = _numbers(text_high, 4)
    four_low    = _numbers(text_low,  4)

    first_prize  = five_digit[:1]          # 1 number
    second_prize = five_digit[1:11]        # up to 10
    third_prize  = four_high[:10]          # first 10 four-digit
    fourth_prize = four_high[10:20]        # next 10 four-digit
    fifth_prize  = four_low                # all remaining four-digit

    prizes = []
    for n in first_prize:
        prizes.append((1, PRIZE_LABELS[1], n, 5))
    for n in second_prize:
        prizes.append((2, PRIZE_LABELS[2], n, 5))
    for n in third_prize:
        prizes.append((3, PRIZE_LABELS[3], n, 4))
    for n in fourth_prize:
        prizes.append((4, PRIZE_LABELS[4], n, 4))
    for n in fifth_prize:
        prizes.append((5, PRIZE_LABELS[5], n, 4))

    return {
        "lottery_name":  lottery_name,
        "draw_number":   draw_number,
        "draw_date_pdf": draw_date,
        "series":        series,
        "prizes":        prizes,
    }


def infer_draw_time_from_filename(fname):
    """
    Heuristic for pre-existing named PDFs (DD/ED/ND prefix).
    DD* → 1:00 PM,  ED* → 6:00 PM,  ND* → 8:00 PM
    """
    prefix = fname[:2].upper()
    return {"DD": "1:00 PM", "ED": "6:00 PM", "ND": "8:00 PM",
            "MD": "1:00 PM"}.get(prefix, "")


def infer_date_from_filename(fname):
    """
    DD010625.pdf → 2025-06-01
    Format assumed: XX DDMMYY
    """
    m = re.search(r'(\d{2})(\d{2})(\d{2})', fname)
    if not m:
        return ""
    day, mon, yr = m.groups()
    return f"20{yr}-{mon}-{day}"


def pdf_to_rows(pdf_path, date="", draw_time=""):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(
                (p.extract_text() or "") for p in pdf.pages
            )
    except Exception as e:
        return [], f"pdf_error: {e}"

    if not text.strip():
        return [], "empty_text"

    parsed = parse_text(text)

    fname = pdf_path.name
    rows  = []
    for rank, label, number, digit_len in parsed["prizes"]:
        rows.append({
            "date":            date or parsed["draw_date_pdf"],
            "draw_time":       draw_time,
            "lottery_name":    parsed["lottery_name"],
            "draw_number":     parsed["draw_number"],
            "draw_date_pdf":   parsed["draw_date_pdf"],
            "series":          parsed["series"] if rank == 1 else "",
            "prize_rank":      rank,
            "prize_label":     label,
            "winning_number":  number,
            "digit_length":    digit_len,
            "prize_category":  DIGIT_CATEGORY.get(digit_len, ""),
            "source_pdf":      fname,
        })

    return rows, "ok"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Build lookup: filename → (date, draw_time) from index.csv
    lookup = {}
    with open(INDEX_CSV) as f:
        for row in csv.DictReader(f):
            fname = row["local_file"].split("/")[-1]
            lookup[fname] = (row["date"], row["draw_time"])

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    print(f"PDFs to parse: {len(pdf_files)}")

    all_rows = []
    errors   = []

    for i, pdf_path in enumerate(pdf_files, 1):
        fname = pdf_path.name
        date, draw_time = lookup.get(fname, ("", ""))

        # For pre-existing named PDFs not in index
        if not date:
            date      = infer_date_from_filename(fname)
            draw_time = infer_draw_time_from_filename(fname)

        rows, status = pdf_to_rows(pdf_path, date, draw_time)
        all_rows.extend(rows)

        if status != "ok":
            errors.append((fname, status))

        if i % 100 == 0 or i == len(pdf_files):
            print(f"  [{i:4d}/{len(pdf_files)}]  rows so far: {len(all_rows)}")

    # Write CSV
    fieldnames = ["date", "draw_time", "lottery_name", "draw_number",
                  "draw_date_pdf", "series", "prize_rank", "prize_label",
                  "winning_number", "digit_length", "prize_category", "source_pdf"]

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nTotal rows written : {len(all_rows)}")
    print(f"Parse errors       : {len(errors)}")
    if errors:
        for fname, err in errors[:10]:
            print(f"  {fname}: {err}")
    print(f"Output             : {OUT_CSV}")


if __name__ == "__main__":
    main()
