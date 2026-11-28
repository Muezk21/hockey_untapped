import math
import random
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw_data" / "ducks_data"
REPORTS_DIR = BASE_DIR / "analytics_reports"
REPORTS_DIR.mkdir(exist_ok=True)

TIMING_LABELS = {
    "Rush Shot (<5s After Zone Entry)": "Rush",
    "Rush Shot (rush / unsettled) <5s within zone entry": "Rush",
    "Early Possession Shot (<10s)": "Early",
    "Early Possession Shot <10s within zone entry": "Early",
    "Sustained Possession Shot (10–30s)": "Sustained",
    "Sustained Possession Shot – 10–30s of in-zone possession": "Sustained",
    "Extended Possession Shot (>30s)": "Extended",
}
FOLLOWUP_LABELS = {
    "2nd Scoring Chance (Same Possession)": "2nd chance",
    "3rd+ Scoring Chance (Same Possession)": "3rd+ chance",
}
DESCRIPTORS = {"Shot With Traffic": "Traffic", "Low-Value Shot": "Low-Value"}
POSSESSION_STARTS = {"OZ Turnover Forced", "DZ Blueline Play Shut Down"}
GAP_WINDOW = 10
RNG = random.Random(20261127)


def yes(value):
    return str(value).strip().upper() in {"YES", "TRUE", "1"}


def nonblank(value):
    return pd.notna(value) and str(value).strip() != ""


def wilson(successes, total, z=1.96):
    if total <= 0:
        return (None, None)
    p = successes / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    half = z * math.sqrt((p * (1 - p) / total) + z * z / (4 * total * total)) / den
    return max(0, center - half), min(1, center + half)


def cluster_bootstrap_rate(records, field, reps=2500):
    """Game-cluster bootstrap: resample games, not individual shots."""
    if not records:
        return (None, None)
    games = {}
    for row in records:
        games.setdefault(row["game_id"], []).append(row)
    game_ids = list(games)
    if len(game_ids) < 2:
        return (None, None)
    estimates = []
    for _ in range(reps):
        chosen = [RNG.choice(game_ids) for _ in game_ids]
        n = s = 0
        for game_id in chosen:
            sample = games[game_id]
            n += len(sample)
            s += sum(bool(x[field]) for x in sample)
        if n:
            estimates.append(s / n)
    estimates.sort()
    return estimates[int(.025 * (len(estimates) - 1))], estimates[int(.975 * (len(estimates) - 1))]


def read_legacy_games():
    if not RAW_DIR.exists():
        return []
    games = []
    for path in sorted(RAW_DIR.glob("*.csv")):
        frame = pd.read_csv(path, keep_default_na=False)
        frame.columns = [str(c).strip() for c in frame.columns]
        frame["game_id"] = path.stem
        frame["source_group"] = "legacy_manual"
        games.append(frame)
    return games


def make_legacy_shots(games):
    """Recover shot rows from the old manual log without inventing entry times."""
    shots = []
    ambiguous_descriptors = 0
    for frame in games:
        groups = {}
        for _, row in frame.iterrows():
            event = str(row.get("Event", "")).strip()
            if event in TIMING_LABELS or event in FOLLOWUP_LABELS or event in DESCRIPTORS:
                key = (str(row.get("Period", "")), str(row.get("Game_Clock", "")))
                groups.setdefault(key, []).append(row)

        for (period, clock), rows in groups.items():
            primary = [r for r in rows if str(r.get("Event", "")).strip() in TIMING_LABELS or
                       str(r.get("Event", "")).strip() in FOLLOWUP_LABELS]
            descriptors = [r for r in rows if str(r.get("Event", "")).strip() in DESCRIPTORS]

            if primary:
                for r in primary:
                    event = str(r.get("Event", "")).strip()
                    attached = descriptors if len(primary) == 1 else []
                    if descriptors and len(primary) > 1:
                        ambiguous_descriptors += len(descriptors)
                    related = [r] + attached
                    chance = any(yes(x.get("Is_Scoring_Chance", "NO")) for x in related)
                    if event in FOLLOWUP_LABELS:
                        chance = True
                    goal = any(str(x.get("Shot_Result", "")).strip().lower() == "goal" for x in related)
                    shots.append({
                        "game_id": frame["game_id"].iloc[0],
                        "period": period, "clock": clock,
                        "category": TIMING_LABELS.get(event, FOLLOWUP_LABELS.get(event)),
                        "chance": chance, "goal": goal,
                        "traffic": any(str(x.get("Event", "")).strip() == "Shot With Traffic" for x in attached),
                        "low_value": any(str(x.get("Event", "")).strip() == "Low-Value Shot" for x in attached),
                    })
            elif descriptors:
                shots.append({
                    "game_id": frame["game_id"].iloc[0],
                    "period": period, "clock": clock, "category": "descriptor-only",
                    "chance": any(yes(x.get("Is_Scoring_Chance", "NO")) for x in descriptors),
                    "goal": any(str(x.get("Shot_Result", "")).strip().lower() == "goal" for x in descriptors),
                    "traffic": any(str(x.get("Event", "")).strip() == "Shot With Traffic" for x in descriptors),
                    "low_value": any(str(x.get("Event", "")).strip() == "Low-Value Shot" for x in descriptors),
                })
    return shots, ambiguous_descriptors


