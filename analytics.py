import pandas as pd
import os

# === SETTINGS ===
BASE_DIR = r"C:\Users\khanm\OneDrive\Projects\stat_tracker"
MASTER_FILE = os.path.join(BASE_DIR, "master_dataset.csv")
REPORTS_DIR = os.path.join(BASE_DIR, "analytics_reports")

GAP_WINDOW = 10            # seconds after a gap close to look for a forced turnover
SECOND_CHANCE_WINDOW = 20  # seconds after a chance shot to look for another chance shot

# Create reports directory
os.makedirs(REPORTS_DIR, exist_ok=True)

# === LOAD DATA ===
print("="*70)
print("🏒 NHL STAT TRACKER - ANALYTICS ENGINE")
print("="*70)
print(f"\n📂 Loading data from: {MASTER_FILE}\n")

if not os.path.exists(MASTER_FILE):
    print(f"❌ ERROR: Master dataset not found!")
    print(f"   Please run master_data_script.py first.")
    exit(1)

df = pd.read_csv(MASTER_FILE)

needed = ['shot_descriptor', 'label_matches_computed', 'derived_shot_type']
missing = [c for c in needed if c not in df.columns]
if missing:
    print(f"❌ ERROR: master_dataset.csv is missing columns: {missing}")
    print("   Run preprocess_events.py and master_data_script.py again, then rerun this script.")
    print("   If the columns are still missing, master_data_script.py is dropping them - tell Claude.")
    exit(1)

print(f"✅ Loaded {len(df):,} events from {df['game_id'].nunique()} games")
print(f"   Teams: {', '.join(sorted(df['team'].unique()))}")
print()

# === HELPER FUNCTIONS ===

def calculate_percentage(numerator, denominator):
    """Safely calculate percentage"""
    if denominator == 0:
        return 0.0
    return (numerator / denominator) * 100

def clock_to_seconds(clock_str):
    """'12:34' -> 754. None if it can't be read."""
    try:
        if pd.isna(clock_str):
            return None
        minutes, seconds = map(int, str(clock_str).split(":"))
        return minutes * 60 + seconds
    except:
        return None

def get_possession_data(team_filter=None):
    """Get possession-level data with outcomes"""
    data = df.copy()
    if team_filter:
        data = data[data['team'] == team_filter]

    # Group by possession
    possessions = data.groupby(['game_id', 'possession_id']).agg({
        'Is_Scoring_Chance': lambda x: (x == 'YES').any(),
        'Led_To_Goal': lambda x: (x == 'YES').any(),
        'shot_number_in_possession': 'max',
        'Event': lambda x: list(x)
    }).reset_index()

    possessions.columns = ['game_id', 'possession_id', 'had_scoring_chance',
                           'led_to_goal', 'num_shots', 'events']

    return possessions

# === METRIC 1: TURNOVER → SCORING CHANCE PIPELINE ===
print("="*70)
print("📊 METRIC 1: TURNOVER → SCORING CHANCE PIPELINE")
print("="*70)

turnover_events = df[df['Event'] == 'OZ Turnover Forced'].copy()
print(f"\n🔍 Found {len(turnover_events)} 'OZ Turnover Forced' events\n")

metric1_results = {}

for team in sorted(df['team'].unique()):
    team_turnovers = turnover_events[turnover_events['team'] == team]

    if len(team_turnovers) == 0:
        continue

    # Get possessions that started with turnovers
    turnover_possessions = team_turnovers[['game_id', 'possession_id']].drop_duplicates()

    # Merge with full data to see outcomes
    outcomes = pd.merge(
        turnover_possessions,
        df[['game_id', 'possession_id', 'Is_Scoring_Chance', 'Led_To_Goal', 'time_since_possession_start']],
        on=['game_id', 'possession_id'],
        how='left'
    )

    # Calculate metrics
    total_turnover_poss = len(turnover_possessions)
    scoring_chances = (outcomes['Is_Scoring_Chance'] == 'YES').sum()
    goals = (outcomes['Led_To_Goal'] == 'YES').sum()

    # Average time to shot after turnover
    shots_after_turnover = outcomes[outcomes['time_since_possession_start'].notna()]
    avg_time_to_shot = shots_after_turnover['time_since_possession_start'].mean() if len(shots_after_turnover) > 0 else 0

    # Compare to non-turnover possessions
    non_turnover_poss = get_possession_data(team)
    non_turnover_poss = non_turnover_poss[~non_turnover_poss.set_index(['game_id', 'possession_id']).index.isin(
        turnover_possessions.set_index(['game_id', 'possession_id']).index
    )]

    non_turnover_chance_rate = calculate_percentage(
        non_turnover_poss['had_scoring_chance'].sum(),
        len(non_turnover_poss)
    )

    turnover_chance_rate = calculate_percentage(scoring_chances, total_turnover_poss)

    metric1_results[team] = {
        'total_turnovers': len(team_turnovers),
        'turnover_possessions': total_turnover_poss,
        'scoring_chances': scoring_chances,
        'goals': goals,
        'turnover_chance_rate': turnover_chance_rate,
        'non_turnover_chance_rate': non_turnover_chance_rate,
        'avg_time_to_shot': avg_time_to_shot
    }

    print(f"{team}:")
    print(f"   Total 'OZ Turnover Forced': {len(team_turnovers)}")
    print(f"   Possessions generated: {total_turnover_poss}")
    print(f"   → Scoring chances: {scoring_chances} ({turnover_chance_rate:.1f}%)")
    print(f"   → Goals: {goals}")
    print(f"   Avg time to shot: {avg_time_to_shot:.1f}s")
    print(f"   📈 Non-turnover chance rate: {non_turnover_chance_rate:.1f}%")
    print(f"   ✨ Turnover advantage: {turnover_chance_rate - non_turnover_chance_rate:+.1f}%\n")

