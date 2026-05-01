import threading
import time

from flask import Flask, render_template, request, jsonify
from scorer import get_scorer

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


if __name__ == "__main__":
    scorer = get_scorer()      # pre-warm on direct run
    app.run(port=6001, debug=False)
