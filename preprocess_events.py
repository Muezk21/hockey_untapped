import os
import pandas as pd

BASE_DIR = r"C:\Users\khanm\OneDrive\Projects\stat_tracker"
RAW_DATA_DIR = os.path.join(BASE_DIR, "raw_data")
ENRICHED_DATA_DIR = os.path.join(BASE_DIR, "enriched_data")

RAW_FOLDERS = {
    "Ducks": "ducks_data",
    "Stars": "stars_data",
    "Islanders": "islanders_data",
    "Leafs": "leafs_data",
    "Red Wings": "redwings_data",
    "Sharks": "sharks_data",
}

# POSSESSION_START: begins a new possession (hotkeys 1 and =)
# ENTRY:            zone entry with the puck already in your possession (hotkeys 3 and 4).
#                   It does NOT start a new possession. It sets the zone-entry time that
#                   shot timing is measured from.
# POSSESSION_END:   Lost Possession (L)
# SHOT:             any shot event
EVENT_MAP = {
    "DZ Blueline Play Shut Down": "POSSESSION_START",
    "OZ Turnover Forced": "POSSESSION_START",
    "DZ → OZ Transition Completed": "ENTRY",
    "Stretch Pass → OZ Possession": "ENTRY",
    "Lost Possession": "POSSESSION_END",
    "Rush Shot (<5s After Zone Entry)": "SHOT",
    "Early Possession Shot (<10s)": "SHOT",
    "Sustained Possession Shot (10–30s)": "SHOT",
    "Extended Possession Shot (>30s)": "SHOT",
    "Shot With Traffic": "SHOT",
    "Low-Value Shot": "SHOT",
    "2nd Scoring Chance (Same Possession)": "SHOT",
    "3rd+ Scoring Chance (Same Possession)": "SHOT",
}

# Your timing keys (5/6/7/X): the shot's timing group is YOUR label.
TIMING_LABELS = {
    "Rush Shot (<5s After Zone Entry)": "Rush",
    "Early Possession Shot (<10s)": "Early",
    "Sustained Possession Shot (10–30s)": "Sustained",
    "Extended Possession Shot (>30s)": "Extended",
}

# Second / third chance in the same possession (hotkeys 8 and 9)
FOLLOWUP_LABELS = {
    "2nd Scoring Chance (Same Possession)": "2nd chance",
    "3rd+ Scoring Chance (Same Possession)": "3rd+ chance",
}

# Shot descriptors (hotkeys 0 and -). Logged on top of a timing shot, they merge into it.
DESCRIPTORS = {
    "Shot With Traffic": "Traffic",
    "Low-Value Shot": "Low-Value",
}

# Events that are real but are not possession starts, entries, ends, or shots.
# Anything NOT in EVENT_MAP and NOT in this set triggers a warning.
KNOWN_OTHER_EVENTS = {
    "Activated D-Man (OZ)",
    "D-Man Aggressive Gap Close",
}

FLAG_COLUMNS = ["Is_Scoring_Chance", "Penalty_Drawn", "Led_To_Goal"]


def normalize_event(name):
    """
    Merge renamed versions of the timing-based shot events into one name each,
    so old and new tracker wording are counted together.
    """
    name = str(name).strip()
    if name in EVENT_MAP or name in KNOWN_OTHER_EVENTS:
        return name

    low = name.lower()
    if low.startswith("rush shot"):
        return "Rush Shot (<5s After Zone Entry)"
    if low.startswith("early possession shot"):
        return "Early Possession Shot (<10s)"
    if low.startswith("sustained possession shot"):
        return "Sustained Possession Shot (10–30s)"
    if low.startswith("extended possession shot"):
        return "Extended Possession Shot (>30s)"
    return name


def find_clock_column(columns):
    for col in columns:
        normalized = col.lower().replace(" ", "").replace("_", "")
        if normalized in {"gameclock", "clock", "time"}:
            return col
    return None


def clock_to_seconds(clock_str):
    try:
        minutes, seconds = map(int, str(clock_str).split(":"))
        return minutes * 60 + seconds
    except:
        return None


