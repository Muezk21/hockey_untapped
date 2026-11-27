import time
import json
import os
from datetime import datetime
from PIL import ImageGrab, ImageEnhance, ImageFilter
import pytesseract
import keyboard
import re
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# === CONFIGURATION ===
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "OCR Tracker" / "broadcast_configs.json"
OUTPUT_DIR = BASE_DIR / "raw_data"

# Default broadcast configurations (you'll customize these)
DEFAULT_CONFIGS = {
    "ESPN": {
        "clock_region": (850, 30, 1050, 80),
        "period_region": (1060, 30, 1120, 80)
    },
    "TNT": {
        "clock_region": (850, 30, 1050, 80),
        "period_region": (1060, 30, 1120, 80)
    },
    "NHL_Network": {
        "clock_region": (850, 30, 1050, 80),
        "period_region": (1060, 30, 1120, 80)
    }
}

# Event hotkeys mapping
EVENT_MAP = {
    "1": "DZ Blueline Play Shut Down",
    "2": "D-Man Aggressive Gap Close",
    "3": "DZ → OZ Transition Completed",
    "4": "Stretch Pass → OZ Possession",
    "5": "Rush Shot (<5s After Zone Entry)",
    "6": "Early Possession Shot (<10s)",
    "7": "Sustained Possession Shot (10–30s)",
    "x": "Extended Possession Shot (>30s)",
    "8": "2nd Scoring Chance (Same Possession)",
    "9": "3rd+ Scoring Chance (Same Possession)",
    "0": "Shot With Traffic",
    "-": "Low-Value Shot",
    "=": "OZ Turnover Forced",
    "a": "Activated D-Man (OZ)",
    "l": "Lost Possession"
}

TEAM_NAMES = {
    "1": "Ducks",
    "2": "Stars",
    "3": "Islanders",
    "4": "Sharks",
    "5": "Maple Leafs",
    "6": "Red Wings"
}

# === HELPER FUNCTIONS ===

def load_configs():
    """Load broadcast configurations from file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIGS

def save_configs(configs):
    """Save broadcast configurations to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=2)
    print(f"✅ Configurations saved to {CONFIG_FILE}")

def capture_region(region):
    """Capture a specific screen region"""
    try:
        screenshot = ImageGrab.grab(bbox=region)
        return screenshot
    except Exception as e:
        print(f"❌ Screen capture error: {e}")
        return None

def clean_clock_text(text):
    """Clean OCR output to extract clock time"""
    # Remove whitespace and common OCR errors
    text = text.strip().replace(" ", "").replace("O", "0").replace("o", "0")
    text = text.replace("I", "1").replace("l", "1").replace("|", "1")
    
    # Look for MM:SS pattern
    match = re.search(r'(\d{1,2}):(\d{2})', text)
    if match:
        minutes, seconds = match.groups()
        return f"{minutes.zfill(2)}:{seconds}"
    return None

def read_clock(config):
    """Read game clock from screen with image preprocessing"""
    image = capture_region(config["clock_region"])
    if image is None:
        return None

    try:
        # Improve image quality for OCR
        image = image.convert("L")
        image = image.resize((image.width * 4, image.height * 4))
        image = ImageEnhance.Contrast(image).enhance(2.5)
        image = image.filter(ImageFilter.SHARPEN)

        custom_config = (
            '--psm 7 -c tessedit_char_whitelist=0123456789:'
        )

        text = pytesseract.image_to_string(
            image,
            config=custom_config
        )

        return clean_clock_text(text)

    except Exception as e:
        print(f"❌ OCR error: {e}")
        return None

def read_period(config):
    """Read current period from screen"""
    image = capture_region(config["period_region"])
    if image is None:
        return None
    
    try:
        custom_config = '--psm 7 -c tessedit_char_whitelist=123OT'
        text = pytesseract.image_to_string(image, config=custom_config)
        text = text.strip().replace("O", "0").replace("o", "0")
        
        # Look for period number or OT
        if "OT" in text.upper():
            return "OT"
        
        match = re.search(r'[123]', text)
        if match:
            return match.group()
        
        return None
    except Exception as e:
        print(f"❌ Period read error: {e}")
        return None