def elapsed_from_clock(period, clock):
    try:
        m, s = [int(x) for x in str(clock).split(":")]
        period_number = int(period)
        return (period_number - 1) * 1200 + (1200 - (m * 60 + s))
    except Exception:
        return None


def legacy_event_audit(games):
    rows = []
    all_events = []
    for frame in games:
        game_id = frame["game_id"].iloc[0]
        for _, r in frame.iterrows():
            event = str(r.get("Event", "")).strip()
            all_events.append((game_id, r))
            rows.append({
                "game_id": game_id, "event": event,
                "chance_flag": yes(r.get("Is_Scoring_Chance", "NO")),
                "led_to_goal_flag": yes(r.get("Led_To_Goal", "NO")),
                "actual_goal": str(r.get("Shot_Result", "")).strip().lower() == "goal",
            })
    return pd.DataFrame(rows), all_events


def gap_close_matches(all_events):
    """One-to-one temporal matches only; this is association, not proof of causation."""
    gaps, turnovers = [], []
    for game_id, r in all_events:
        event = str(r.get("Event", "")).strip()
        t = elapsed_from_clock(r.get("Period", ""), r.get("Game_Clock", ""))
        if t is None:
            continue
        item = {
            "game_id": game_id, "period": str(r.get("Period", "")),
            "elapsed": t, "clock": str(r.get("Game_Clock", "")),
            "chance": yes(r.get("Is_Scoring_Chance", "NO")),
            "led_to_goal": yes(r.get("Led_To_Goal", "NO")),
        }
        if event == "D-Man Aggressive Gap Close":
            gaps.append(item)
        elif event == "OZ Turnover Forced":
            turnovers.append(item)
    gaps.sort(key=lambda x: (x["game_id"], x["period"], x["elapsed"]))
    turnovers.sort(key=lambda x: (x["game_id"], x["period"], x["elapsed"]))
    used = set()
    matches = []
    for gap in gaps:
        candidates = []
        for i, turnover in enumerate(turnovers):
            if i in used:
                continue
            if (turnover["game_id"], turnover["period"]) != (gap["game_id"], gap["period"]):
                continue
            delta = turnover["elapsed"] - gap["elapsed"]
            if 0 <= delta <= GAP_WINDOW:
                candidates.append((delta, i, turnover))
        if candidates:
            delta, i, turnover = min(candidates, key=lambda x: (x[0], x[1]))
            used.add(i)
            matches.append({
                "game_id": gap["game_id"], "period": gap["period"],
                "gap_close_clock": gap["clock"], "turnover_clock": turnover["clock"],
                "seconds_after_gap_close": delta,
                "chance_flag_on_turnover_event": turnover["chance"],
                "led_to_goal_flag_on_turnover_event": turnover["led_to_goal"],
            })
    return gaps, turnovers, matches


def load_v4_exports():
    exports = []
    for path in sorted(BASE_DIR.glob("*.csv")):
        if path.name.lower() == "master_dataset.csv":
            continue
        try:
            frame = pd.read_csv(path, keep_default_na=False)
        except Exception:
            continue
        required = {"Source", "Event_Type", "Game_ID", "Game_Clock", "Team"}
        if required.issubset(set(frame.columns)):
            frame["__file"] = path.name
            exports.append(frame)
    return exports