# === METRIC 2: SHOT TIMING (FROM ZONE ENTRY) → SCORING CHANCES ===
print("="*70)
print("📊 METRIC 2: SHOT TIMING (FROM ZONE ENTRY) → SCORING CHANCES")
print("="*70)

shots_with_timing = df[df['derived_shot_type'].notna() & (df['derived_shot_type'] != '')].copy()
print(f"\n🔍 Found {len(shots_with_timing)} shots (double-logged shots already merged into one)\n")

TIMED_GROUPS = ['Rush', 'Early', 'Sustained', 'Extended']
OTHER_GROUPS = ['Traffic', 'Low-Value', '2nd chance', '3rd+ chance']

metric2_results = {}

for team in sorted(df['team'].unique()):
    team_shots = shots_with_timing[shots_with_timing['team'] == team]

    if len(team_shots) == 0:
        continue

    timing_breakdown = {}

    for shot_group in TIMED_GROUPS + OTHER_GROUPS:
        type_shots = team_shots[team_shots['derived_shot_type'] == shot_group]
        chances = (type_shots['Is_Scoring_Chance'] == 'YES').sum()
        goals = (type_shots['Led_To_Goal'] == 'YES').sum()
        timing_breakdown[shot_group] = {
            'count': len(type_shots),
            'chance_rate': calculate_percentage(chances, len(type_shots)),
            'goal_rate': calculate_percentage(goals, len(type_shots))
        }

    metric2_results[team] = timing_breakdown

    print(f"{team}:")
    print("   Timed shots (your 5/6/7/X key, timed from zone entry):")
    for shot_group in TIMED_GROUPS:
        data = timing_breakdown[shot_group]
        print(f"   {shot_group:12} ({data['count']:3} shots): "
              f"Chance rate {data['chance_rate']:5.1f}% | Goal rate {data['goal_rate']:5.1f}%")
    print("   Shots with no timing key (Traffic / Low-Value only, 2nd / 3rd chance):")
    for shot_group in OTHER_GROUPS:
        data = timing_breakdown[shot_group]
        print(f"   {shot_group:12} ({data['count']:3} shots): "
              f"Chance rate {data['chance_rate']:5.1f}% | Goal rate {data['goal_rate']:5.1f}%")

    if timing_breakdown['Rush']['count'] > 0 and timing_breakdown['Extended']['count'] > 0:
        advantage = timing_breakdown['Rush']['chance_rate'] - timing_breakdown['Extended']['chance_rate']
        print(f"   ✨ Rush advantage over Extended: {advantage:+.1f}%")
        if timing_breakdown['Extended']['count'] < 10 or timing_breakdown['Rush']['count'] < 10:
            print("   ⚠️  One of these groups has under 10 shots - treat the comparison as rough")

    checked = team_shots['label_matches_computed'].dropna().map(lambda v: str(v).lower() == 'true')
    if len(checked) > 0:
        print(f"   Cross-check: on the {len(checked)} timed shots that have a logged zone entry, "
              f"your key matches the entry-based timing on {int(checked.sum())} ({checked.mean() * 100:.0f}%)")
    print()

# === METRIC 3: SHOT EFFICIENCY & QUALITY ===
print("="*70)
print("📊 METRIC 3: SHOT EFFICIENCY & QUALITY")
print("="*70)

metric3_results = {}

