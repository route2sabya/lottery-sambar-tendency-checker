"""
Lottery tendency scorer.
Precomputes signal tables from results.csv at startup, then answers
score(number) queries in O(1).

Input routing:
  4-digit number   → prizes 3 / 4 / 5
  5-digit number   → prizes 1 / 2  (2nd prize pool)
  8-char SSSNNNNN  → 1st prize  (SSS = series, NNNNN = 5-digit number)

Signals (all expressed as ratio vs. random-baseline = 1.0):
  digit_ratio   — positional digit frequency bias
  decay_ratio   — time-decayed appearance frequency
  tier_ratio    — prize-tier-specific appearance count
  series_ratio  — how often this series wins 1st prize  [1st prize only]
  series_decay  — time-decayed series frequency         [1st prize only]

Weights:
  4/5-digit : digit 45 % | decay 35 % | tier 20 %
  1st prize : digit 25 % | series 40 % | series_decay 35 %
"""
import csv
import math
import os
from collections import defaultdict, Counter
from datetime import datetime

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "input_history", "results.csv")

HALF_LIFE   = 90          # sessions (~1 month at 3 draws/day)
DECAY_K     = math.log(2) / HALF_LIFE

WEIGHTS = {"digit": 0.45, "decay": 0.35, "tier": 0.20}

PRIZE_DRAWS = {"1": 1, "2": 10, "3": 10, "4": 10, "5": 100}
PRIZE_POOL  = {"1": 100_000, "2": 100_000, "3": 10_000,
               "4": 10_000,  "5": 10_000}

# Prize tiers relevant for 4-digit and 5-digit numbers
DIGIT_TIERS = {4: ["3", "4", "5"], 5: ["1", "2"]}


