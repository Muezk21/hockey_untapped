import pandas as pd
import os

# === SETTINGS ===
BASE_DIR = r"C:\Users\khanm\OneDrive\Projects\stat_tracker"
ENRICHED_DATA_DIR = os.path.join(BASE_DIR, "enriched_data")
OUTPUT_FILE = os.path.join(BASE_DIR, "master_dataset.csv")

all_games = []

# Check if enriched data directory exists
if not os.path.exists(ENRICHED_DATA_DIR):
    print(f"❌ ERROR: Enriched data directory not found!")
    print(f"   Looking for: {ENRICHED_DATA_DIR}")
    print(f"   Please run preprocess_events.py first.")
    exit(1)

# Get all team folders
team_folders = [f for f in os.listdir(ENRICHED_DATA_DIR) 
                if os.path.isdir(os.path.join(ENRICHED_DATA_DIR, f))]

if not team_folders:
    print(f"❌ ERROR: No team folders found in {ENRICHED_DATA_DIR}")
    print(f"   Please run preprocess_events.py first.")
    exit(1)

print("📁 Found team folders:", team_folders)
print()

for team_folder in team_folders:
    team_path = os.path.join(ENRICHED_DATA_DIR, team_folder)
    
    # Loop through all enriched CSVs in this team folder
    csv_files = [f for f in os.listdir(team_path) if f.endswith(".csv")]
    
    if not csv_files:
        print(f"⚠️  No CSV files found in {team_folder}, skipping...")
        continue
    
    for file in csv_files:
        file_path = os.path.join(team_path, file)
        
        try:
            df = pd.read_csv(file_path)
            
            # Clean team name: "ducks_data" → "Ducks"
            team_name = team_folder.replace("_data", "").replace("_", " ").title()
            df["team"] = team_name
            
            # Add game identifier
            df["game_id"] = file.replace(".csv", "")
            
            # Extract opponent and date from filename if possible
            # Expected format: team_vs_opponent_YYYY-MM-DD.csv
            if "_vs_" in file:
                parts = file.replace(".csv", "").split("_vs_")
                if len(parts) == 2:
                    opponent_date = parts[1].rsplit("_", 1)
                    if len(opponent_date) == 2:
                        df["opponent"] = opponent_date[0].replace("_", " ").title()
                        df["game_date"] = opponent_date[1]
                    else:
                        df["opponent"] = parts[1].replace("_", " ").title()
                        df["game_date"] = None
            else:
                df["opponent"] = None
                df["game_date"] = None
            
            all_games.append(df)
            print(f"✅ Loaded: {team_name} - {file}")
            
        except Exception as e:
            print(f"❌ Error loading {file}: {e}")
            continue

print()

# Combine everything
if all_games:
    master_df = pd.concat(all_games, ignore_index=True)
    
    # Reorder columns for better readability
    base_cols = ["team", "opponent", "game_date", "game_id", "Period", "Game_Clock"]
    
    # Handle both old and new column names
    clock_col = "Game_Clock" if "Game_Clock" in master_df.columns else (
        "clock" if "clock" in master_df.columns else None
    )
    
    if clock_col and clock_col != "Game_Clock":
        base_cols = ["team", "opponent", "game_date", "game_id", "Period", clock_col]
    
    # Only include base columns that exist
    base_cols = [c for c in base_cols if c in master_df.columns]
    other_cols = [c for c in master_df.columns if c not in base_cols]
    master_df = master_df[base_cols + other_cols]
    
    # Save master dataset
    master_df.to_csv(OUTPUT_FILE, index=False)
    
    print("="*70)
    print("✅ MASTER DATASET CREATED SUCCESSFULLY!")
    print("="*70)
    print(f"📊 Total events: {len(master_df):,}")
    print(f"🏒 Total games: {master_df['game_id'].nunique()}")
    print(f"🔢 Teams tracked: {master_df['team'].nunique()}")
    
    if 'opponent' in master_df.columns and master_df['opponent'].notna().any():
        unique_opponents = master_df['opponent'].nunique()
        print(f"🎯 Unique opponents: {unique_opponents}")
    
    print(f"\n📁 Saved to: {OUTPUT_FILE}")
    
    # Quick stats
    print("\n" + "="*70)
    print("📈 QUICK STATS")
    print("="*70)
    
    if 'possession_id' in master_df.columns:
        total_possessions = master_df.groupby('game_id')['possession_id'].max().sum()
        print(f"   Total possessions tracked: {int(total_possessions):,}")
    
    if 'shot_number_in_possession' in master_df.columns:
        total_shots = master_df['shot_number_in_possession'].notna().sum()
        print(f"   Total shots logged: {total_shots:,}")
    
    if 'Led_To_Goal' in master_df.columns:
        goals = (master_df['Led_To_Goal'] == 'YES').sum()
        print(f"   Total goals: {goals}")
    
    if 'Is_Scoring_Chance' in master_df.columns:
        chances = (master_df['Is_Scoring_Chance'] == 'YES').sum()
        print(f"   Total scoring chances: {chances}")
    
    # Shot type breakdown
    if 'derived_shot_type' in master_df.columns:
        print("\n   Shot Type Distribution:")
        shot_dist = master_df['derived_shot_type'].value_counts()
        for shot_type, count in shot_dist.items():
            if pd.notna(shot_type):
                print(f"      {shot_type}: {count}")
    
    # Event breakdown
    if 'Event' in master_df.columns:
        print("\n   Top 10 Events:")
        event_dist = master_df['Event'].value_counts().head(10)
        for event, count in event_dist.items():
            print(f"      {event}: {count}")
    
    print("="*70)
    
    # Team-by-team summary
    print("\n" + "="*70)
    print("📊 TEAM-BY-TEAM SUMMARY")
    print("="*70)
    
    for team in sorted(master_df['team'].unique()):
        team_data = master_df[master_df['team'] == team]
        games = team_data['game_id'].nunique()
        events = len(team_data)
        
        shots = team_data['shot_number_in_possession'].notna().sum() if 'shot_number_in_possession' in team_data.columns else 0
        chances = (team_data['Is_Scoring_Chance'] == 'YES').sum() if 'Is_Scoring_Chance' in team_data.columns else 0
        goals = (team_data['Led_To_Goal'] == 'YES').sum() if 'Led_To_Goal' in team_data.columns else 0
        
        print(f"\n   {team}:")
        print(f"      Games: {games}")
        print(f"      Events: {events}")
        print(f"      Shots: {shots}")
        print(f"      Scoring Chances: {chances}")
        print(f"      Goals: {goals}")
    
    print("="*70)
    
else:
    print("⚠️ No enriched data found!")
    print(f"Looking in: {ENRICHED_DATA_DIR}")
    print("Please run preprocess_events.py first.")