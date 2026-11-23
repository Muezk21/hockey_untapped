"""
dman_impact.py

Question: do 'Activated D-Man (OZ)' events actually go with more scoring chances,
or does the current number (21.6% of D-man possessions vs 18.7% of all possessions)
just reflect how possessions and your S marks work?

Run it after preprocess_events.py + master_data_script.py have built master_dataset.csv.
Needs pandas and numpy (both come with your pandas install).
"""
import os
import math
import pandas as pd
import numpy as np

BASE_DIR = r"C:\Users\khanm\OneDrive\Projects\stat_tracker"
MASTER_FILE = os.path.join(BASE_DIR, "master_dataset.csv")
TEAM = "Ducks"

A_EVENT = "Activated D-Man (OZ)"
OZ_EVENTS = ["OZ Turnover Forced", "DZ → OZ Transition Completed", "Stretch Pass → OZ Possession"]
OTHER_EVENTS = ["D-Man Aggressive Gap Close", "DZ Blueline Play Shut Down"]
WINDOWS = [10, 20]
N_BOOT = 3000
rng = np.random.default_rng(7)


# ---------- helpers ----------

def clock_to_seconds(c):
    try:
        m, s = map(int, str(c).split(":"))
        return m * 60 + s
    except Exception:
        return np.nan


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def rate_str(k, n):
    if n == 0:
        return "   n/a (n=0)"
    lo, hi = wilson(k, n)
    return f"{k / n * 100:5.1f}%  [{lo * 100:4.1f}-{hi * 100:4.1f}]  (n={n})"


def pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"


# ---------- load ----------

if not os.path.exists(MASTER_FILE):
    print("master_dataset.csv not found. Run preprocess_events.py and master_data_script.py first.")
    raise SystemExit(1)

df = pd.read_csv(MASTER_FILE)
df = df[df["team"] == TEAM].copy()
if df.empty:
    print(f"No rows for team {TEAM}.")
    raise SystemExit(1)

df["clock_seconds"] = df["Game_Clock"].apply(clock_to_seconds)
df["period_s"] = df["Period"].astype(str)
df["_ord"] = range(len(df))
df["is_chance"] = df["Is_Scoring_Chance"].astype(str).str.upper().eq("YES")
df["is_goal"] = df["Led_To_Goal"].astype(str).str.upper().eq("YES")
df = df.sort_values(["game_id", "period_s", "clock_seconds", "_ord"],
                    ascending=[True, True, False, True]).reset_index(drop=True)

n_games = df["game_id"].nunique()
n_A = int((df["Event"] == A_EVENT).sum())
print("=" * 72)
print("ACTIVATED D-MAN: DOES IT REALLY GO WITH MORE SCORING CHANCES?")
print("=" * 72)
print(f"{TEAM}: {n_games} games, {len(df)} events, {n_A} Activated D-Man events, "
      f"{int(df['is_chance'].sum())} rows marked as scoring chances\n")
if n_A == 0:
    raise SystemExit("No Activated D-Man events found.")

# ---------- possession table ----------

poss = df.groupby(["game_id", "possession_id"], sort=False).agg(
    start_event=("Event", "first"),
    start_clock=("clock_seconds", "max"),
    end_clock=("clock_seconds", "min"),
    n_events=("Event", "size"),
    n_A=("Event", lambda x: int((x == A_EVENT).sum())),
    chance=("is_chance", "max"),
    goal=("is_goal", "max"),
).reset_index()
poss["duration"] = (poss["start_clock"] - poss["end_clock"]).fillna(0)
poss["has_A"] = poss["n_A"] > 0

# ---------- CHECK 1: the current metric, with the right comparison ----------