for team in sorted(df['team'].unique()):
    team_data = df[df['team'] == team]
    possessions = get_possession_data(team)

    # Shots per possession
    possessions_with_shots = possessions[possessions['num_shots'] > 0]
    avg_shots_per_poss = possessions['num_shots'].mean()

    # Scoring chance % per possession
    chance_poss_rate = calculate_percentage(
        possessions['had_scoring_chance'].sum(),
        len(possessions)
    )

    # Shot type quality comparison
    descriptor = team_data['shot_descriptor'].fillna('')
    traffic_shots = team_data[descriptor == 'Traffic']      # every shot tagged Traffic (merged or alone)
    low_value_shots = team_data[descriptor == 'Low-Value']  # every shot tagged Low-Value

    traffic_chance_rate = calculate_percentage(
        (traffic_shots['Is_Scoring_Chance'] == 'YES').sum(),
        len(traffic_shots)
    ) if len(traffic_shots) > 0 else 0

    low_value_chance_rate = calculate_percentage(
        (low_value_shots['Is_Scoring_Chance'] == 'YES').sum(),
        len(low_value_shots)
    ) if len(low_value_shots) > 0 else 0

    # Average possession time before scoring chance
    chances = team_data[team_data['Is_Scoring_Chance'] == 'YES']
    avg_poss_time_for_chance = chances['time_since_possession_start'].mean() if len(chances) > 0 else 0

    metric3_results[team] = {
        'avg_shots_per_poss': avg_shots_per_poss,
        'chance_poss_rate': chance_poss_rate,
        'traffic_shots': len(traffic_shots),
        'traffic_chance_rate': traffic_chance_rate,
        'low_value_shots': len(low_value_shots),
        'low_value_chance_rate': low_value_chance_rate,
        'avg_poss_time_for_chance': avg_poss_time_for_chance
    }

    print(f"\n{team}:")
    print(f"   Avg shots per possession (among possessions with a shot): {avg_shots_per_poss:.2f}")
    print(f"   Possessions with scoring chance: {chance_poss_rate:.1f}%")
    print(f"   'Shot With Traffic' chance rate: {traffic_chance_rate:.1f}% ({len(traffic_shots)} shots)")
    print(f"   'Low-Value Shot' chance rate: {low_value_chance_rate:.1f}% ({len(low_value_shots)} shots)")
    print(f"   Avg time in possession before chance: {avg_poss_time_for_chance:.1f}s")
    if traffic_chance_rate > 0 and low_value_chance_rate > 0:
        quality_diff = traffic_chance_rate - low_value_chance_rate
        print(f"   ✨ Shot quality advantage: {quality_diff:+.1f}%")

print()

# === METRIC 4: D-MEN OFFENSIVE IMPACT ===
print("="*70)
print("📊 METRIC 4: D-MEN OFFENSIVE IMPACT")
print("="*70)

metric4_results = {}