class LotteryScorer:
    def __init__(self, results_csv: str = RESULTS_CSV):
        self._load(results_csv)

    # ── Loading & precomputation ─────────────────────────────────────────────

    def _load(self, path: str):
        rows = sorted(
            csv.DictReader(open(path)),
            key=lambda r: (r["date"], r["draw_time"]),
        )

        self.session_order = sorted({(r["date"], r["draw_time"]) for r in rows})
        self.sess_idx      = {k: i for i, k in enumerate(self.session_order)}
        self.N             = len(self.session_order)

        self._build_digit_tables(rows)
        self._build_decay_tables(rows)
        self._build_tier_tables(rows)
        self._build_history(rows)
        self._build_expected_decay()
        self._build_series_tables(rows)
        self._build_date_map(rows)

    def _build_digit_tables(self, rows):
        """pos_prob[digit_len][pos][digit] = observed probability"""
        raw = {4: [Counter() for _ in range(4)],
               5: [Counter() for _ in range(5)]}
        total = {4: 0, 5: 0}

        for r in rows:
            num = r["winning_number"]
            n   = len(num)
            if n not in raw:
                continue
            for pos, d in enumerate(num):
                raw[n][pos][d] += 1
            total[n] += 1

        self.digit_prob = {}
        for n in (4, 5):
            self.digit_prob[n] = []
            for pos in range(n):
                t = sum(raw[n][pos].values()) or 1
                self.digit_prob[n].append(
                    {str(d): raw[n][pos].get(str(d), 0) / t for d in range(10)}
                )

    def _build_decay_tables(self, rows):
        """decay_score[prize][number] = Σ exp(-k * age_in_sessions)"""
        self.decay_score = {p: defaultdict(float) for p in "12345"}
        for r in rows:
            prize = r["prize_rank"]
            num   = r["winning_number"]
            idx   = self.sess_idx[(r["date"], r["draw_time"])]
            age   = self.N - 1 - idx
            self.decay_score[prize][num] += math.exp(-DECAY_K * age)

    def _build_tier_tables(self, rows):
        """tier_freq[prize][number] = raw appearance count"""
        self.tier_freq = {p: Counter() for p in "12345"}
        for r in rows:
            self.tier_freq[r["prize_rank"]][r["winning_number"]] += 1

    def _build_history(self, rows):
        """history[number] = list of {date, draw_time, prize_label, prize_rank}"""
        hist = defaultdict(list)
        for r in rows:
            hist[r["winning_number"]].append({
                "date":        r["date"],
                "draw_time":   r["draw_time"],
                "prize_rank":  r["prize_rank"],
                "prize_label": r["prize_label"],
                "lottery":     r["lottery_name"],
            })
        # Sort each list newest-first
        self.history_map = {
            num: sorted(v, key=lambda x: (x["date"], x["draw_time"]), reverse=True)
            for num, v in hist.items()
        }

    def _build_series_tables(self, rows):
        """
        For 1st prize rows only, build:
          series_freq[series]        — raw appearance count
          series_decay[series]       — time-decayed score
          series_history[series]     — list of {date, draw_time, winning_number, lottery}
        """
        self.series_freq    = Counter()
        self.series_decay   = defaultdict(float)
        self.series_history = defaultdict(list)

        for r in rows:
            if r["prize_rank"] != "1":
                continue
            s = r["series"].strip().upper()
            if not s:
                continue
            idx = self.sess_idx[(r["date"], r["draw_time"])]
            age = self.N - 1 - idx
            self.series_freq[s]  += 1
            self.series_decay[s] += math.exp(-DECAY_K * age)
            self.series_history[s].append({
                "date":           r["date"],
                "draw_time":      r["draw_time"],
                "winning_number": r["winning_number"],
                "lottery":        r["lottery_name"],
            })

        # Sort each series history newest-first
        for s in self.series_history:
            self.series_history[s].sort(
                key=lambda x: (x["date"], x["draw_time"]), reverse=True
            )

        # Pre-compute expected series decay (uniform assumption)
        # Each session picks 1 series from ~487 possible → prob = 1/N_series per session
        n_series = max(len(self.series_freq), 1)
        geo_sum  = (1 - math.exp(-DECAY_K * self.N)) / (1 - math.exp(-DECAY_K))
        self.expected_series_decay = geo_sum / n_series
        self.n_unique_series = n_series

    def _build_date_map(self, rows):
        """date_map[date][draw_time] = sorted list of result dicts"""
        dm = defaultdict(lambda: defaultdict(list))
        for r in rows:
            dm[r["date"]][r["draw_time"]].append({
                "prize_rank":    r["prize_rank"],
                "prize_label":   r["prize_label"],
                "lottery_name":  r["lottery_name"],
                "series":        r["series"],
                "winning_number": r["winning_number"],
            })
        # Sort entries within each slot by prize rank
        for date in dm:
            for dt in dm[date]:
                dm[date][dt].sort(key=lambda x: x["prize_rank"])
        self.date_map        = dm
        self.all_dates       = sorted(dm.keys(), reverse=True)
        self.draw_times      = sorted({r["draw_time"] for r in rows if r["draw_time"] != "draw_time"})
        self.all_numbers     = sorted(self.history_map.keys())
        self.all_series_list = sorted(self.series_freq.keys())

    def _build_expected_decay(self):
        """
        expected_decay[prize] = E[decay_score] for a random number in that pool.
        = (draws_per_session / pool_size) × Σ_{age=0}^{N-1} exp(-k × age)
        """
        geo_sum = (1 - math.exp(-DECAY_K * self.N)) / (1 - math.exp(-DECAY_K))
        self.expected_decay = {
            p: (PRIZE_DRAWS[p] / PRIZE_POOL[p]) * geo_sum
            for p in "12345"
        }

    # ── Scoring ──────────────────────────────────────────────────────────────

    def _digit_ratio(self, number: str) -> float:
        n = len(number)
        if n not in self.digit_prob:
            return 1.0
        prod = 1.0
        for pos, d in enumerate(number):
            prod *= self.digit_prob[n][pos].get(d, 0.001)
        expected = 0.1 ** n
        return prod / expected

    def _decay_ratio(self, number: str, prize: str) -> float:
        actual   = self.decay_score[prize].get(number, 0.0)
        expected = self.expected_decay[prize]
        return actual / expected if expected else 0.0

    def _tier_ratio(self, number: str, prize: str) -> float:
        actual   = self.tier_freq[prize].get(number, 0)
        expected = PRIZE_DRAWS[prize] / PRIZE_POOL[prize] * self.N
        return actual / expected if expected else 0.0

    def _composite(self, dr, dcr, tr) -> float:
        return (WEIGHTS["digit"] * dr +
                WEIGHTS["decay"] * dcr +
                WEIGHTS["tier"]  * tr)

    # ── Series scoring (1st prize) ────────────────────────────────────────────

    def _series_freq_ratio(self, series: str) -> float:
        expected = self.N / self.n_unique_series   # avg appearances per series
        actual   = self.series_freq.get(series, 0)
        return actual / expected if expected else 0.0

    def _series_decay_ratio(self, series: str) -> float:
        actual   = self.series_decay.get(series, 0.0)
        expected = self.expected_series_decay
        return actual / expected if expected else 0.0

    def _score_first_prize(self, series: str, number: str) -> dict:
        """Score an 8-character 1st prize input: SSS (series) + NNNNN (5-digit)."""
        series = series.upper()
        number = number.zfill(5)

        digit_r        = self._digit_ratio(number)       # 5-digit positional bias
        series_freq_r  = self._series_freq_ratio(series)
        series_decay_r = self._series_decay_ratio(series)

        # Composite (1st prize weights)
        composite = (0.25 * digit_r +
                     0.40 * series_freq_r +
                     0.35 * series_decay_r)

        # Series metadata
        s_count   = self.series_freq.get(series, 0)
        s_hist    = self.series_history.get(series, [])
        s_last    = s_hist[0]["date"] if s_hist else None
        s_gap     = None
        if s_hist:
            last_key = (s_hist[0]["date"], s_hist[0]["draw_time"])
            if last_key in self.sess_idx:
                s_gap = self.N - 1 - self.sess_idx[last_key]

        expected_per_series = round(self.N / self.n_unique_series, 2)

        # Rank this series among all known series
        sorted_counts = sorted(self.series_freq.values(), reverse=True)
        rank = next((i+1 for i, v in enumerate(sorted_counts) if v <= s_count), len(sorted_counts))

        series_breakdown = {
            "series":              series,
            "appearances":         s_count,
            "expected":            expected_per_series,
            "freq_ratio":          round(series_freq_r, 4),
            "decay_ratio":         round(series_decay_r, 4),
            "rank":                rank,
            "total_series":        self.n_unique_series,
            "known":               series in self.series_freq,
            "last_won":            s_last,
            "gap_sessions":        s_gap,
        }

        return {
            "number":            series + number,
            "series":            series,
            "five_digit":        number,
            "prize_type":        "first",
            "digit_length":      8,
            "composite_score":   min(300, round(composite * 100)),
            "composite_ratio":   round(composite, 4),
            "digit_ratio":       round(digit_r, 4),
            "series_freq_ratio": round(series_freq_r, 4),
            "series_decay_ratio":round(series_decay_r, 4),
            "per_prize": {
                "1": {
                    "prize_label":   "1st Prize",
                    "digit_ratio":   round(digit_r, 4),
                    "series_ratio":  round(series_freq_r, 4),
                    "series_decay":  round(series_decay_r, 4),
                    "composite":     round(composite, 4),
                    "score":         min(300, round(composite * 100)),
                }
            },
            "digit_breakdown":   self._digit_breakdown(number),
            "series_breakdown":  series_breakdown,
            "series_history":    s_hist[:20],
            "appearances":       s_count,
            "last_seen":         s_last,
            "gap_sessions":      s_gap,
            "baseline_score":    100,
            "sessions_total":    self.N,
        }

    def score(self, number: str) -> dict:
        """
        Routes by input length/format:
          4-digit           → prizes 3/4/5
          5-digit           → prizes 1/2 (2nd prize pool)
          8-char SSSNNNNN   → 1st prize (SSS=series, NNNNN=5-digit number)
        """
        number = number.strip().replace(" ", "")

        # 8-char 1st prize: first 3 chars are the series (may contain letters)
        if len(number) == 8 and not number.isdigit():
            series = number[:3].upper()
            num5   = number[3:]
            if num5.isdigit() and len(num5) == 5:
                return self._score_first_prize(series, num5)
            return {"error": "8-character input must be series (3 chars) + 5 digits, e.g. 83K90495"}

        number = number.zfill(len(number))
        n      = len(number)

        if n not in DIGIT_TIERS:
            return {"error": f"Enter a 4-digit, 5-digit, or 8-character (series+number) input."}

        tiers = DIGIT_TIERS[n]

        # Per-tier scores
        per_tier = {}
        for p in tiers:
            dr  = self._digit_ratio(number)
            dcr = self._decay_ratio(number, p)
            tr  = self._tier_ratio(number, p)
            comp = self._composite(dr, dcr, tr)
            per_tier[p] = {
                "prize_label":   f"{['','1st','2nd','3rd','4th','5th'][int(p)]} Prize",
                "digit_ratio":   round(dr, 4),
                "decay_ratio":   round(dcr, 4),
                "tier_ratio":    round(tr, 4),
                "composite":     round(comp, 4),
                "score":         min(300, round(comp * 100)),
            }

        # Aggregate: weighted by data richness (draws per session)
        total_weight = sum(PRIZE_DRAWS[p] for p in tiers)
        agg_comp = sum(
            per_tier[p]["composite"] * PRIZE_DRAWS[p]
            for p in tiers
        ) / total_weight

        # Shared digit breakdown (same for all tiers)
        digit_breakdown = self._digit_breakdown(number)

        # History
        history = self.history_map.get(number, [])
        appearances = len(history)
        last_seen   = history[0]["date"] if history else None

        # Gap since last seen (in sessions)
        gap = None
        if history:
            last_key = (history[0]["date"], history[0]["draw_time"])
            if last_key in self.sess_idx:
                gap = self.N - 1 - self.sess_idx[last_key]

        return {
            "number":          number,
            "prize_type":      "standard",
            "digit_length":    n,
            "composite_score": min(300, round(agg_comp * 100)),
            "composite_ratio": round(agg_comp, 4),
            "digit_ratio":     round(self._digit_ratio(number), 4),
            "avg_decay_ratio": round(
                sum(per_tier[p]["decay_ratio"] for p in tiers) / len(tiers), 4
            ),
            "avg_tier_ratio":  round(
                sum(per_tier[p]["tier_ratio"] for p in tiers) / len(tiers), 4
            ),
            "per_prize":       per_tier,
            "digit_breakdown": digit_breakdown,
            "appearances":     appearances,
            "last_seen":       last_seen,
            "gap_sessions":    gap,
            "history":         history[:20],          # last 20 appearances
            "baseline_score":  100,
            "sessions_total":  self.N,
        }

    def _digit_breakdown(self, number: str) -> list:
        """Per-position digit analysis for the frontend heatmap."""
        n = len(number)
        if n not in self.digit_prob:
            return []
        out = []
        for pos, d in enumerate(number):
            prob     = self.digit_prob[n][pos].get(d, 0.001)
            expected = 0.1
            delta    = (prob - expected) / expected * 100   # % above/below
            out.append({
                "position":  pos,
                "digit":     d,
                "prob":      round(prob, 4),
                "expected":  expected,
                "delta_pct": round(delta, 1),
                "status":    "hot" if delta > 5 else ("cold" if delta < -5 else "neutral"),
            })
        return out

    def hot_series(self, top_n: int = 20) -> list:
        """Top series codes by composite (series_freq + series_decay) score."""
        results = []
        for s, count in self.series_freq.items():
            sfr  = self._series_freq_ratio(s)
            sdr  = self._series_decay_ratio(s)
            comp = 0.40 * sfr + 0.35 * sdr + 0.25   # digit component = 1.0 baseline
            hist = self.series_history.get(s, [])
            results.append((comp, s, count, hist[0]["date"] if hist else None))
        results.sort(reverse=True)
        return [
            {"series": s, "score": min(300, round(comp * 100)),
             "appearances": cnt, "last_won": last}
            for comp, s, cnt, last in results[:top_n]
        ]

    def hot_numbers(self, prize: str = "5", top_n: int = 20) -> list:
        """Top numbers by composite score for a given prize tier."""
        pool = PRIZE_POOL[prize]
        digits = 4 if prize in ("3","4","5") else 5

        results = []
        for num_int in range(pool):
            num = str(num_int).zfill(digits)
            dr  = self._digit_ratio(num)
            dcr = self._decay_ratio(num, prize)
            tr  = self._tier_ratio(num, prize)
            comp = self._composite(dr, dcr, tr)
            results.append((comp, num))

        results.sort(reverse=True)
        return [
            {"number": num, "score": min(300, round(comp * 100)),
             "appearances": self.tier_freq[prize].get(num, 0)}
            for comp, num in results[:top_n]
        ]


# Singleton — loaded once at import time
_scorer = None  # type: LotteryScorer

def get_scorer() -> LotteryScorer:
    global _scorer
    if _scorer is None:
        print("Loading scorer …", flush=True)
        _scorer = LotteryScorer()
        print(f"Scorer ready. {_scorer.N} sessions indexed.", flush=True)
    return _scorer
