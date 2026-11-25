import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import ImageGrab, ImageTk
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "OCR Tracker" / "broadcast_configs.json"

class BroadcastCalibrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Broadcast Calibrator")
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.configure(bg='black')
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.regions = {}
        self.current_region = "clock"
        
        # Instructions
        self.instructions = tk.Label(
            self.root, 
            text="Draw a box around the GAME CLOCK\n(Click and drag, then release)",
            font=("Arial", 24, "bold"),
            fg="yellow",
            bg="black"
        )
        self.instructions.place(relx=0.5, rely=0.1, anchor="center")
        
        # Bind events
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.root.quit())
    
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=3
        )
    
    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
    
    def on_release(self, event):
        end_x, end_y = event.x, event.y
        
        # Ensure correct order
        x1, x2 = sorted([self.start_x, end_x])
        y1, y2 = sorted([self.start_y, end_y])
        
        self.regions[f"{self.current_region}_region"] = (x1, y1, x2, y2)
        
        print(f"✅ {self.current_region.title()} region captured: {x1, y1, x2, y2}")
        
        # Move to next region
        if self.current_region == "clock":
            self.current_region = "period"
            self.instructions.config(text="Now draw a box around the PERIOD\n(e.g., '1', '2', '3', or 'OT')")
            self.canvas.delete(self.rect)
            self.rect = None
        else:
            # Done - save and exit
            self.save_configuration()
            self.root.quit()
    
    def save_configuration(self):
        # Ask for broadcast name
        self.root.attributes('-fullscreen', False)
        broadcast_name = simpledialog.askstring("Broadcast Name", "Enter broadcast name (e.g., ESPN, TNT):")
        
        if not broadcast_name:
            broadcast_name = "Custom"
        
        # Load existing configs
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                configs = json.load(f)
        else:
            configs = {}
        
        # Add new configuration
        configs[broadcast_name] = self.regions
        
        # Save
        with open(CONFIG_FILE, 'w') as f:
            json.dump(configs, f, indent=2)
        
        messagebox.showinfo("Success", f"✅ Configuration saved for '{broadcast_name}'!")
        print(f"\n✅ Saved configuration for '{broadcast_name}':")
        print(f"   Clock region: {self.regions['clock_region']}")
        print(f"   Period region: {self.regions['period_region']}")
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    print("="*70)
    print("📺 BROADCAST CALIBRATOR")
    print("="*70)
    print("\n📋 Instructions:")
    print("   1. Have your game video ready and PAUSED")
    print("   2. Make sure the clock and period are visible")
    print("   3. Click and drag to draw boxes around:")
    print("      - Game clock (MM:SS)")
    print("      - Period indicator (1, 2, 3, or OT)")
    print("   4. Configuration will be saved automatically")
    print("\n⚠️  Press ESC to cancel\n")
    
    input("Press ENTER when ready...")
    
    calibrator = BroadcastCalibrator()
    calibrator.run()