for team in sorted(df['team'].unique()):
    team_data = df[df['team'] == team].copy()
    team_data['clock_seconds'] = team_data['Game_Clock'].apply(clock_to_seconds)

    # Possessions that contain a scoring chance / a goal (any event in the possession marked)
    chance_poss = set(zip(
        team_data.loc[team_data['Is_Scoring_Chance'] == 'YES', 'game_id'],
        team_data.loc[team_data['Is_Scoring_Chance'] == 'YES', 'possession_id']))
    goal_poss = set(zip(
        team_data.loc[team_data['Led_To_Goal'] == 'YES', 'game_id'],
        team_data.loc[team_data['Led_To_Goal'] == 'YES', 'possession_id']))

    # --- Activated D-Man impact ---
    activated_dman = team_data[team_data['Event'] == 'Activated D-Man (OZ)']

    dman_possessions = activated_dman[['game_id', 'possession_id']].drop_duplicates()
    dman_outcomes = pd.merge(
        dman_possessions,
        team_data[['game_id', 'possession_id', 'Is_Scoring_Chance', 'Led_To_Goal']],
        on=['game_id', 'possession_id'],
        how='left'
    )

    dman_chances = (dman_outcomes['Is_Scoring_Chance'] == 'YES').sum()
    dman_chance_rate = calculate_percentage(dman_chances, len(dman_possessions)) if len(dman_possessions) > 0 else 0

    # --- Aggressive gap close → forced turnover within GAP_WINDOW seconds ---
    gap_close = team_data[team_data['Event'] == 'D-Man Aggressive Gap Close']

    # Lookup of forced turnovers: (game, period) -> [(clock_seconds, possession_id), ...]
    turnover_rows = team_data[(team_data['Event'] == 'OZ Turnover Forced') & team_data['clock_seconds'].notna()]
    turn_lookup = {}
    for _, r in turnover_rows.iterrows():
        turn_lookup.setdefault((r['game_id'], r['Period']), []).append((r['clock_seconds'], r['possession_id']))

    def first_turnover_within(game, period, t, window=GAP_WINDOW):
        """Earliest forced turnover in the `window` seconds after clock time t (clock counts down)."""
        hits = [(ts, pid) for ts, pid in turn_lookup.get((game, period), []) if t - window <= ts <= t]
        return max(hits) if hits else None

    gap_with_time = gap_close[gap_close['clock_seconds'].notna()]
    turnovers_after_gap = 0
    gap_chance_poss = 0      # turnover possession contained a scoring chance
    gap_chance_broad = 0     # ...or S was marked on the gap close itself
    gap_goals = 0

    for _, g in gap_with_time.iterrows():
        hit = first_turnover_within(g['game_id'], g['Period'], g['clock_seconds'])
        if hit is None:
            continue
        turnovers_after_gap += 1
        key = (g['game_id'], hit[1])
        poss_chance = key in chance_poss
        gap_marked_chance = (g['Is_Scoring_Chance'] == 'YES')
        poss_goal = key in goal_poss
        gap_marked_goal = (g['Led_To_Goal'] == 'YES')
        gap_chance_poss += int(poss_chance)
        gap_chance_broad += int(poss_chance or gap_marked_chance)
        gap_goals += int(poss_goal or gap_marked_goal)

    gap_turnover_rate = calculate_percentage(turnovers_after_gap, len(gap_close)) if len(gap_close) > 0 else 0

    # Reference: how often is ANY other tracked event followed by a forced turnover within the window?
    ref_events = team_data[
        (~team_data['Event'].isin(['OZ Turnover Forced', 'D-Man Aggressive Gap Close'])) &
        team_data['clock_seconds'].notna()
    ]
    ref_hits = sum(
        1 for _, r in ref_events.iterrows()
        if first_turnover_within(r['game_id'], r['Period'], r['clock_seconds']) is not None
    )
    ref_rate = calculate_percentage(ref_hits, len(ref_events))

    metric4_results[team] = {
        'activated_dman_events': len(activated_dman),
        'dman_possessions': len(dman_possessions),
        'dman_chances': dman_chances,
        'dman_chance_rate': dman_chance_rate,
        'gap_close_events': len(gap_close),
        'turnovers_after_gap': turnovers_after_gap,
        'gap_turnover_rate': gap_turnover_rate,
        'gap_chance_poss': gap_chance_poss,
        'gap_chance_broad': gap_chance_broad,
        'gap_goals': gap_goals,
        'gap_reference_rate': ref_rate
    }

    print(f"\n{team}:")
    print(f"   'Activated D-Man (OZ)' events: {len(activated_dman)}")
    print(f"   → Possessions with activated D-man: {len(dman_possessions)}")
    print(f"   → Scoring chances generated: {dman_chances} ({dman_chance_rate:.1f}%)")
    print(f"   'D-Man Aggressive Gap Close': {len(gap_close)}")
    print(f"   → Turnovers forced within {GAP_WINDOW}s: {turnovers_after_gap} ({gap_turnover_rate:.1f}%)")
    if turnovers_after_gap > 0:
        print(f"      Of those {turnovers_after_gap}:")
        print(f"      • Scoring chance in the turnover possession: {gap_chance_poss} "
              f"({calculate_percentage(gap_chance_poss, turnovers_after_gap):.1f}%)")
        print(f"      • Counting S marked on the gap close itself: {gap_chance_broad} "
              f"({calculate_percentage(gap_chance_broad, turnovers_after_gap):.1f}%)")
        print(f"      • Led to a goal: {gap_goals}")
        if team in metric1_results:
            print(f"      • For context, all turnover possessions: "
                  f"{metric1_results[team]['turnover_chance_rate']:.1f}% had a chance")
    print(f"   Reference: any other tracked event is followed by a forced turnover within "
          f"{GAP_WINDOW}s {ref_rate:.1f}% of the time")

print()

# === METRIC 5: SECOND-CHANCE PRESSURE (time-based) ===
print("="*70)
print("📊 METRIC 5: SECOND-CHANCE PRESSURE")
print("="*70)
print(f"   (After a scoring-chance shot, how often is there another within {SECOND_CHANCE_WINDOW}s?)")

metric5_results = {}

