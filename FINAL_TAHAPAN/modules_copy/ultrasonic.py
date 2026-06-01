from gpiozero import DistanceSensor
from time import sleep

# ====================================
# KONFIGURASI SENSOR
# ====================================

# TRIG = GPIO23
# ECHO = GPIO24

sensor = DistanceSensor(
    echo=24,
    trigger=23,
    max_distance=4
)

# Tinggi sensor ke alas (cm)
TINGGI_SENSOR = 32

print("Sensor Ultrasonik Raspberry Pi 5 Siap...")

try:
    while True:

        # ====================================
        # BACA JARAK
        # ====================================

        jarak = sensor.distance * 100
        jarak = round(jarak, 2)

        # ====================================
        # HITUNG TINGGI BENDA
        # ====================================

        tinggi = TINGGI_SENSOR - jarak

        # Hindari negatif
        if tinggi < 0:
            tinggi = 0

        tinggi = round(tinggi, 2)

        # ====================================
        # TAMPILKAN HASIL
        # ====================================

        print("======================")
        print(f"Jarak Sensor : {jarak} cm")
        print(f"Tinggi Benda : {tinggi} cm")
        print("======================")

        sleep(1)

except KeyboardInterrupt:
    print("Program dihentikan")