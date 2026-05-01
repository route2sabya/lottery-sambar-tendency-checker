# Lottery Sambad Tendency Checker

Flask web app that scores lottery ticket numbers against historical Lottery Sambad draw data.

## Stack
- **Backend**: Python 3.11, Flask, Gunicorn (1 worker)
- **Frontend**: Vanilla JS, dark-themed HTML/CSS, SVG gauge
- **Data**: `input_history/results.csv` (15MB, 128K+ rows), `input_history/index.csv`
- **Hosting**: Fly.io (`lottery-sambad-checker` app, Mumbai region, 512MB VM)
- **Repo**: https://github.com/route2sabya/lottery-sambar-tendency-checker

## Key Files
| File | Purpose |
|---|---|
| `app.py` | Flask routes + background update thread (polls every 2h) |
| `scorer.py` | Loads CSV, builds signal tables, scores numbers |
| `update_data.py` | Fetches new PDFs from site, parses, appends to CSVs |
| `scrape_history.py` | Scrapes lotterysambadresult.in for PDF links |
| `parse_pdfs.py` | Extracts winning numbers from PDFs into CSV rows |
| `templates/index.html` | Full frontend (search, gauge, heatmap, hot numbers, ad zones) |

## Input Formats
- `1234` → 4-digit (prizes 3/4/5)
- `12345` → 5-digit (prizes 1/2)
- `83K90495` → 8-char series+5digit (1st prize)

## Scoring Signals
- **digit_ratio** — positional digit frequency bias
- **decay_ratio** — time-decayed appearance frequency
- **tier_ratio** — prize-tier-specific count
- Weights: digit 45% | decay 35% | tier 20%

## Daily Update Flow
1. `update_data.py` scrapes `oldresult.html` for new PDF filenames
2. Downloads new PDFs → parses → appends rows to `results.csv` + `index.csv`
3. Sets `scorer = None` → reloaded on next request
4. Source domain changed from `lotterysambadresult.in` → `lottery-sambad.com.co`
5. Matching is by **filename** (not URL) to survive future domain changes

## Common Commands
```bash
# Run locally
.venv/bin/python app.py

# Fetch latest draws manually
.venv/bin/python update_data.py

# Deploy to Fly.io
fly deploy

# Logs
fly logs
```

## Ad Zones
4 placeholder zones in `templates/index.html` — replace `.ad-placeholder` divs with AdSense `<ins>` tags:
- Top leaderboard (728×90)
- Left rail (160×600) — visible ≥1220px only
- Right rail (160×600) — visible ≥1220px only
- Bottom leaderboard (728×90)

## Git
- Committer: Sabyasachi Purkayastha <route2sabya@gmail.com>
- No Claude co-author lines in commits
