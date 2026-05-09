import threading
import time

from flask import Flask, render_template, request, jsonify, Response, abort
from scorer import get_scorer

DRAW_SLUGS = {'1pm': '1:00 PM', '6pm': '6:00 PM', '8pm': '8:00 PM'}
DRAW_LABELS = {'1pm': 'Day (1 PM)', '6pm': 'Evening (6 PM)', '8pm': 'Night (8 PM)'}
PRIZE_NAMES = {'1': '1st Prize', '2': '2nd Prize', '3': '3rd Prize', '4': '4th Prize', '5': '5th Prize'}
BASE_URL = 'https://lottery-sambad-checker.rentowise.in'

app    = Flask(__name__)
scorer = None   # lazy-loaded on first request so startup is fast in dev


def _s():
    global scorer
    if scorer is None:
        scorer = get_scorer()
    return scorer


def _updater_loop():
    """Background thread: check for new PDFs every 2 hours, reload scorer if data changed."""
    time.sleep(300)           # wait 5 min after startup before first check
    while True:
        try:
            from update_data import run_update
            added = run_update(verbose=True)
            if added > 0:
                global scorer
                scorer = None     # next request triggers reload from updated CSV
                print(f"[updater] scorer queued for reload ({added} new rows)", flush=True)
        except Exception as exc:
            print(f"[updater] error: {exc}", flush=True)
        time.sleep(2 * 3600)  # poll every 2 hours


threading.Thread(target=_updater_loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/score")
def api_score():
    number = request.args.get("number", "").strip().upper()
    if not number:
        return jsonify({"error": "Provide a number parameter."}), 400
    if len(number) in (4, 5):
        if not number.isdigit():
            return jsonify({"error": "4- or 5-digit input must contain digits only."}), 400
    elif len(number) == 8:
        if not (number[:3].isalnum() and number[3:].isdigit()):
            return jsonify({"error": "8-character input: first 3 chars = series code, last 5 = digits (e.g. 83K90495)."}), 400
    else:
        return jsonify({"error": f"Enter a 4-digit, 5-digit, or 8-character (series+5digit) number (got {len(number)})."}), 400
    return jsonify(_s().score(number))


@app.route("/api/hot-numbers")
def api_hot():
    prize = request.args.get("prize", "5")
    if prize not in "12345":
        return jsonify({"error": "prize must be 1–5"}), 400
    top_n = min(int(request.args.get("top", 20)), 50)
    return jsonify(_s().hot_numbers(prize=prize, top_n=top_n))


@app.route("/api/stats")
def api_stats():
    s = _s()
    return jsonify({
        "sessions_total": s.N,
        "date_range": {
            "first": s.session_order[0][0],
            "last":  s.session_order[-1][0],
        },
    })


@app.route("/hot/prize-<prize>")
def hot_prize_page(prize):
    if prize not in '12345':
        abort(404)
    s = _s()
    numbers = s.hot_numbers(prize=prize, top_n=30)
    return render_template('hot_prize.html', prize=prize,
                           prize_name=PRIZE_NAMES[prize], numbers=numbers,
                           sessions_total=s.N, draw_times=DRAW_SLUGS,
                           draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/draw/<slug>")
def draw_session_page(slug):
    if slug not in DRAW_SLUGS:
        abort(404)
    draw_time = DRAW_SLUGS[slug]
    s = _s()
    recent_dates = [d for d in s.all_dates if draw_time in s.date_map[d]][:20]
    recent_results = [{'date': d, 'entries': s.date_map[d][draw_time]} for d in recent_dates]
    hot = s.hot_numbers(prize='5', top_n=20)
    return render_template('draw_session.html', slug=slug, draw_time=draw_time,
                           label=DRAW_LABELS[slug], recent_results=recent_results,
                           hot=hot, sessions_total=s.N,
                           draw_times=DRAW_SLUGS, draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/series/<code>")
def series_page(code):
    code = code.upper()
    s = _s()
    if code not in s.series_freq:
        abort(404)
    sfr  = s._series_freq_ratio(code)
    sdr  = s._series_decay_ratio(code)
    comp = 0.40 * sfr + 0.35 * sdr + 0.25
    history = s.series_history.get(code, [])
    last_won = history[0]['date'] if history else None
    gap = None
    if history:
        last_key = (history[0]['date'], history[0]['draw_time'])
        if last_key in s.sess_idx:
            gap = s.N - 1 - s.sess_idx[last_key]
    return render_template('series.html', code=code,
                           score=min(300, round(comp * 100)),
                           appearances=s.series_freq[code],
                           freq_ratio=round(sfr, 3),
                           decay_ratio=round(sdr, 3),
                           history=history, last_won=last_won,
                           gap=gap, sessions_total=s.N,
                           n_series=s.n_unique_series,
                           draw_times=DRAW_SLUGS, draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/number/<number>")
def number_page(number):
    number = number.upper().strip()
    s = _s()
    data = s.score(number)
    if 'error' in data:
        abort(404)
    return render_template('number.html', data=data, number=number,
                           draw_times=DRAW_SLUGS, draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/results/")
def results_index():
    s = _s()
    return render_template('results_index.html', dates=s.all_dates[:60],
                           sessions_total=s.N,
                           draw_times=DRAW_SLUGS, draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/results/<date>")
def results_date_page(date):
    s = _s()
    if date not in s.date_map:
        abort(404)
    draws = [{'draw_time': dt, 'slug': next((k for k, v in DRAW_SLUGS.items() if v == dt), dt),
              'entries': s.date_map[date][dt]}
             for dt in sorted(s.date_map[date].keys())]
    prev_date = next((d for d in s.all_dates if d < date), None)
    next_date = next((d for d in reversed(s.all_dates) if d > date), None)
    return render_template('results_date.html', date=date, draws=draws,
                           prev_date=prev_date, next_date=next_date,
                           sessions_total=s.N,
                           draw_times=DRAW_SLUGS, draw_labels=DRAW_LABELS, prize_names=PRIZE_NAMES)


@app.route("/sitemap.xml")
def sitemap():
    s = _s()
    urls = [
        (BASE_URL + '/',          'daily',   '1.0'),
        (BASE_URL + '/results/',  'daily',   '0.9'),
    ]
    for p in '12345':
        urls.append((f'{BASE_URL}/hot/prize-{p}', 'daily', '0.8'))
    for slug in DRAW_SLUGS:
        urls.append((f'{BASE_URL}/draw/{slug}', 'daily', '0.8'))
    for date in s.all_dates:
        urls.append((f'{BASE_URL}/results/{date}', 'weekly', '0.7'))
    for code in s.all_series_list:
        urls.append((f'{BASE_URL}/series/{code}', 'weekly', '0.6'))
    for num in s.all_numbers:
        urls.append((f'{BASE_URL}/number/{num}', 'weekly', '0.5'))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, pri in urls:
        lines.append(f'  <url><loc>{loc}</loc><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')
    lines.append('</urlset>')
    return Response('\n'.join(lines), mimetype='application/xml')


@app.route("/robots.txt")
def robots():
    txt = "User-agent: *\nAllow: /\nSitemap: https://lottery-sambad-checker.rentowise.in/sitemap.xml"
    return Response(txt, mimetype="text/plain")


if __name__ == "__main__":
    scorer = get_scorer()      # pre-warm on direct run
    app.run(port=6001, debug=False)