print("-" * 72)
print("CHECK 1: possessions WITH a D-man activation vs WITHOUT one")
print("  (the old number compared D-man possessions to ALL possessions, which include them)")
print("  format: chance rate  [95% interval]  (possessions)")
print("-" * 72)
wa, wo = poss[poss["has_A"]], poss[~poss["has_A"]]
print(f"  With activated D-man:    {rate_str(int(wa['chance'].sum()), len(wa))}")
print(f"  Without:                 {rate_str(int(wo['chance'].sum()), len(wo))}")
print(f"  All possessions:         {rate_str(int(poss['chance'].sum()), len(poss))}")

# ---------- CHECK 2: confounders (how the possession started, how long it lasted) ----------

print("\n" + "-" * 72)
print("CHECK 2: same comparison, split by how the possession started and how long it lasted")
print("  If D-man possessions only look better because they last longer, the edge")
print("  shrinks or disappears inside each row below.")
print("-" * 72)

print("  By possession start:")
starts = poss["start_event"].value_counts()
for ev in starts.index:
    sub = poss[poss["start_event"] == ev]
    a, o = sub[sub["has_A"]], sub[~sub["has_A"]]
    if len(a) < 5:
        continue
    print(f"   {ev[:34]:34s} with D-man {rate_str(int(a['chance'].sum()), len(a))}")
    print(f"   {'':34s} without    {rate_str(int(o['chance'].sum()), len(o))}")

print("\n  By possession length (seconds from start to last event):")
poss["dur_bucket"] = pd.cut(poss["duration"], [-1, 10, 30, 10_000], labels=["0-10s", "10-30s", "30s+"])
for b in ["0-10s", "10-30s", "30s+"]:
    sub = poss[poss["dur_bucket"] == b]
    a, o = sub[sub["has_A"]], sub[~sub["has_A"]]
    print(f"   {b:7s} with D-man {rate_str(int(a['chance'].sum()), len(a))}")
    print(f"   {'':7s} without    {rate_str(int(o['chance'].sum()), len(o))}")
print(f"\n  Median length: with D-man {wa['duration'].median():.0f}s, without {wo['duration'].median():.0f}s")

# ---------- CHECK 3: event-window comparison against other offensive-zone events ----------

print("\n" + "-" * 72)
print("CHECK 3: chance within N seconds AFTER each type of event")
print("  'any' counts an S on the event's own row (your cause-marking habit).")
print("  'later' counts only S on rows after it, so it cannot be your marking habit.")
print("-" * 72)

for W in WINDOWS:
    self_s = np.zeros(len(df), dtype=bool)
    later_s = np.zeros(len(df), dtype=bool)
    pos = 0
    for (gid, per), grp in df.groupby(["game_id", "period_s"], sort=False):
        t = grp["clock_seconds"].values
        ch = grp["is_chance"].values
        n = len(grp)
        for i in range(n):
            self_s[pos + i] = ch[i]
            if np.isnan(t[i]):
                continue
            j = i + 1
            while j < n and not np.isnan(t[j]) and t[j] >= t[i] - W:
                if ch[j]:
                    later_s[pos + i] = True
                    break
                j += 1
        pos += n
    df[f"self_S"] = self_s
    df[f"later_{W}"] = later_s
    df[f"any_{W}"] = self_s | later_s

print(f"{'event type':34s}{'n':>5s} | {'any 10s':>8s} {'later 10s':>10s} | {'any 20s':>8s} {'later 20s':>10s}")
order = [A_EVENT] + OZ_EVENTS + OTHER_EVENTS
for ev in order:
    sub = df[df["Event"] == ev]
    if len(sub) == 0:
        continue
    marker = "  <==" if ev == A_EVENT else ""
    print(f"{ev[:34]:34s}{len(sub):5d} | "
          f"{sub['any_10'].mean() * 100:7.1f}% {sub['later_10'].mean() * 100:9.1f}% | "
          f"{sub['any_20'].mean() * 100:7.1f}% {sub['later_20'].mean() * 100:9.1f}%{marker}")