# === MAIN TRACKER CLASS ===

class OCRTracker:
    def __init__(self, broadcast, team, opponent, game_date):
        self.broadcast = broadcast
        self.team = team
        self.opponent = opponent
        self.game_date = game_date
        self.config = load_configs()[broadcast]
        
        self.tracking = False
        self.events = []
        self.current_clock = "20:00"
        self.current_period = "1"
        self.last_clock_update = time.time()
        
        # Hotkey state tracking
        self.pressed_keys = set()
        self.last_event_index = None
        
    def update_clock_and_period(self):
        """Continuously update clock and period from screen"""
        while self.tracking:
            # Read clock
            clock = read_clock(self.config)
            if clock:
                self.current_clock = clock
                self.last_clock_update = time.time()
            
            # Read period every 2 seconds (changes less frequently)
            if time.time() - getattr(self, 'last_period_check', 0) > 2:
                period = read_period(self.config)
                if period:
                    self.current_period = period
                self.last_period_check = time.time()
            
            time.sleep(0.5)  # Update clock twice per second
    
    def log_event(self, event_name):
        """Log an event with current clock and period"""
        event = {
            "team": self.team,
            "clock": self.current_clock,
            "period": self.current_period,
            "event": event_name,
            "chance": "NO",
            "penalty": "NO",
            "goal": "NO",
            "shotResult": ""
        }
        
        self.events.append(event)
        self.last_event_index = len(self.events) - 1
        
        print(f"✅ [{self.current_period}] {self.current_clock} - {event_name}")
    
    def modify_last_event(self, attribute, value):
        """Modify the last logged event"""
        if self.last_event_index is not None and self.last_event_index < len(self.events):
            self.events[self.last_event_index][attribute] = value
            attr_name = {
                'chance': 'SCORING CHANCE',
                'penalty': 'PENALTY DRAWN',
                'goal': 'LED TO GOAL'
            }.get(attribute, attribute)
            print(f"   ↳ Marked as {attr_name}")
    
    def undo_last_event(self):
        """Remove the last logged event"""
        if self.events:
            removed = self.events.pop()
            self.last_event_index = len(self.events) - 1
            print(f"↩️  Undone: {removed['event']}")
    
    def handle_hotkeys(self):
        """Listen for hotkey presses"""
        while self.tracking:
            # Check for event hotkeys
            for key, event_name in EVENT_MAP.items():
                if keyboard.is_pressed(key) and key not in self.pressed_keys:
                    self.pressed_keys.add(key)
                    self.log_event(event_name)
                elif not keyboard.is_pressed(key) and key in self.pressed_keys:
                    self.pressed_keys.discard(key)
            
            # Check for modifier hotkeys
            if keyboard.is_pressed('s') and 's' not in self.pressed_keys:
                self.pressed_keys.add('s')
                self.modify_last_event('chance', 'YES')
            elif not keyboard.is_pressed('s') and 's' in self.pressed_keys:
                self.pressed_keys.discard('s')
            
            if keyboard.is_pressed('p') and 'p' not in self.pressed_keys:
                self.pressed_keys.add('p')
                self.modify_last_event('penalty', 'YES')
            elif not keyboard.is_pressed('p') and 'p' in self.pressed_keys:
                self.pressed_keys.discard('p')
            
            if keyboard.is_pressed('g') and 'g' not in self.pressed_keys:
                self.pressed_keys.add('g')
                self.modify_last_event('goal', 'YES')
            elif not keyboard.is_pressed('g') and 'g' in self.pressed_keys:
                self.pressed_keys.discard('g')
            
            if keyboard.is_pressed('backspace') and 'backspace' not in self.pressed_keys:
                self.pressed_keys.add('backspace')
                self.undo_last_event()
            elif not keyboard.is_pressed('backspace') and 'backspace' in self.pressed_keys:
                self.pressed_keys.discard('backspace')
            
            # Check for stop tracking (ESC)
            if keyboard.is_pressed('esc'):
                self.stop_tracking()
                break
            
            time.sleep(0.1)  # Check 10 times per second
    
    def start_tracking(self):
        """Start the tracking system"""
        self.tracking = True
        print("\n" + "="*70)
        print("🏒 OCR TRACKER STARTED")
        print("="*70)
        print(f"Team: {self.team}")
        print(f"Opponent: {self.opponent}")
        print(f"Date: {self.game_date}")
        print(f"Broadcast: {self.broadcast}")
        print("\n📺 Reading clock from screen...")
        print("⌨️  Press hotkeys to log events")
        print("🛑 Press ESC to stop tracking\n")
        
        # Start clock reading thread
        import threading
        clock_thread = threading.Thread(target=self.update_clock_and_period, daemon=True)
        clock_thread.start()
        
        # Start hotkey listening (blocks until ESC pressed)
        self.handle_hotkeys()
    
    def stop_tracking(self):
        """Stop tracking and export data"""
        self.tracking = False
        print("\n" + "="*70)
        print("🛑 TRACKING STOPPED")
        print("="*70)
        
        if not self.events:
            print("⚠️  No events logged.")
            return
        
        # Export to CSV
        self.export_csv()
    
    def export_csv(self):
        """Export events to CSV file"""
        import csv
        
        # Create team folder if needed
        team_folder = f"{self.team.lower().replace(' ', '_')}_data"
        team_path = os.path.join(OUTPUT_DIR, team_folder)
        os.makedirs(team_path, exist_ok=True)
        
        # Generate filename
        filename = f"{self.team.lower().replace(' ', '_')}_vs_{self.opponent.lower().replace(' ', '_')}_{self.game_date}.csv"
        filepath = os.path.join(team_path, filename)
        
        # Write CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'Team', 'Game_Clock', 'Period', 'Event', 
                'Is_Scoring_Chance', 'Penalty_Drawn', 'Led_To_Goal', 'Shot_Result'
            ])
            writer.writeheader()
            
            for event in self.events:
                writer.writerow({
                    'Team': event['team'],
                    'Game_Clock': event['clock'],
                    'Period': event['period'],
                    'Event': event['event'],
                    'Is_Scoring_Chance': event['chance'],
                    'Penalty_Drawn': event['penalty'],
                    'Led_To_Goal': event['goal'],
                    'Shot_Result': event['shotResult']
                })
        
        print(f"\n✅ Exported {len(self.events)} events to:")
        print(f"   {filepath}")

