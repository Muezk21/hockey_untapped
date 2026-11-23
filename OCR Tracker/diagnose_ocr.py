from PIL import ImageGrab
import pytesseract
import json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Load your config
with open(r'C:\Users\khanm\Desktop\stat_tracker\broadcast_configs.json', 'r') as f:
    configs = json.load(f)

# Test each broadcast
for broadcast_name, config in configs.items():
    print(f"\n{'='*50}")
    print(f"Testing: {broadcast_name}")
    print(f"{'='*50}")
    
    clock_region = config['clock_region']
    print(f"Clock region: {clock_region}")
    
    # Capture image
    img = ImageGrab.grab(bbox=clock_region)
    img.save(f'test_{broadcast_name}_clock.png')
    print(f"✅ Saved: test_{broadcast_name}_clock.png")
    
    # Try multiple OCR configs
    configs_to_try = [
        ('Default', ''),
        ('Single line', '--psm 7'),
        ('Single word', '--psm 8'),
        ('Digits only', '--psm 7 -c tessedit_char_whitelist=0123456789:')
    ]
    
    for config_name, ocr_config in configs_to_try:
        try:
            text = pytesseract.image_to_string(img, config=ocr_config)
            print(f"  {config_name}: '{text.strip()}'")
        except Exception as e:
            print(f"  {config_name}: ERROR - {e}")

print("\n" + "="*50)
print("CHECK THE SAVED IMAGES:")
print("="*50)
print("Look at the test_*_clock.png files")
print("Are the numbers visible and clear?")
print("If images are blank/black, the region is wrong")