oz = df[df["Event"].isin(OZ_EVENTS)]
a_rows = df[df["Event"] == A_EVENT]
print(f"{'(all OZ events pooled)':34s}{len(oz):5d} | "
      f"{oz['any_10'].mean() * 100:7.1f}% {oz['later_10'].mean() * 100:9.1f}% | "
      f"{oz['any_20'].mean() * 100:7.1f}% {oz['later_20'].mean() * 100:9.1f}%")
print("\n  Fair comparison is D-man vs the OZ events (turnover forced, entries). Gap close and")
print("  Blueline shutdown happen far from the net, so they are not a fair baseline.")

# ---------- bootstrap by game ----------

print("\n" + "-" * 72)
print("CHECK 4: is the D-man advantage bigger than luck? (resampling whole games)")
print("  Difference = chance rate after D-man minus chance rate after other OZ events")
print("-" * 72)

games = df["game_id"].unique()
per_game = {}
for gid in games:
    g = df[df["game_id"] == gid]
    ga, go = g[g["Event"] == A_EVENT], g[g["Event"].isin(OZ_EVENTS)]
    per_game[gid] = {
        k: (int(ga[k].sum()), len(ga), int(go[k].sum()), len(go))
        for k in ["any_10", "later_10", "any_20", "later_20"]
    }

for k, label in [("any_10", "any chance within 10s"), ("later_10", "later chance within 10s"),
                 ("any_20", "any chance within 20s"), ("later_20", "later chance within 20s")]:
    arr = np.array([per_game[g][k] for g in games], dtype=float)  # cols: ka, na, ko, no
    ka, na, ko, no = arr.sum(axis=0)
    est = ka / na - ko / no
    diffs = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(games), len(games))
        s = arr[pick].sum(axis=0)
        if s[1] > 0 and s[3] > 0:
            diffs.append(s[0] / s[1] - s[2] / s[3])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    verdict = "interval includes 0: no clear effect" if lo <= 0 <= hi else "interval excludes 0"
    print(f"  {label:26s} difference {est * 100:+5.1f} points  [{lo * 100:+5.1f}, {hi * 100:+5.1f}]  {verdict}")

# ---------- CHECK 5: where S sits, and game-by-game consistency ----------

print("\n" + "-" * 72)
print("CHECK 5: how much of the D-man 'impact' is S marked on the D-man row itself?")
print("-" * 72)
a_any = a_rows[a_rows["any_10"]]
print(f"  Activated D-Man events with a chance within 10s: {len(a_any)} of {len(a_rows)}")
print(f"    ...of those, S is on the D-man row itself:      {int(a_any['self_S'].sum())}")
print(f"    ...chance only on a later row:                  {int((~a_any['self_S']).sum())}")
oz_any = oz[oz["any_10"]]
print(f"  Other OZ events with a chance within 10s: {len(oz_any)} of {len(oz)}")
print(f"    ...of those, S is on the event row itself:      {int(oz_any['self_S'].sum())}")
print("  A much higher own-row share for D-man events means your habit of marking S on the")
print("  D-man row, not the play itself, is driving the number.")

print("\n  Game by game (games with 3+ D-man events): D-man chance rate vs other OZ events, 10s window")
higher = lower = equal = 0
for gid in games:
    ka, na, ko, no = per_game[gid]["any_10"]
    if na < 3 or no == 0:
        continue
    ra, ro = ka / na, ko / no
    if ra > ro:
        higher += 1
    elif ra < ro:
        lower += 1
    else:
        equal += 1
print(f"    D-man higher in {higher} games, lower in {lower}, equal in {equal}")

print("\n" + "=" * 72)
print("HOW TO READ THIS")
print("=" * 72)
print("  - A real effect should survive CHECK 2 (inside each start type / length row),")
print("    show up in the 'later' columns of CHECK 3, and have a CHECK 4 interval above 0.")
print("  - If the difference only appears in the 'any' column, it comes from where you")
print("    press S, not from what the D-man did.")
print("  - Even a clear difference here is an association: D-man activations happen late in")
print("    possessions, close to the chance, so this cannot prove they cause chances.")