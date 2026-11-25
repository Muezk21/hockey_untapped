from PIL import ImageGrab
import pytesseract
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Use your saved clock region
import json
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "OCR Tracker" / "broadcast_configs.json"
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

# Get the first broadcast config
broadcast = list(config.keys())[0]
clock_region = config[broadcast]['clock_region']

print(f"Testing clock region: {clock_region}")

# Capture and try to read
img = ImageGrab.grab(bbox=clock_region)
img.save('clock_test.png')
print("Saved clock_test.png - check this image")

text = pytesseract.image_to_string(img, config='--psm 7')
print(f"OCR read: '{text}'")