def analyze_v4_exports(exports):
    possession_rows = []
    entry_rows = []
    shot_rows = []
    audit_rows = []
    gap_rows = []

    for frame in exports:
        game_id = str(frame["Game_ID"].iloc[0]) if len(frame) else frame["__file"].iloc[0]
        ducks = frame[frame["Team"].astype(str).str.upper().isin(["ANA", "DUCKS"])].copy()
        if "Possession_ID" not in ducks.columns:
            ducks["Possession_ID"] = ""
        carryins = ducks[
            (ducks["Event_Type"].astype(str) == "Zone Entry") &
            (ducks["Event"].astype(str) == "Carry-in")
        ]
        shots = ducks[ducks["Event_Type"].astype(str) == "Shot"].copy()
        audit_rows.append({
            "file": frame["__file"].iloc[0], "game_id": game_id,
            "rows": len(frame), "ducks_shots": len(shots),
            "carry_ins": len(carryins),
            "has_possession_ids": ducks["Possession_ID"].map(nonblank).any(),
        })

        for _, r in shots.iterrows():
            if str(r.get("Possession_Class", "")) in {"Rush", "Early", "Sustained", "Extended"}:
                shot_rows.append({
                    "game_id": game_id,
                    "category": str(r.get("Possession_Class")),
                    "chance": yes(r.get("Is_Scoring_Chance", "NO")) or yes(r.get("Second_Chance", "NO")) or yes(r.get("Third_Plus_Chance", "NO")),
                    "goal": str(r.get("Shot_Result", "")).strip().lower() == "goal",
                    "event_id": str(r.get("Event_ID", "")),
                })

        if not ducks["Possession_ID"].map(nonblank).any():
            continue

        ducks["__pid"] = ducks["Possession_ID"].astype(str)
        ducks = ducks[ducks["__pid"].map(nonblank)]
        for pid, group in ducks.groupby("__pid"):
            group_shots = group[group["Event_Type"].astype(str) == "Shot"]
            has_entry = ((group["Event_Type"].astype(str) == "Zone Entry") &
                         (group["Event"].astype(str) == "Carry-in")).any()
            has_turnover = (group["Event"].astype(str) == "OZ Turnover Forced").any()
            has_activation = (group["Event"].astype(str) == "Activated D-Man (OZ)").any()
            has_gap = (group["Event"].astype(str) == "D-Man Aggressive Gap Close").any()
            chance = group["Is_Scoring_Chance"].map(yes).any()
            if "Second_Chance" in group:
                chance = chance or group["Second_Chance"].map(yes).any()
            if "Third_Plus_Chance" in group:
                chance = chance or group["Third_Plus_Chance"].map(yes).any()
            goal = group_shots["Shot_Result"].astype(str).str.lower().eq("goal").any()
            possession_rows.append({
                "game_id": game_id, "possession_id": pid,
                "has_entry": has_entry, "has_turnover": has_turnover,
                "has_activation": has_activation, "has_gap_close": has_gap,
                "shots": len(group_shots), "chance": bool(chance), "goal": bool(goal),
            })

        if "Elapsed_Seconds" in ducks.columns:
            gap_events = ducks[ducks["Event"].astype(str) == "D-Man Aggressive Gap Close"]
            turnover_events = ducks[ducks["Event"].astype(str) == "OZ Turnover Forced"]
            used = set()
            for _, gap in gap_events.iterrows():
                try:
                    gt = float(gap["Elapsed_Seconds"])
                except Exception:
                    continue
                candidates = []
                for idx, turnover in turnover_events.iterrows():
                    if idx in used:
                        continue
                    try:
                        delta = float(turnover["Elapsed_Seconds"]) - gt
                    except Exception:
                        continue
                    if 0 <= delta <= GAP_WINDOW:
                        candidates.append((delta, idx, turnover))
                if candidates:
                    delta, idx, turnover = min(candidates, key=lambda x: x[0])
                    used.add(idx)
                    gap_rows.append({
                        "game_id": game_id, "gap_clock": gap["Game_Clock"],
                        "turnover_clock": turnover["Game_Clock"], "seconds_after": delta,
                    })

    return possession_rows, shot_rows, audit_rows, gap_rows


def rate_text(successes, total):
    if total <= 0:
        return "n/a"
    lo, hi = wilson(successes, total)
    return f"{100*successes/total:.1f}% ({successes}/{total}; Wilson 95% CI {100*lo:.1f}–{100*hi:.1f}%)"


