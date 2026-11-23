"""
ducks_record_vs_numbers.py

For every tracked Ducks game in raw_data/ducks_data:
  1. Reads your raw tracker CSV and computes per-game numbers
  2. Looks up the real result (score, W/L) from the NHL API
  3. Prints a per-game table, rank correlations between your numbers and
     results, and a season-by-season summary
  4. Saves everything to analytics_reports/ducks_game_results.csv

Uses only the Python standard library, so any Python 3 works.
"""
import os
import re
import csv
import glob
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
import json

BASE_DIR = r"C:\Users\khanm\OneDrive\Projects\stat_tracker"
RAW_DIR = os.path.join(BASE_DIR, "raw_data", "ducks_data")
OUT_DIR = os.path.join(BASE_DIR, "analytics_reports")
TEAM = "ANA"
MIN_EVENTS_FLAG = 40  # games with fewer tracked events get flagged

# Games before this date are left out of the comparison (set to None to include all).
# The early games were tracked before turnovers and S marks were being logged,
# so including them makes the tracking change look like a hockey effect.
MIN_DATE = "2026-01-19"

METRICS = [
    ("events", "Total events tracked"),
    ("turnovers", "OZ turnovers forced"),
    ("to_chances", "Turnovers marked S"),
    ("to_chance_rate", "Turnover -> chance rate"),
    ("shots", "Shots tracked"),
    ("quick_shot_share", "Rush+Early share of shots"),
    ("chances_marked", "Events marked S"),
    ("dman_acts", "Activated D-Man"),
    ("dman_chance_rate", "D-Man -> chance rate"),
    ("gap_closes", "Gap closes"),
    ("goals_led", "Events marked G"),
    ("penalties_drawn", "Events marked P"),
]


# ---------- NHL API ----------

def api_get(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json",
    })
    with urlopen(req) as r:
        return json.load(r)


_sched = {}


def season_code(d):
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}{start + 1}"


def schedule(season):
    if season not in _sched:
        data = api_get(f"https://api-web.nhle.com/v1/club-schedule-season/{TEAM}/{season}")
        _sched[season] = [g for g in data.get("games", [])
                          if g.get("gameState") in ("OFF", "FINAL")]
    return _sched[season]


OPP_ALIASES = {"SJ": "SJS", "TB": "TBL", "LA": "LAK", "NJ": "NJD", "WAS": "WSH",
               "CLB": "CBJ", "VEG": "VGK", "WIN": "WPG", "MON": "MTL"}


def parse_opponent(fname):
    """'26_4_9_ANA_VS_SJS.csv' -> 'SJS'. None if the filename has no 2-3 letter opponent code."""
    m = re.search(r"VS_+([A-Za-z]{2,3})(?![A-Za-z])", fname, re.IGNORECASE)
    if not m:
        return None
    code = m.group(1).upper()
    return OPP_ALIASES.get(code, code)


def find_game(d, opp_code=None):
    """Returns (game, day_offset, opponent_check).

    With an opponent code from the filename: find that opponent within +/-3 days,
    closest date first -> opponent_check 'ok'.
    If that fails, or there is no opponent in the filename, fall back to the nearest
    Ducks game within +/-1 day. The check is then 'MISMATCH' (a filename opponent
    was expected but the game found is against someone else) or
    'no opponent in filename'.
    """
    games = schedule(season_code(d))
    if opp_code:
        best = None
        for g in games:
            gd = datetime.strptime(g["gameDate"], "%Y-%m-%d").date()
            offset = (gd - d).days
            opps = {g["homeTeam"].get("abbrev"), g["awayTeam"].get("abbrev")}
            if opp_code in opps and abs(offset) <= 3:
                if best is None or abs(offset) < abs(best[1]):
                    best = (g, offset)
        if best:
            return best[0], best[1], "ok"
    for offset in (0, -1, 1):
        target = (d + timedelta(days=offset)).isoformat()
        for g in games:
            if g.get("gameDate") == target:
                return g, offset, ("MISMATCH" if opp_code else "no opponent in filename")
    return None, None, None


def result_info(g):
    home, away = g["homeTeam"], g["awayTeam"]
    if home.get("abbrev") == TEAM:
        me, opp, where = home, away, "H"
    else:
        me, opp, where = away, home, "A"
    gf, ga = me.get("score"), opp.get("score")
    if gf is None or ga is None:
        return None
    ptype = (g.get("gameOutcome") or {}).get("lastPeriodType", "REG")
    win = gf > ga
    label = ("W" if win else "L") + ("" if ptype == "REG" else "-" + ptype)
    return {
        "opp": opp.get("abbrev", "?"), "where": where,
        "gf": gf, "ga": ga, "gd": gf - ga,
        "win": 1 if win else 0, "result": label,
        "game_type": g.get("gameType"),
    }


# ---------- filename + tracker data ----------

