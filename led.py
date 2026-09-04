import sys
import os
import time
import subprocess
import threading
import speech_recognition as sr
from rpi_ws281x import PixelStrip, Color
from gpiozero import InputDevice

# Hibacsatorna némítása a felesleges ALSA/Jack hibaüzenetek miatt
try:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
except Exception:
    pass

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Alapkonfiguráció
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

# LED szalag inicializálása
pixels = PixelStrip(LED_COUNT, 12, 800000, 10, False, 150, 0)
pixels.begin()

is_processing = False
sensor = InputDevice(SENSOR_PIN, pull_up=False)

# Globális állapotok a zökkenőmentes szkennerhez
scanner_index = 0
scanner_direction = 1  # 1 = jobbra, -1 = balra

def clear_leds():
    for i in range(LED_COUNT): 
        pixels.setPixelColor(i, Color(0, 0, 0))
    pixels.show()

def get_kitt_colors(r, g, b):
    main_c = Color(int(r), int(g), int(b))
    side_c = Color(int(r // 17), int(g // 24), int(b // 17))
    return main_c, side_c

def run_listening_animation_step(r=255, g=0, b=0):
    """Egyetlen oda-vissza kétoldali összefutó ciklus (kb. 0.8 másodperc)"""
    main_c, side_c = get_kitt_colors(r, g, b)
    half = LED_COUNT // 2
    
    # Összefutás befelé
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
        
    # Szétfutás kifelé
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
    """Egyetlen fénylépés (nem teljes ciklus!), ami fenntartja a folyamatosságot"""
    global scanner_index, scanner_direction
    
    main_c, side_c = get_kitt_colors(r, g, b)
    
    # LED-ek frissítése az aktuális index alapján
    for k in range(LED_COUNT): 
        pixels.setPixelColor(k, Color(0, 0, 0))
        
    pixels.setPixelColor(scanner_index, main_c)
    if scanner_index > 0: 
        pixels.setPixelColor(scanner_index - 1, side_c)
    if scanner_index < LED_COUNT - 1: 
        pixels.setPixelColor(scanner_index + 1, side_c)
        
    pixels.show()
    time.sleep(speed)
    
    # Index léptetése és az irány megfordítása a széleken
    scanner_index += scanner_direction
    if scanner_index >= LED_COUNT:
        scanner_index = LED_COUNT - 2
        scanner_direction = -1
    elif scanner_index < 0:
        scanner_index = 1
        scanner_direction = 1

def play_audio_with_led(filename, speed=0.08, r=255, g=0, b=0, dynamic_acceleration=False, color_fade_to_yellow=False, dynamic_deceleration=False):
    """Lejátssza az MP3-at, miközben opcionálisan gyorsítja vagy fokozatosan lassítja a LED-et"""
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
                print("[RENDSZER] AZONNALI KIKAPCSOLÁS (FOKOZATOSAN LASSULÓ EFFEKT)...")
                play_audio_with_led("off.mp3", speed=0.08, r=255, g=0, b=0, dynamic_deceleration=True)
                clear_leds()
                subprocess.run(["sudo", "shutdown", "-h", "now"])
                sys.exit(0)
                
            elif any(x in txt for x in ["spm", "spm fokozat", "fokozat", "turbo", "turbó"]):
                print("[KITT] SPM fokozat aktiválása! (FINOMÍTOTT GYORSULÁS EFFEKT)...")
                play_audio_with_led("turbo.mp3", speed=0.08, r=255, g=0, b=0, dynamic_acceleration=True)

            elif any(x in txt for x in ["bemutatás", "bemutatas", "bemutatása", "bemutatasa", "ismertetés", "ismertetes", "ismertetése", "karr"]):
                print("[KITT] KARR mód indítása (LÁGY ÁTMENET PIROSBÓL SÁRGÁBA)...")
                play_audio_with_led("karr.mp3", speed=0.08, r=255, g=0, b=0, color_fade_to_yellow=True)
                
            elif any(x in txt for x in ["frissítés", "frissites", "frissítése", "frissitese"]):
                print("[RENDSZER] MINDEN FÁJL FRISSÍTÉSE A GITHUBRÓL...")
                
                zip_url = "https://github.com/szabovizes-stack/kocsi-kitt.git"
                tmp_zip = "/tmp/kocsi-kitt.zip"
                
                download_cmd = ["wget", "-O", tmp_zip, zip_url]
                result = subprocess.run(download_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if result.returncode == 0:
                    print("[RENDSZER] Letöltés kész! Összes fájl felülírása és kék szkenner...")
                    
                    subprocess.run("rm -rf /tmp/kocsi-kitt*", shell=True)
                    subprocess.run(["unzip", "-o", tmp_zip, "-d", "/tmp"], stdout=subprocess.DEVNULL)
                    
                    fade_start = time.time()
                    while time.time() - fade_start < 5.0:
                        run_scanner_animation_step_single(speed=0.05, r=0, g=0, b=255)
                    clear_leds()
                    
                    extracted_dir = None
                    for item in os.listdir("/tmp"):
                        if item.startswith("kocsi-kitt") and os.path.isdir(os.path.join("/tmp", item)):
                            extracted_dir = os.path.join("/tmp", item)
                            break
                    
                    if extracted_dir:
                        print(f"[RENDSZER] Megtalált mappa: {extracted_dir}. Másolás...")
                        subprocess.run(f"cp -rf {extracted_dir}/* /home/kitt/", shell=True)
                        subprocess.run(f"cp -rf {extracted_dir}/*.mp3 /home/kitt/hangok/ 2>/dev/null", shell=True)
                        subprocess.run(f"cp {extracted_dir}/led.py /home/kitt/led.py", shell=True)
                    
                    if os.path.exists(tmp_zip):
                        os.remove(tmp_zip)
                        
                    subprocess.run(["sudo", "systemctl", "restart", "kitt.service"])
                    sys.exit(0)
                else:
                    print("[RENDSZER] Hiba a letöltésnél.")

            elif any(x in txt for x in ["mutatkozz be", "mutatkoz be"]):
                print("[KITT] Bemutatkozás indítása...")
                play_audio_with_led("bem.mp3", speed=0.08, r=255, g=0, b=0)

            elif "hogy vagy" in txt or "hogyvagy" in txt:
                print("[KITT] Válasz a 'hogy vagy' kérdésre...")
                play_audio_with_led("hogy_vagy.mp3", speed=0.08, r=255, g=0, b=0)

            elif "indul" in txt:
                print("[KITT] Indulás parancs (GYORSABB EFFECT)...")
                play_audio_with_led("indul.mp3", speed=0.04, r=255, g=0, b=0)

            elif any(x in txt for x in ["intro", "inro", "főcímdal", "focimdal", "zene"]):
                print("[KITT] Intro / Zene...")
                play_audio_with_led("intro.mp3", speed=0.08, r=255, g=0, b=0)
            else:
                print("[RENDSZER] Ismeretlen parancs.")
                
    except sr.UnknownValueError:
        print("[GOOGLE] Sikertelen feldolgozás: Nem észlelhető beszéd.")
    except Exception as e:
        print(f"[HIBA] Eszköz vagy kommunikációs hiba: {e}")
        
    is_processing = False
    print("[RENDSZER] Kész az újabb érintésre.\n")

def automatic_timer_worker():
    global is_processing
    while True:
        time.sleep(360)
        for track in subsequent_tracks:
            while is_processing:
                time.sleep(1.0)
            print(f"[RENDSZER] Letelt a 6 perc! Automatikus parancs indítása: {track}...")
            is_processing = True
            play_audio_with_led(track, speed=0.08, r=255, g=0, b=0)
            is_processing = False
            print(f"[RENDSZER] {track} lefutott. Készenlét.\n")
            time.sleep(360)

if __name__ == "__main__":
    clear_leds()
    
    timer_thread = threading.Thread(target=automatic_timer_worker, daemon=True)
    timer_thread.start()
    
    print("[RENDSZER] KITT SIKERESEN ELINDULT! Folyamatos, ugrásmentes szkenner aktív.\n")
    
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
            print("\n[RENDSZER] Manuális leállítás... Fények kikapcsolása.")
            clear_leds()
            sys.exit(0)
