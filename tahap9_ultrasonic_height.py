import RPi.GPIO as GPIO
import time
import statistics
import json
import csv
import os
from datetime import datetime

# =====================================================
# TAHAP 9 - ULTRASONIC HEIGHT DENGAN KALIBRASI + FILTER
# =====================================================
# Sensor: HC-SR04
#
# Wiring:
# TRIG = GPIO23
# ECHO = GPIO24
#
# Rumus:
# tinggi_objek = jarak_alas_terkalibrasi - jarak_sensor_ke_objek
#
# Revisi:
# - Kalibrasi alas otomatis
# - Median filter
# - Outlier rejection
# - Deadband agar noise kecil tanpa objek dianggap 0 cm
# =====================================================

TRIG = 23
ECHO = 24

OUTPUT_DIR = "hasil_tahap9"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CALIB_FILE = os.path.join(OUTPUT_DIR, "ultrasonic_calibration.json")
LATEST_JSON = os.path.join(OUTPUT_DIR, "latest_height.json")
LOG_CSV = os.path.join(OUTPUT_DIR, "height_log.csv")
LOG_JSONL = os.path.join(OUTPUT_DIR, "height_log.jsonl")

MIN_DISTANCE_CM = 2.0
MAX_DISTANCE_CM = 400.0

# Jumlah sampel pembacaan tiap output
SAMPLE_COUNT = 15

# Jumlah sampel saat kalibrasi alas
BASE_CALIBRATION_SAMPLES = 35

# Timeout echo
TIMEOUT_SECONDS = 0.04

# Noise kecil dianggap 0 cm.
# Dari data Anda, noise tanpa objek sekitar 0.75 cm.
# Jadi 1.2 cm aman untuk menghilangkan false height.
HEIGHT_DEADBAND_CM = 1.2

# Outlier rejection
OUTLIER_MIN_THRESHOLD_CM = 0.45
OUTLIER_MAD_MULTIPLIER = 3.0


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)

    GPIO.output(TRIG, False)
    time.sleep(0.5)


def read_distance_once():
    GPIO.output(TRIG, False)
    time.sleep(0.00002)

    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_time = time.monotonic()

    while GPIO.input(ECHO) == 0:
        if time.monotonic() - start_time > TIMEOUT_SECONDS:
            return None

    pulse_start = time.monotonic()

    while GPIO.input(ECHO) == 1:
        if time.monotonic() - pulse_start > TIMEOUT_SECONDS:
            return None

    pulse_end = time.monotonic()

    pulse_duration = pulse_end - pulse_start

    distance_cm = (pulse_duration * 34300.0) / 2.0

    if distance_cm < MIN_DISTANCE_CM or distance_cm > MAX_DISTANCE_CM:
        return None

    return distance_cm


def remove_outliers(samples):
    if len(samples) < 5:
        return samples

    median_value = statistics.median(samples)
    deviations = [abs(x - median_value) for x in samples]
    mad = statistics.median(deviations)

    threshold = max(
        OUTLIER_MIN_THRESHOLD_CM,
        mad * OUTLIER_MAD_MULTIPLIER
    )

    filtered = [
        x for x in samples
        if abs(x - median_value) <= threshold
    ]

    if len(filtered) < 5:
        return samples

    return filtered


def read_distance_filtered(sample_count=SAMPLE_COUNT):
    samples = []

    for _ in range(sample_count):
        distance = read_distance_once()

        if distance is not None:
            samples.append(distance)

        time.sleep(0.045)

    if len(samples) == 0:
        return None, [], []

    filtered = remove_outliers(samples)

    distance_cm = statistics.median(filtered)

    return distance_cm, samples, filtered


def calibrate_base_distance():
    print("")
    print("=====================================================")
    print("KALIBRASI JARAK SENSOR KE ALAS")
    print("=====================================================")
    print("Kosongkan area kerja.")
    print("Pastikan tidak ada objek, tangan, kabel, atau benda lain di bawah sensor.")
    print("Pastikan sensor menghadap tegak lurus ke alas.")
    print("Tekan ENTER jika sudah siap.")
    print("=====================================================")
    input()

    readings = []

    print("Mengambil sampel kalibrasi alas...")

    for i in range(BASE_CALIBRATION_SAMPLES):
        distance = read_distance_once()

        if distance is not None:
            readings.append(distance)
            print(f"Sampel {i + 1}/{BASE_CALIBRATION_SAMPLES}: {distance:.2f} cm")
        else:
            print(f"Sampel {i + 1}/{BASE_CALIBRATION_SAMPLES}: gagal")

        time.sleep(0.07)

    if len(readings) < 15:
        print("ERROR: Sampel valid terlalu sedikit.")
        print("Cek wiring, posisi sensor, atau pantulan permukaan.")
        return None

    filtered = remove_outliers(readings)
    base_distance_cm = statistics.median(filtered)

    calib_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_distance_cm": round(base_distance_cm, 3),
        "raw_sample_count": len(readings),
        "filtered_sample_count": len(filtered),
        "raw_samples": [round(x, 3) for x in readings],
        "filtered_samples": [round(x, 3) for x in filtered],
        "height_deadband_cm": HEIGHT_DEADBAND_CM
    }

    with open(CALIB_FILE, "w") as f:
        json.dump(calib_data, f, indent=4)

    print("")
    print("Kalibrasi selesai.")
    print(f"Jarak sensor ke alas terkalibrasi: {base_distance_cm:.2f} cm")
    print(f"File kalibrasi disimpan: {CALIB_FILE}")
    print("")

    return base_distance_cm