# === MAIN SETUP ===

def main():
    print("="*70)
    print("🏒 NHL OCR TRACKER - SETUP")
    print("="*70)
    
    # Select broadcast
    configs = load_configs()
    print("\n📺 Available broadcasts:")
    broadcast_list = list(configs.keys())
    for i, broadcast in enumerate(broadcast_list, 1):
        print(f"   {i}. {broadcast}")
    
    broadcast_choice = input("\nSelect broadcast (1-{}): ".format(len(broadcast_list)))
    try:
        broadcast = broadcast_list[int(broadcast_choice) - 1]
    except:
        print("❌ Invalid choice")
        return
    
    # Select team
    print("\n🏒 Select your team:")
    for key, team in TEAM_NAMES.items():
        print(f"   {key}. {team}")
    
    team_choice = input("\nSelect team (1-6): ")
    team = TEAM_NAMES.get(team_choice, "Ducks")
    
    # Get opponent and date
    opponent = input("\n🎯 Opponent name: ")
    game_date = input("📅 Game date (YYYY-MM-DD): ")
    
    if not game_date:
        game_date = datetime.now().strftime("%Y-%m-%d")
    
    # Start tracker
    tracker = OCRTracker(broadcast, team, opponent, game_date)
    
    input("\n⏸️  Position your game video, then press ENTER to start tracking...")
    
    tracker.start_tracking()

if __name__ == "__main__":
    main()