def classify_shot(seconds):
    if seconds <= 5:
        return "Rush"
    elif seconds <= 10:
        return "Early"
    elif seconds <= 30:
        return "Sustained"
    else:
        return "Extended"


def merge_same_time_shots(df):
    """
    Shot rows logged at the same period + game clock are ONE shot.
    Example: 'Early Possession Shot' + 'Shot With Traffic' at 08:45.
      - the timing / 2nd / 3rd row is kept as the shot
      - Traffic / Low-Value becomes a descriptor on that shot (column shot_descriptor)
      - S / P / G pressed on any of the rows carries over to the kept shot
    Returns (merged_df, number_of_rows_merged_away).
    """
    df = df.copy()
    df["shot_descriptor"] = ""
    df["merged_rows"] = 0
    idx = list(df.index)
    n = len(idx)
    drop_idx = []

    pos = 0
    while pos < n:
        j = pos
        while (j + 1 < n
               and df.at[idx[j + 1], "Period"] == df.at[idx[pos], "Period"]
               and df.at[idx[j + 1], "clock_seconds"] == df.at[idx[pos], "clock_seconds"]):
            j += 1

        run = idx[pos:j + 1]
        shot_rows = [k for k in run if EVENT_MAP.get(df.at[k, "Event"]) == "SHOT"]

        if shot_rows:
            others = [k for k in shot_rows if df.at[k, "Event"] not in DESCRIPTORS]
            primary = others[0] if others else shot_rows[0]

            # descriptor of the kept row itself (a lone Traffic / Low-Value shot)
            if df.at[primary, "Event"] in DESCRIPTORS:
                df.at[primary, "shot_descriptor"] = DESCRIPTORS[df.at[primary, "Event"]]

            merged_group = [primary]
            for k in shot_rows:
                if k != primary and df.at[k, "Event"] in DESCRIPTORS:
                    df.at[primary, "shot_descriptor"] = DESCRIPTORS[df.at[k, "Event"]]
                    df.at[primary, "merged_rows"] += 1
                    merged_group.append(k)
                    drop_idx.append(k)

            if len(merged_group) > 1:
                for col in FLAG_COLUMNS:
                    if col in df.columns and any(
                            str(df.at[k, col]).strip().upper() == "YES" for k in merged_group):
                        df.at[primary, col] = "YES"
                if "Shot_Result" in df.columns:
                    for k in merged_group:
                        val = df.at[k, "Shot_Result"]
                        if pd.notna(val) and str(val).strip() != "":
                            df.at[primary, "Shot_Result"] = val
                            break

        pos = j + 1

    df = df.drop(index=drop_idx).reset_index(drop=True)
    return df, len(drop_idx)


def clear_old_output(output_path, team_name):
    """
    Delete old enriched CSVs but keep the folder itself.
    (Deleting the whole folder fails when OneDrive has it locked.)
    """
    if not os.path.exists(output_path):
        return
    removed = 0
    for f in os.listdir(output_path):
        if f.endswith(".csv"):
            try:
                os.remove(os.path.join(output_path, f))
                removed += 1
            except PermissionError:
                print(f"⚠️  Could not delete {f} (file in use or OneDrive sync). It will be overwritten.")
    print(f"🗑️  Cleared {removed} old enriched file(s) for {team_name}")


