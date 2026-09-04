import sys
import os
import time
import subprocess
import threading
import speech_recognition as sr
from rpi_ws281x import PixelStrip, Color
from gpiozero import InputDevice

try:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
except Exception:
    pass

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

LED_COUNT = 12
SOUND_FOLDER = "/home/kitt/hangok"
SENSOR_PIN = 17

subsequent_tracks = [
    "nyomozas.mp3", 
    "parkolo.mp3", 
    "solyomszem.mp3", 
    "spm.mp3", 
    "hangszint.mp3", 
    "csendben_vagy.mp3"
]

pixels = PixelStrip(LED_COUNT, 12, 800000, 10, False, 150, 0)
pixels.begin()

is_processing = False
sensor = InputDevice(SENSOR_PIN, pull_up=False)

scanner_index = 0
scanner_direction = 1

def clear_leds():
    for i in range(LED_COUNT): 
        pixels.setPixelColor(i, Color(0, 0, 0))
    pixels.show()

def get_kitt_colors(r, g, b):
    main_c = Color(int(r), int(g), int(b))
    side_c = Color(int(r // 17), int(g // 24), int(b // 17))
    return main_c, side_c

def run_listening_animation_step(r=255, g=0, b=0):
    main_c, side_c = get_kitt_colors(r, g, b)
    half = LED_COUNT // 2
    for i in range(half):
        for k in range(LED_COUNT): pixels.setPixelColor(k, Color(0, 0, 0))
        left = i
        right = LED_COUNT - 1 - i
        pixels.setPixelColor(left, main_c)
        pixels.setPixelColor(right, main_c)
        if left > 0: pixels.setPixelColor(left - 1, side_c)
        if right < LED_COUNT - 1: pixels.setPixelColor(right + 1, side_c)
        pixels.show()
        time.sleep(0.06)
    for i in range(half - 1, -1, -1):
        for k in range(LED_COUNT): pixels.setPixelColor(k, Color(0, 0, 0))
        left = i
        right = LED_COUNT - 1 - i
        pixels.setPixelColor(left, main_c)
        pixels.setPixelColor(right, main_c)
        if left > 0: pixels.setPixelColor(left - 1, side_c)
        if right < LED_COUNT - 1: pixels.setPixelColor(right + 1, side_c)
        pixels.show()
        time.sleep(0.06)

def run_scanner_animation_step_single(speed=0.08, r=255, g=0, b=0):
    global scanner_index, scanner_direction
    main_c, side_c = get_kitt_colors(r, g, b)
    for k in range(LED_COUNT): 
        pixels.setPixelColor(k, Color(0, 0, 0))
    pixels.setPixelColor(scanner_index, main_c)
    if scanner_index > 0: 
        pixels.setPixelColor(scanner_index - 1, side_c)
    if scanner_index < LED_COUNT - 1: 
        pixels.setPixelColor(scanner_index + 1, side_c)
    pixels.show()
    time.sleep(speed)
    scanner_index += scanner_direction
    if scanner_index >= LED_COUNT:
        scanner_index = LED_COUNT - 2
        scanner_direction = -1
    elif scanner_index < 0:
        scanner_index = 1
        scanner_direction = 1

def play_audio_with_led(filename, speed=0.08, r=255, g=0, b=0, dynamic_acceleration=False, color_fade_to_yellow=False, dynamic_deceleration=False):
    path = os.path.join(SOUND_FOLDER, filename)
    cmd = ["mpg123", "-o", "alsa", "-a", "hw:0,0", "--buffer", "1024", path]
    start_time = time.time()
    estimated_duration = 4.0 
    fade_duration = 2.5  
    current_g = int(g)
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while process.poll() is None:
        current_speed = speed
        elapsed = time.time() - start_time
        if dynamic_acceleration:
            progress = min(elapsed / estimated_duration, 1.0)
            current_speed = 0.08 - (progress * (0.08 - 0.035))
        if dynamic_deceleration:
            progress = min(elapsed / estimated_duration, 1.0)
            current_speed = 0.08 + (progress * (0.25 - 0.08))
        if color_fade_to_yellow:
            fade_progress = min(elapsed / fade_duration, 1.0)
            current_g = int(0 + (fade_progress * 120))
        run_scanner_animation_step_single(current_speed, r=int(r), g=current_g, b=int(b))

def process_and_respond():
    global is_processing, anim_running
    print("\n[KITT] Érintés érzékelve! Átváltás szobai hangrögzítésre...")
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True 
    r.dynamic_energy_adjustment_damping = 0.15
    r.dynamic_energy_ratio = 1.5
    try:
        with sr.Microphone() as source:
            print("[RENDSZER] Környezeti zaj mérése...")
            r.adjust_for_ambient_noise(source, duration=0.5)
            print("[RENDSZER] Beszélhetsz! (Összefutó effekt fut)...")
            anim_running = True
            def animation_worker():
                while anim_running:
                    run_listening_animation_step(r=255, g=0, b=0)
            anim_thread = threading.Thread(target=animation_worker)
            anim_thread.start()
            audio_data = r.record(source, duration=4.0)
            anim_running = False
            anim_thread.join()
        print("[RENDSZER] Hangfelvétel lezárva. Feldolgozás a Google-lel...")
        raw_txt = r.recognize_google(audio_data, language="hu-HU").lower().strip()
        txt = raw_txt.replace(".", "").replace(",", "").replace("!", "").replace("?", "").strip()
        print(f"[GOOGLE] Érzékelt szöveg: '{txt}'")
        if txt:
            if any(x in txt for x in ["leállítás", "leallitas", "kikapcsolás", "kikapcsolas"]):
                print("[RENDSZER] AZONNALI KIKAPCSOLÁS...")
                play_audio_with_led("off.mp3", speed=0.08, r=255, g=0, b=0, dynamic_deceleration=True)
                clear_leds()
                subprocess.run(["sudo", "shutdown", "-h", "now"])
                sys.exit(0)
            elif any(x in txt for x in ["spm", "spm fokozat", "fokozat", "turbo", "turbó"]):
                print("[KITT] SPM fokozat...")
                play_audio_with_led("turbo.mp3", speed=0.08, r=255, g=0, b=0, dynamic_acceleration=True)
            elif any(x in txt for x in ["bemutatás", "bemutatas", "bemutatása", "bemutatasa", "ismertetés", "ismertetes", "ismertetése", "karr"]):
                print("[KITT] KARR mód...")
                play_audio_with_led("karr.mp3", speed=0.08, r=255, g=0, b=0, color_fade_to_yellow=True)
            elif any(x in txt for x in ["frissítés", "frissites", "frissítése", "frissitese"]):
                print("[RENDSZER] Kód frissítése a GitHubról...")
                github_url = "https://raw.githubusercontent.com/szabovizes-stack/kocsi-kitt/refs/heads/main/led.py"
                tmp_path = "/tmp/led_new.py"
                download_cmd = ["wget", "-O", tmp_path, github_url]
                result = subprocess.run(download_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    print("[RENDSZER] Sikeres letöltés! KÉK KITT-szkenner visszajelzés...")
                    
                    # ÚJ JAVÍTÁS: Kék KITT-szkenner pörgetése pontosan 5 másodpercig (r=0, g=0, b=255)
                    fade_start = time.time()
                    while time.time() - fade_start < 5.0:
                        run_scanner_animation_step_single(speed=0.05, r=0, g=0, b=255)
                        
                    clear_leds()
                    subprocess.run(["sudo", "cp", tmp_path, "/home/kitt/led.py"])
                    subprocess.run(["sudo", "systemctl", "restart", "kitt.service"])
                    sys.exit(0)
                else:
                    print("[RENDSZER] Hiba a letöltésnél.")
            elif any(x in txt for x in ["mutatkozz be", "mutatkoz be"]):
                play_audio_with_led("bem.mp3", speed=0.08, r=255, g=0, b=0)
            elif "hogy vagy" in txt or "hogyvagy" in txt:
                play_audio_with_led("hogy_vagy.mp3", speed=0.08, r=255, g=0, b=0)
            elif "indul" in txt:
                play_audio_with_led("indul.mp3", speed=0.04, r=255, g=0, b=0)
            elif any(x in txt for x in ["intro", "inro", "főcímdal", "focimdal", "zene"]):
                play_audio_with_led("intro.mp3", speed=0.08, r=255, g=0, b=0)
            else:
                print("[RENDSZER] Ismeretlen parancs.")
    except sr.UnknownValueError:
        print("[GOOGLE] Nem észlelhető beszéd.")
    except Exception as e:
        print(f"[HIBA] Kommunikációs hiba: {e}")
    is_processing = False
    print("[RENDSZER] Kész az újabb érintésre.\n")

def automatic_timer_worker():
    global is_processing
    while True:
        time.sleep(360)
        for track in subsequent_tracks:
            while is_processing:
                time.sleep(1.0)
            print(f"[RENDSZER] Letelt a 6 perc: {track}...")
            is_processing = True
            play_audio_with_led(track, speed=0.08, r=255, g=0, b=0)
            is_processing = False
            time.sleep(360)

if __name__ == "__main__":
    clear_leds()
    timer_thread = threading.Thread(target=automatic_timer_worker, daemon=True)
    timer_thread.start()
    print("[RENDSZER] KITT SIKERESEN ELINDULT! Folyamatos szkenner aktív.\n")
    while True:
        try:
            if not is_processing:
                run_scanner_animation_step_single(speed=0.08, r=255, g=0, b=0)
            else:
                time.sleep(0.05)
            if sensor.is_active and not is_processing:
                time.sleep(0.03)
                if sensor.is_active:
                    is_processing = True
                    process_and_respond()
                    while sensor.is_active:
                        time.sleep(0.05)
        except KeyboardInterrupt:
            clear_leds()
            sys.exit(0)