def main():
    print("=" * 72)
    print("HOCKEY UNTAPPED — DATA AUDIT & ANALYTICS")
    print("=" * 72)

    games = read_legacy_games()
    if games:
        raw = pd.concat(games, ignore_index=True)
        events, all_events = legacy_event_audit(games)
        shots, ambiguous = make_legacy_shots(games)
        games_n = len(games)
        event_n = len(raw)
        event_counts = raw["Event"].astype(str).value_counts()
        carryins = int((raw["Event"].astype(str).str.strip() == "Carry-in").sum())
        goal_rows = int(raw["Shot_Result"].astype(str).str.strip().str.lower().eq("goal").sum())
        led_tags = int(raw["Led_To_Goal"].map(yes).sum())
        chance_flags = int(raw["Is_Scoring_Chance"].map(yes).sum())

        print(f"\nLEGACY MANUAL DATA: {games_n} games, {event_n:,} raw rows")
        print(f"  Actual Carry-in events recorded: {carryins}")
        print("  Entry-based shot timing: NOT AVAILABLE for this cohort")
        print(f"  Legacy shot observations reconstructed: {len(shots)}")
        print(f"  Scoring-chance flags on raw event rows: {chance_flags}")
        print(f"  Led_To_Goal attribution tags: {led_tags}")
        print(f"  Actual Shot_Result=Goal rows: {goal_rows}")
        print("  NOTE: Led_To_Goal is an attribution tag, not a goal counter.")

        event_summary = []
        for name in ["OZ Turnover Forced", "D-Man Aggressive Gap Close",
                     "Activated D-Man (OZ)", "DZ → OZ Transition Completed",
                     "Stretch Pass → OZ Possession", "DZ Blueline Play Shut Down"]:
            subset = events[events["event"] == name]
            event_summary.append({
                "Event": name, "Count": len(subset),
                "Chance_Flag_On_Event": int(subset["chance_flag"].sum()),
                "Led_To_Goal_Tags_On_Event": int(subset["led_to_goal_flag"].sum()),
            })

        turnover_n = int((events["event"] == "OZ Turnover Forced").sum())
        turnover_chance_flags = int(events.loc[events["event"] == "OZ Turnover Forced", "chance_flag"].sum())
        gaps, turnovers, matches = gap_close_matches(all_events)
        print(f"\n  Turnover events: {turnover_n}")
        print(f"  Chance flag placed directly on turnover event: {rate_text(turnover_chance_flags, turnover_n)}")
        print(f"  Gap closes: {len(gaps)}")
        print(f"  Unique gap-close → turnover temporal matches within {GAP_WINDOW}s: {len(matches)}/{len(gaps)}")
        print("  This is a timing association only; it does not prove the gap close caused the turnover.")
        print("  Turnover-possession outcomes and D-man possession outcomes are withheld for legacy data:")
        print("  the raw files omit full NHL event sequences and do not contain trustworthy possession IDs.")

        categories = ["Rush", "Early", "Sustained", "Extended", "2nd chance", "3rd+ chance", "descriptor-only"]
        shot_summary = []
        for category in categories:
            subset = [x for x in shots if x["category"] == category]
            if not subset:
                continue
            chance_n = sum(x["chance"] for x in subset)
            goal_n = sum(x["goal"] for x in subset)
            ci_lo, ci_hi = cluster_bootstrap_rate(subset, "chance")
            shot_summary.append({
                "Cohort": "Legacy manually assigned timing / tags",
                "Category": category, "Shots": len(subset),
                "Scoring_Chance": chance_n, "Chance_Rate_%": round(100*chance_n/len(subset), 2),
                "Chance_Rate_Game_Cluster_CI_Low_%": round(100*ci_lo, 2) if ci_lo is not None else "",
                "Chance_Rate_Game_Cluster_CI_High_%": round(100*ci_hi, 2) if ci_hi is not None else "",
                "Actual_Goals": goal_n, "Goal_Rate_%": round(100*goal_n/len(subset), 2),
            })
            print(f"  {category:16} n={len(subset):3} | chance {rate_text(chance_n, len(subset))} | actual goals {goal_n}/{len(subset)} ({100*goal_n/len(subset):.1f}%)")

        traffic = [x for x in shots if x["traffic"]]
        low = [x for x in shots if x["low_value"]]
        descriptor_summary = []
        for name, subset in [("Traffic tag (overlaps timing groups)", traffic), ("Low-value tag", low)]:
            if subset:
                descriptor_summary.append({
                    "Descriptor": name, "Shots": len(subset),
                    "Scoring_Chance": sum(x["chance"] for x in subset),
                    "Chance_Rate_%": round(100*sum(x["chance"] for x in subset)/len(subset), 2),
                    "Actual_Goals": sum(x["goal"] for x in subset),
                    "Goal_Rate_%": round(100*sum(x["goal"] for x in subset)/len(subset), 2),
                })
        print("\n  Descriptor rates include overlap with timing categories; do not add them to timing-group totals.")
        for d in descriptor_summary:
            print(f"  {d['Descriptor']}: {d['Shots']} shots, chance {d['Chance_Rate_%']:.1f}%, actual goals {d['Actual_Goals']} ({d['Goal_Rate_%']:.1f}%)")

        pd.DataFrame(event_summary).to_csv(REPORTS_DIR / "legacy_event_audit.csv", index=False)
        pd.DataFrame(shot_summary).to_csv(REPORTS_DIR / "legacy_shot_metrics.csv", index=False)
        pd.DataFrame(descriptor_summary).to_csv(REPORTS_DIR / "legacy_descriptor_metrics.csv", index=False)
        pd.DataFrame(matches).to_csv(REPORTS_DIR / "legacy_gap_close_matches.csv", index=False)
        pd.DataFrame([{
            "Games": games_n, "Raw_Events": event_n, "Carry_in_Events": carryins,
            "Legacy_Shots_Reconstructed": len(shots), "Ambiguous_Descriptor_Collisions": ambiguous,
            "Scoring_Chance_Event_Flags": chance_flags, "Led_To_Goal_Tags": led_tags,
            "Actual_Goal_Shot_Rows": goal_rows, "Turnover_Events": turnover_n,
            "Turnover_Event_Chance_Flags": turnover_chance_flags,
            "Gap_Close_Events": len(gaps), "Unique_Gap_To_Turnover_Matches": len(matches),
        }]).to_csv(REPORTS_DIR / "legacy_data_quality_audit.csv", index=False)
    else:
        print("\nNo legacy raw game CSVs found.")

    exports = load_v4_exports()
    if exports:
        possessions, v4_shots, audit, v4_gaps = analyze_v4_exports(exports)
        print(f"\nV4 EXPORTS: {len(exports)} game export(s)")
        for a in audit:
            print(f"  {a['file']}: {a['ducks_shots']} Ducks shots, {a['carry_ins']} carry-ins, possession IDs: {'yes' if a['has_possession_ids'] else 'no'}")
        if possessions:
            pdf = pd.DataFrame(possessions)
            for label, subset in [
                ("All tracked possessions", pdf),
                ("Carry-in possessions", pdf[pdf["has_entry"]]),
                ("Forced-turnover possessions", pdf[pdf["has_turnover"]]),
                ("Possessions with activated D-man", pdf[pdf["has_activation"]]),
            ]:
                if len(subset):
                    print(f"  {label}: {len(subset)} | chance {rate_text(int(subset['chance'].sum()), len(subset))} | goals {int(subset['goal'].sum())}/{len(subset)}")
            pdf.to_csv(REPORTS_DIR / "v4_possession_metrics.csv", index=False)
        else:
            print("  No exported Possession_ID values yet; possession-level V4 metrics will populate after the updated tracker is used.")
        if v4_shots:
            shotdf = pd.DataFrame(v4_shots)
            rows = []
            for category, group in shotdf.groupby("category"):
                rows.append({
                    "Category": category, "Shots": len(group),
                    "Scoring_Chance": int(group["chance"].sum()),
                    "Chance_Rate_%": round(100*group["chance"].mean(), 2),
                    "Actual_Goals": int(group["goal"].sum()),
                    "Goal_Rate_%": round(100*group["goal"].mean(), 2),
                })
            pd.DataFrame(rows).to_csv(REPORTS_DIR / "v4_entry_timing_metrics.csv", index=False)
        pd.DataFrame(audit).to_csv(REPORTS_DIR / "v4_export_audit.csv", index=False)
        pd.DataFrame(v4_gaps).to_csv(REPORTS_DIR / "v4_gap_close_matches.csv", index=False)
    else:
        print("\nNo V4 game exports found in the repository root.")

    print(f"\nReports written to: {REPORTS_DIR}")
    print("Historical entry timing is intentionally excluded until actual Carry-in records exist.")
    print("=" * 72)


if __name__ == "__main__":
    main()