def load_base_distance():
    if not os.path.exists(CALIB_FILE):
        return None

    with open(CALIB_FILE, "r") as f:
        data = json.load(f)

    return float(data["base_distance_cm"])


def calculate_height(base_distance_cm, distance_cm):
    height_cm = base_distance_cm - distance_cm

    # Noise kecil tanpa objek dianggap nol
    if height_cm <= HEIGHT_DEADBAND_CM:
        return 0.0

    if height_cm < 0:
        return 0.0

    return height_cm


def append_csv_log(data):
    fieldnames = [
        "timestamp",
        "base_distance_cm",
        "distance_cm",
        "height_cm",
        "sample_count_raw",
        "sample_count_filtered",
        "raw_samples",
        "filtered_samples",
        "height_deadband_cm"
    ]

    file_exists = os.path.exists(LOG_CSV)

    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(data)


def append_jsonl_log(data):
    with open(LOG_JSONL, "a") as f:
        f.write(json.dumps(data) + "\n")


def save_latest(data):
    with open(LATEST_JSON, "w") as f:
        json.dump(data, f, indent=4)

    append_csv_log(data)
    append_jsonl_log(data)


def main():
    print("=====================================================")
    print("TAHAP 9 - ULTRASONIC HEIGHT")
    print("VERSI FILTER + DEADBAND")
    print("=====================================================")
    print(f"TRIG GPIO          : {TRIG}")
    print(f"ECHO GPIO          : {ECHO}")
    print(f"Output folder      : {OUTPUT_DIR}")
    print(f"HEIGHT_DEADBAND_CM : {HEIGHT_DEADBAND_CM} cm")
    print("=====================================================")
    print("")

    setup_gpio()

    try:
        base_distance_cm = load_base_distance()

        if base_distance_cm is not None:
            print(f"File kalibrasi ditemukan: {CALIB_FILE}")
            print(f"Jarak alas saat ini: {base_distance_cm:.2f} cm")
            print("")
            print("Pilih:")
            print("1 = pakai kalibrasi lama")
            print("2 = kalibrasi ulang")
            choice = input("Masukkan pilihan [1/2]: ").strip()

            if choice == "2":
                base_distance_cm = calibrate_base_distance()
        else:
            print("File kalibrasi belum ada.")
            base_distance_cm = calibrate_base_distance()

        if base_distance_cm is None:
            print("ERROR: Kalibrasi gagal. Program dihentikan.")
            return

        print("=====================================================")
        print("MODE PEMBACAAN TINGGI")
        print("=====================================================")
        print("Tanpa objek, Height harus menjadi 0.00 cm.")
        print("Dengan objek 5 cm, Height harus mendekati 5.00 cm.")
        print("Tekan CTRL + C untuk berhenti.")
        print("=====================================================")
        print("")

        while True:
            distance_cm, raw_samples, filtered_samples = read_distance_filtered()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if distance_cm is None:
                print("GAGAL membaca sensor ultrasonik.")
                time.sleep(0.5)
                continue

            height_cm = calculate_height(base_distance_cm, distance_cm)

            data = {
                "timestamp": timestamp,
                "base_distance_cm": round(base_distance_cm, 3),
                "distance_cm": round(distance_cm, 3),
                "height_cm": round(height_cm, 3),
                "sample_count_raw": len(raw_samples),
                "sample_count_filtered": len(filtered_samples),
                "raw_samples": [round(x, 3) for x in raw_samples],
                "filtered_samples": [round(x, 3) for x in filtered_samples],
                "height_deadband_cm": HEIGHT_DEADBAND_CM
            }

            save_latest(data)

            print(
                f"Base={base_distance_cm:.2f} cm | "
                f"Distance={distance_cm:.2f} cm | "
                f"Height={height_cm:.2f} cm | "
                f"Raw={len(raw_samples)} | "
                f"Filtered={len(filtered_samples)}"
            )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("")
        print("Program dihentikan oleh user.")

    finally:
        GPIO.cleanup()
        print("GPIO cleanup selesai.")


if __name__ == "__main__":
    main()