import pystray
from PIL import Image, ImageDraw
import subprocess
import time
from pynput.keyboard import Controller, Key

keyboard = Controller()

def on_toggle(icon, item):
    keyboard.press(Key.ctrl)
    keyboard.press(Key.alt)
    keyboard.press('v')
    time.sleep(0.05)
    keyboard.release('v')
    keyboard.release(Key.alt)
    keyboard.release(Key.ctrl)

def on_quit(icon, item):
    icon.stop()
    subprocess.run(["pkill", "-f", "python3 main.py"])

def main():
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    
    color = (200, 50, 50, 255) # Keep it red for visibility, but make it a mic
    
    dc.rounded_rectangle([24, 10, 40, 36], radius=8, fill=color)
    
    dc.arc([16, 20, 48, 46], start=0, end=180, fill=color, width=4)
    
    dc.line([32, 46, 32, 54], fill=color, width=4)
    
    dc.line([20, 54, 44, 54], fill=color, width=4)
    
    menu = pystray.Menu(
        pystray.MenuItem("Toggle Vocara Window", on_toggle, default=True),
        pystray.MenuItem("Quit Vocara", on_quit)
    )
    icon = pystray.Icon("Vocara", image, "Vocara", menu)
    icon.run()

if __name__ == "__main__":
    main()