def preprocess_team(team_name, folder_name):
    folder_path = os.path.join(RAW_DATA_DIR, folder_name)

    if not os.path.exists(folder_path):
        print(f"⚠️  Warning: Folder not found: {folder_path}")
        print(f"   Skipping {team_name}...")
        return

    output_path = os.path.join(ENRICHED_DATA_DIR, folder_name)

    csv_files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]

    if not csv_files:
        print(f"⚠️  Warning: No CSV files found in {folder_path}")
        print(f"   Skipping {team_name}...")
        return

    clear_old_output(output_path, team_name)
    os.makedirs(output_path, exist_ok=True)

    unknown_events = {}
    total_merged = 0
    total_followups = 0
    agree = 0
    compared = 0
    followup_events_total = 0
    auto_marked = 0
    goal_no_chance = 0
    timed_total = 0
    timed_with_entry = 0

    for file in csv_files:
        df = pd.read_csv(os.path.join(folder_path, file))
        df.columns = [c.strip() for c in df.columns]

        clock_col = find_clock_column(df.columns)
        if clock_col is None:
            raise ValueError(f"No clock column found in {file}. Columns: {list(df.columns)}")

        df["Event"] = df["Event"].apply(normalize_event)

        # 2nd / 3rd Scoring Chance events ARE scoring chances by definition, so mark them
        # automatically (S is not needed on them).
        if "Is_Scoring_Chance" in df.columns:
            is_followup = df["Event"].isin(list(FOLLOWUP_LABELS.keys()))
            marked_already = df["Is_Scoring_Chance"].astype(str).str.strip().str.upper() == "YES"
            followup_events_total += int(is_followup.sum())
            auto_marked += int((is_followup & ~marked_already).sum())
            df.loc[is_followup, "Is_Scoring_Chance"] = "YES"

        for name in df["Event"].unique():
            if name not in EVENT_MAP and name not in KNOWN_OTHER_EVENTS:
                unknown_events.setdefault(name, []).append(file)

        df["clock_seconds"] = df[clock_col].apply(clock_to_seconds)

        df = df.sort_values(
            by=["Period", "clock_seconds"],
            ascending=[True, False]
        ).reset_index(drop=True)

        # One shot = one row (merge double-logged shots)
        df, merged = merge_same_time_shots(df)
        total_merged += merged

        # Info only: shots marked as leading to a goal but not marked as a scoring chance
        if "Led_To_Goal" in df.columns and "Is_Scoring_Chance" in df.columns:
            is_shot_row = df["Event"].map(lambda e: EVENT_MAP.get(e) == "SHOT")
            has_goal = df["Led_To_Goal"].astype(str).str.strip().str.upper() == "YES"
            has_chance = df["Is_Scoring_Chance"].astype(str).str.strip().str.upper() == "YES"
            goal_no_chance += int((is_shot_row & has_goal & ~has_chance).sum())

        possession_id = 0
        shot_count = 0
        possession_start_time = None
        entry_time = None
        current_period = None
        last_possession_time = None
        followup_pid = None      # possession a follow-up shot may join after a shot ended it
        followup_count = 0

        possession_ids = []
        shot_numbers = []
        time_in_possession_list = []
        derived_shot_types = []
        computed_shot_types = []
        computed_basis_list = []
        label_matches = []

        for _, row in df.iterrows():

            event_name = row["Event"]
            event_type = EVENT_MAP.get(event_name)
            current_time = row["clock_seconds"]
            row_period = row["Period"]

            # RESET ON NEW PERIOD
            if current_period != row_period:
                possession_start_time = None
                last_possession_time = None
                entry_time = None
                shot_count = 0
                followup_pid = None
                followup_count = 0
                current_period = row_period

            # END POSSESSION (Lost Possession)
            if event_type == "POSSESSION_END":
                possession_start_time = None
                last_possession_time = None
                entry_time = None
                shot_count = 0
                followup_pid = None
                followup_count = 0

            # A shot that arrives right after another shot (no event in between) is a
            # follow-up chance in the SAME possession. It does not start a new clock.
            joins_followup = (event_type == "SHOT"
                              and possession_start_time is None
                              and followup_pid is not None)

            # START NEW POSSESSION: hotkeys 1 and =, or any event when none is active
            if not joins_followup and (event_type == "POSSESSION_START" or possession_start_time is None):
                if last_possession_time is None or current_time != last_possession_time:
                    possession_id += 1
                    possession_start_time = current_time
                    last_possession_time = current_time
                    entry_time = None
                    shot_count = 0
                    followup_pid = None
                    followup_count = 0

            # ZONE ENTRY (3 / 4): timing for shots is measured from here
            if event_type == "ENTRY":
                entry_time = current_time

            possession_ids.append(possession_id)

            # SHOT LOGIC
            if event_type == "SHOT":
                if joins_followup:
                    followup_count += 1
                    shot_number = followup_count
                    time_in_possession = None
                    computed = None
                    basis = None
                    total_followups += 1
                else:
                    shot_count += 1
                    shot_number = shot_count
                    if possession_start_time is not None and pd.notna(current_time):
                        time_in_possession = possession_start_time - current_time
                    else:
                        time_in_possession = None

                    # Cross-check category: from the last zone entry; if none was logged,
                    # from the possession start, where it can never be called Rush.
                    computed = None
                    basis = None
                    if entry_time is not None and pd.notna(current_time):
                        computed = classify_shot(entry_time - current_time)
                        basis = "entry"
                    elif time_in_possession is not None:
                        computed = classify_shot(time_in_possession)
                        basis = "possession start"
                        if computed == "Rush":
                            computed = "Early"

                shot_numbers.append(shot_number)
                time_in_possession_list.append(time_in_possession)

                # The shot's group is YOUR label
                if event_name in TIMING_LABELS:
                    group = TIMING_LABELS[event_name]
                elif event_name in FOLLOWUP_LABELS:
                    group = FOLLOWUP_LABELS[event_name]
                else:
                    group = DESCRIPTORS.get(event_name)
                derived_shot_types.append(group)
                computed_shot_types.append(computed)
                computed_basis_list.append(basis)

                if event_name in TIMING_LABELS and not joins_followup:
                    timed_total += 1
                    if basis == "entry":
                        timed_with_entry += 1

                # Only shots with a logged zone entry can be checked against your key
                if event_name in TIMING_LABELS and basis == "entry":
                    matched = (TIMING_LABELS[event_name] == computed)
                    label_matches.append(matched)
                    compared += 1
                    agree += int(matched)
                else:
                    label_matches.append(None)

                # Shot ends the possession (unless it's a 2nd/3rd chance, which keeps it alive)
                if event_name not in FOLLOWUP_LABELS:
                    if not joins_followup:
                        followup_pid = possession_id
                        followup_count = shot_count
                    possession_start_time = None
                    last_possession_time = None
                    entry_time = None
                    shot_count = 0
            else:
                shot_numbers.append(None)
                time_in_possession_list.append(None)
                derived_shot_types.append(None)
                computed_shot_types.append(None)
                computed_basis_list.append(None)
                label_matches.append(None)

        df["possession_id"] = possession_ids
        df["shot_number_in_possession"] = shot_numbers
        df["time_since_possession_start"] = time_in_possession_list
        df["derived_shot_type"] = derived_shot_types
        df["computed_shot_type"] = computed_shot_types
        df["computed_basis"] = computed_basis_list
        df["label_matches_computed"] = label_matches

        df = df.drop(columns=["clock_seconds"])

        output_file = os.path.join(output_path, file)
        df.to_csv(output_file, index=False)

        print(f"✅ Processed {team_name} game: {file}")

    print(f"\n🔎 CHECKS for {team_name}:")
    print(f"   Double-logged shot rows merged into one shot: {total_merged}")
    print(f"   Follow-up shots that joined an earlier possession: {total_followups}")
    print(f"   2nd/3rd chance events logged: {followup_events_total}; "
          f"S was missing on {auto_marked} (auto-marked as scoring chances)")
    print(f"   Shots marked G but not S: {goal_no_chance}")
    print(f"   Timed shots (5/6/7/X): {timed_total}; "
          f"{timed_with_entry} had a zone entry (3 or 4) logged earlier in their possession")
    if compared:
        print(f"   Where an entry was logged, your key matches the entry-based timing: "
              f"{agree} of {compared} ({agree / compared * 100:.0f}%)")

    if unknown_events:
        print(f"\n⚠️  UNRECOGNIZED EVENT NAMES in {team_name} data (these are NOT counted as shots or possessions):")
        for name, files in unknown_events.items():
            print(f"   '{name}' in {len(files)} file(s), e.g. {files[0]}")
        print("   Add them to EVENT_MAP or normalize_event() in preprocess_events.py.\n")


if __name__ == "__main__":
    print(f"Base directory: {BASE_DIR}")
    print(f"Reading from: {RAW_DATA_DIR}")
    print(f"Writing to: {ENRICHED_DATA_DIR}\n")

    for team, folder in RAW_FOLDERS.items():
        preprocess_team(team, folder)

    print("\n✅ Processing complete!")