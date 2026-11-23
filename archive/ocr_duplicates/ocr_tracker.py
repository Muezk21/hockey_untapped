import time
import json
import os
from datetime import datetime
from PIL import ImageGrab
import pytesseract
import keyboard
import re

# === SET TESSERACT PATH ===
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# === CONFIGURATION ===
BASE_DIR = r"C:\Users\khanm\Desktop\stat_tracker"
CONFIG_FILE = os.path.join(BASE_DIR, "broadcast_configs.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "raw_data")

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

# Event hotkeys mapping - ONLY exact single keys
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
    """Read game clock from screen"""
    image = capture_region(config["clock_region"])
    if image is None:
        return None
    
    try:
        # Configure tesseract for single line of text
        custom_config = '--psm 7 -c tessedit_char_whitelist=0123456789:'
        text = pytesseract.image_to_string(image, config=custom_config)
        clock = clean_clock_text(text)
        return clock
    except Exception as e:
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
        self.legend_visible = True
        
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
            
            time.sleep(0.5)
    
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
        """Remove the last logged event - silent"""
        if self.events:
            self.events.pop()
            self.last_event_index = len(self.events) - 1
            print("↩️  Removed last event")
    
    def print_hotkey_reference(self):
        """Print hotkey reference on demand"""
        if not self.legend_visible:
            return
            
        print("\n" + "="*70)
        print("⌨️  HOTKEY REFERENCE")
        print("="*70)
        print("POSSESSION STARTS:")
        print("  1=DZ Blueline | 2=Gap Close | 3=DZ→OZ | 4=Stretch | ==Turnover")
        print("\nSHOTS:")
        print("  5=Rush | 6=Early | 7=Sustained | X=Extended | 8=2nd | 9=3rd+")
        print("  0=Traffic | -=Low Value")
        print("\nOTHER:")
        print("  A=D-Man OZ | L=Lost Possession")
        print("\nMODIFIERS (mark last event):")
        print("  S=Scoring Chance | P=Penalty | G=Goal")
        print("\nCONTROLS:")
        print("  H=Toggle Legend | Backspace=Undo | ESC=Stop & Export")
        print("="*70 + "\n")
    
    def handle_hotkeys(self):
        """Listen for hotkey presses - FIXED to block arrow keys"""
        
        while self.tracking:
            try:
                # Get the actual key event
                event = keyboard.read_event(suppress=False)
                
                # Only process key DOWN events (ignore key UP)
                if event.event_type != keyboard.KEY_DOWN:
                    continue
                
                key_name = event.name.lower()
                
                # BLOCK arrow keys and other navigation keys
                if key_name in ['left', 'right', 'up', 'down', 'home', 'end', 'page up', 'page down']:
                    continue
                
                # Check for help key (H)
                if key_name == 'h':
                    if 'h' not in self.pressed_keys:
                        self.pressed_keys.add('h')
                        self.legend_visible = not self.legend_visible
                        if self.legend_visible:
                            self.print_hotkey_reference()
                        else:
                            print("💤 Legend hidden (press H to show)\n")
                        time.sleep(0.2)
                    continue
                
                # Check for backspace
                if key_name == 'backspace':
                    if 'backspace' not in self.pressed_keys:
                        self.pressed_keys.add('backspace')
                        self.undo_last_event()
                        time.sleep(0.2)
                        self.pressed_keys.discard('backspace')
                    continue
                
                # Check for ESC
                if key_name == 'esc':
                    self.stop_tracking()
                    break
                
                # Check for event hotkeys - ONLY exact single characters
                if key_name in EVENT_MAP:
                    if key_name not in self.pressed_keys:
                        self.pressed_keys.add(key_name)
                        self.log_event(EVENT_MAP[key_name])
                        time.sleep(0.15)
                        self.pressed_keys.discard(key_name)
                    continue
                
                # Check for modifiers (s, p, g)
                if key_name == 's':
                    if 's' not in self.pressed_keys:
                        self.pressed_keys.add('s')
                        self.modify_last_event('chance', 'YES')
                        time.sleep(0.15)
                        self.pressed_keys.discard('s')
                    continue
                
                if key_name == 'p':
                    if 'p' not in self.pressed_keys:
                        self.pressed_keys.add('p')
                        self.modify_last_event('penalty', 'YES')
                        time.sleep(0.15)
                        self.pressed_keys.discard('p')
                    continue
                
                if key_name == 'g':
                    if 'g' not in self.pressed_keys:
                        self.pressed_keys.add('g')
                        self.modify_last_event('goal', 'YES')
                        time.sleep(0.15)
                        self.pressed_keys.discard('g')
                    continue
                    
            except Exception as e:
                continue
        
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
        
        self.print_hotkey_reference()
        
        print("📺 Reading clock from screen...")
        print("⌨️  Press hotkeys to log events")
        print("💡 Press H to toggle legend visibility")
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
        
        self.export_csv()
    
    def export_csv(self):
        """Export events to CSV file"""
        import csv
        
        team_folder = f"{self.team.lower().replace(' ', '_')}_data"
        team_path = os.path.join(OUTPUT_DIR, team_folder)
        os.makedirs(team_path, exist_ok=True)
        
        filename = f"{self.team.lower().replace(' ', '_')}_vs_{self.opponent.lower().replace(' ', '_')}_{self.game_date}.csv"
        filepath = os.path.join(team_path, filename)
        
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
    
    print("\n🏒 Select your team:")
    for key, team in TEAM_NAMES.items():
        print(f"   {key}. {team}")
    
    team_choice = input("\nSelect team (1-6): ")
    team = TEAM_NAMES.get(team_choice, "Ducks")
    
    opponent = input("\n🎯 Opponent name: ")
    game_date = input("📅 Game date (YYYY-MM-DD): ")
    
    if not game_date:
        game_date = datetime.now().strftime("%Y-%m-%d")
    
    tracker = OCRTracker(broadcast, team, opponent, game_date)
    
    input("\n⏸️  Position your game video, then press ENTER to start tracking...")
    
    tracker.start_tracking()

if __name__ == "__main__":
    main()