def parse_date(fname):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", fname)
    try:
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        m = re.match(r"(\d{2})_(\d{1,2})_(\d{1,2})", fname)
        if m:
            return datetime(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        pass
    return None


def ratio(a, b):
    return round(a / b, 3) if b else None


DESCRIPTOR_EVENTS = ("Shot With Traffic", "Low-Value Shot")


def unique_shot_count(rows):
    """One shot = one real shot. A Traffic / Low-Value row logged at the same period and
    clock as another shot row is a descriptor on that shot, not a second shot."""
    groups = {}
    for r in rows:
        name = (r.get("Event") or "").strip()
        if "Shot" in name or "Scoring Chance" in name:
            groups.setdefault((r.get("Period"), r.get("Game_Clock")), []).append(name)
    total = 0
    for names in groups.values():
        others = [n for n in names if n not in DESCRIPTOR_EVENTS]
        total += max(len(others), 1)
    return total


def game_metrics(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def ev(r):
        return (r.get("Event") or "").strip()

    def yes(r, col):
        return (r.get(col) or "").strip().upper() == "YES"

    turnovers = [r for r in rows if ev(r) == "OZ Turnover Forced"]
    n_shots = unique_shot_count(rows)
    dman = [r for r in rows if ev(r) == "Activated D-Man (OZ)"]
    rush = sum("Rush Shot" in ev(r) for r in rows)
    early = sum("Early Possession" in ev(r) for r in rows)
    to_ch = sum(yes(r, "Is_Scoring_Chance") for r in turnovers)
    dm_ch = sum(yes(r, "Is_Scoring_Chance") for r in dman)

    return {
        "events": len(rows),
        "turnovers": len(turnovers),
        "to_chances": to_ch,
        "to_chance_rate": ratio(to_ch, len(turnovers)),
        "shots": n_shots,
        "rush_shots": rush,
        "early_shots": early,
        "sustained_shots": sum("Sustained Possession" in ev(r) for r in rows),
        "extended_shots": sum("Extended Possession" in ev(r) for r in rows),
        "quick_shot_share": ratio(rush + early, n_shots),
        "chances_marked": sum(yes(r, "Is_Scoring_Chance") or "Scoring Chance" in ev(r) for r in rows),
        "dman_acts": len(dman),
        "dman_chance_rate": ratio(dm_ch, len(dman)),
        "gap_closes": sum(ev(r) == "D-Man Aggressive Gap Close" for r in rows),
        "goals_led": sum(yes(r, "Led_To_Goal") for r in rows),
        "penalties_drawn": sum(yes(r, "Penalty_Drawn") for r in rows),
    }


# ---------- stats helpers ----------

def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = sum((a - mx) ** 2 for a in x)
    sy = sum((b - my) ** 2 for b in y)
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) ** 0.5


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def fmt(v, width=6):
    return f"{'n/a':>{width}}" if v is None else f"{v:>{width}.2f}"


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------- main ----------

def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
    if not files:
        print(f"No CSV files found in {RAW_DIR}")
        return
    print(f"Found {len(files)} tracked files in {RAW_DIR}\n")

    rows, problems = [], []
    for path in files:
        fname = os.path.basename(path)
        d = parse_date(fname)
        if d is None:
            problems.append(f"{fname}: could not read a date from the filename")
            continue
        file_opp = parse_opponent(fname)
        try:
            game, offset, opp_check = find_game(d, file_opp)
        except Exception as e:
            problems.append(f"{fname}: NHL API error ({e})")
            continue
        if game is None:
            problems.append(f"{fname}: no completed Ducks game found on {d} (+/-1 day)")
            continue
        info = result_info(game)
        if info is None:
            problems.append(f"{fname}: game found but no score available")
            continue
        row = {"file": fname, "date": d.isoformat(), "game_id": game.get("id"),
               "game_date": game.get("gameDate"),
               "season": season_code(d), "date_shift": offset,
               "file_opp": file_opp or "", "opp_check": opp_check}
        row.update(info)
        row.update(game_metrics(path))
        rows.append(row)

    if not rows:
        print("No games could be matched.")
        for p in problems:
            print("  -", p)
        return

    rows.sort(key=lambda r: r["date"])
    matched = len(rows)

    # two files pointing at the same real game means one of them has the wrong date or opponent
    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r["file"])
    dupes = {gid: fs for gid, fs in by_game.items() if len(fs) > 1}
    if dupes:
        print("WARNING: more than one file matched the same real game:")
        for gid, fs in dupes.items():
            print("  - " + "  <->  ".join(fs))
        print("  One of each pair has the wrong date or opponent in its filename.\n")

    if MIN_DATE:
        excluded = [r for r in rows if r["date"] < MIN_DATE]
        rows = [r for r in rows if r["date"] >= MIN_DATE]
        print(f"Excluding {len(excluded)} games before {MIN_DATE} "
              f"(set MIN_DATE = None in the script to include them).\n")
        if len(rows) < 8:
            print("Fewer than 8 games left after the date filter - not enough to compare.")
            return

    # per-game table
    print("PER-GAME TABLE")
    print(f"{'date':<11}{'opp':<5}{'H/A':<4}{'result':<7}{'score':<6}"
          f"{'events':>7}{'TO':>4}{'TO>S':>5}{'shots':>6}{'S':>4}  notes")
    for r in rows:
        notes = []
        if r["events"] < MIN_EVENTS_FLAG:
            notes.append("few events - partial tracking?")
        if r["opp_check"] == "MISMATCH":
            notes.append(f"FILENAME SAYS {r['file_opp']}, SCHEDULE GAME IS {r['opp']} - FIX THE FILENAME")
        elif r["date_shift"]:
            if r["opp_check"] == "ok":
                notes.append(f"date off by {r['date_shift']:+d} day, opponent confirmed")
            else:
                notes.append(f"matched {r['date_shift']:+d} day - no opponent in filename to confirm")
        if r["game_type"] not in (2, None):
            notes.append("not regular season")
        print(f"{r['date']:<11}{r['opp']:<5}{r['where']:<4}{r['result']:<7}"
              f"{str(r['gf']) + '-' + str(r['ga']):<6}"
              f"{r['events']:>7}{r['turnovers']:>4}{r['to_chances']:>5}"
              f"{r['shots']:>6}{r['chances_marked']:>4}  {'; '.join(notes)}")

    # data checks
    n_games = len(rows)
    wins = sum(r["win"] for r in rows)
    losses = n_games - wins
    same = sum(1 for r in rows if r["goals_led"] == r["penalties_drawn"])
    print(f"\nDATA CHECKS")
    print(f"  Record in these games: {wins} wins, {losses} losses")
    if min(wins, losses) < 5:
        print("  -> Too few wins or losses for the 'rho vs win' column to mean anything. Use 'rho vs gd'.")
    print(f"  Games where G count equals P count: {same} of {n_games}")
    if same >= n_games * 0.8:
        print("  -> G and P counts are almost always identical. Open a raw CSV and check that")
        print("     Led_To_Goal and Penalty_Drawn are being recorded separately.")

    # correlations
    print("\nRANK CORRELATIONS (Spearman) vs RESULT")
    print("  gd = goal differential, win = 1 if Ducks won (incl. OT/SO), else 0")
    print("  * = |rho| above ~2/sqrt(n), a rough 'worth a second look' bar, NOT proof")
    print(f"{'metric':<30}{'n':>4}{'rho vs gd':>11}{'rho vs win':>12}")
    for key, label in METRICS:
        pairs = [(r[key], r["gd"], r["win"]) for r in rows if r[key] is not None]
        n = len(pairs)
        if n < 8:
            continue
        x = [p[0] for p in pairs]
        rg = spearman(x, [p[1] for p in pairs])
        rw = spearman(x, [p[2] for p in pairs])
        bar = 2 / n ** 0.5
        flag = "*" if (rg is not None and abs(rg) >= bar) or (rw is not None and abs(rw) >= bar) else ""
        print(f"{label:<30}{n:>4}{fmt(rg, 11)}{fmt(rw, 12)} {flag}")

    # season summary
    print("\nSEASON SUMMARY")
    print(f"{'season':<10}{'games':>6}{'win%':>7}{'avg gd':>8}{'avg TO':>8}"
          f"{'TO>S rate':>11}{'avg shots':>10}{'avg S':>7}")
    for season in sorted({r["season"] for r in rows}):
        g = [r for r in rows if r["season"] == season]
        print(f"{season:<10}{len(g):>6}{fmt(mean([r['win'] for r in g]) * 100, 7)}"
              f"{fmt(mean([r['gd'] for r in g]), 8)}"
              f"{fmt(mean([r['turnovers'] for r in g]), 8)}"
              f"{fmt(mean([r['to_chance_rate'] for r in g]), 11)}"
              f"{fmt(mean([r['shots'] for r in g]), 10)}"
              f"{fmt(mean([r['chances_marked'] for r in g]), 7)}")

    # save
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "ducks_game_results.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved: {out_path}")

    if problems:
        print("\nFILES NOT MATCHED:")
        for p in problems:
            print("  -", p)

    print(f"\n{matched} of {len(files)} games matched; {len(rows)} used in the comparison.")
    bad = [r for r in rows if r["opp_check"] == "MISMATCH"]
    if bad:
        print(f"\nWARNING: {len(bad)} file(s) have an opponent that does not match the schedule:")
        for r in bad:
            print(f"  - {r['file']}: filename says {r['file_opp']}, schedule game is {r['opp']}")
        print("  Their results are probably attached to the wrong game. Fix the filename and rerun.")
    print("Reminder: with a sample this small, a few of these correlations will")
    print("look meaningful by chance alone. Treat them as leads to test on new games.")


if __name__ == "__main__":
    main()