for team in sorted(df['team'].unique()):
    team_data = df[df['team'] == team].copy()
    team_data['clock_seconds'] = team_data['Game_Clock'].apply(clock_to_seconds)
    team_data['period_str'] = team_data['Period'].astype(str)

    is_shot = team_data['shot_number_in_possession'].notna()
    s_rows = team_data[team_data['Is_Scoring_Chance'] == 'YES']
    s_on_shots = int(is_shot[s_rows.index].sum())

    chance_shots = team_data[
        is_shot & (team_data['Is_Scoring_Chance'] == 'YES') & team_data['clock_seconds'].notna()
    ].sort_values(['game_id', 'period_str', 'clock_seconds'], ascending=[True, True, False])

    rows = chance_shots[['game_id', 'period_str', 'clock_seconds']].values.tolist()
    followed = 0
    gaps = []
    for i in range(len(rows) - 1):
        g1, p1, t1 = rows[i]
        g2, p2, t2 = rows[i + 1]
        if g1 == g2 and p1 == p2 and 0 <= t1 - t2 <= SECOND_CHANCE_WINDOW:
            followed += 1
            gaps.append(t1 - t2)

    follow_rate = calculate_percentage(followed, len(chance_shots))
    avg_gap = sum(gaps) / len(gaps) if gaps else 0

    metric5_results[team] = {
        'chance_shots': len(chance_shots),
        'followed': followed,
        'follow_rate': follow_rate,
        'avg_gap': avg_gap,
        's_on_shots': s_on_shots,
        's_total': len(s_rows)
    }

    print(f"\n{team}:")
    print(f"   Scoring chances marked on shot events: {s_on_shots} of {len(s_rows)} "
          f"(the rest are marked on turnovers, D-man events, etc.)")
    print(f"   Chance shots: {len(chance_shots)}")
    print(f"   → Followed by another chance shot within {SECOND_CHANCE_WINDOW}s: {followed} ({follow_rate:.1f}%)")
    if gaps:
        print(f"   Avg gap between them: {avg_gap:.1f}s")
    if len(chance_shots) < 30:
        print(f"   ⚠️  Only {len(chance_shots)} chance shots - treat this rate as rough")

print()

# === EXPORT SUMMARY REPORT ===
print("="*70)
print("💾 EXPORTING SUMMARY REPORTS")
print("="*70)

# Create summary dataframe for each metric
summary_data = []

for team in sorted(df['team'].unique()):
    row = {'Team': team}

    # Metric 1
    if team in metric1_results:
        row['Turnovers_Forced'] = metric1_results[team]['total_turnovers']
        row['Turnover_Chance_Rate_%'] = metric1_results[team]['turnover_chance_rate']
        row['Turnover_Advantage_%'] = metric1_results[team]['turnover_chance_rate'] - metric1_results[team]['non_turnover_chance_rate']

    # Metric 2
    if team in metric2_results:
        row['Rush_Chance_Rate_%'] = metric2_results[team]['Rush']['chance_rate']
        row['Extended_Chance_Rate_%'] = metric2_results[team]['Extended']['chance_rate']
        row['Speed_Advantage_%'] = metric2_results[team]['Rush']['chance_rate'] - metric2_results[team]['Extended']['chance_rate']

    # Metric 3
    if team in metric3_results:
        row['Avg_Shots_Per_Possession'] = metric3_results[team]['avg_shots_per_poss']
        row['Possession_Chance_Rate_%'] = metric3_results[team]['chance_poss_rate']
        row['Traffic_Shot_Chance_Rate_%'] = metric3_results[team]['traffic_chance_rate']

    # Metric 4
    if team in metric4_results:
        m4 = metric4_results[team]
        row['DMan_Activation_Chance_Rate_%'] = m4['dman_chance_rate']
        row['Gap_Close_Turnover_Rate_%'] = m4['gap_turnover_rate']
        row['Gap_Close_Turnover_Reference_%'] = m4['gap_reference_rate']
        row['Gap_Turnover_Chance_Rate_%'] = calculate_percentage(m4['gap_chance_poss'], m4['turnovers_after_gap'])

    # Metric 5
    if team in metric5_results:
        row['Chance_Shots'] = metric5_results[team]['chance_shots']
        row[f'Second_Chance_Within_{SECOND_CHANCE_WINDOW}s_%'] = metric5_results[team]['follow_rate']

    summary_data.append(row)

summary_df = pd.DataFrame(summary_data)
summary_file = os.path.join(REPORTS_DIR, "analytics_summary.csv")
summary_df.to_csv(summary_file, index=False)

print(f"\n✅ Summary report saved: {summary_file}")
print(f"📁 All reports saved to: {REPORTS_DIR}")
print("\n" + "="*70)
print("✅ ANALYTICS COMPLETE!")
print("="*70)