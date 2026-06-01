import time
import json
import os
import sys
import csv
import statistics
from datetime import datetime

# =====================================================
# IMPORT HX711 DARI FOLDER modules/
# =====================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(CURRENT_DIR, "modules")

if MODULES_DIR not in sys.path:
    sys.path.insert(0, MODULES_DIR)

from hx711 import HX711


# =====================================================
# TAHAP 12 - BACA BERAT AKTUAL LOADCELL
# =====================================================
# Input:
# hasil_tahap11/loadcell_calibration.json
#
# Output:
# hasil_tahap12/latest_actual_weight.json
# hasil_tahap12/actual_weight_log.csv
# hasil_tahap12/archive/actual_weight_YYYYMMDD_HHMMSS.json
# =====================================================

CALIBRATION_FILE = "hasil_tahap11/loadcell_calibration.json"

OUTPUT_DIR = "hasil_tahap12"
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

LATEST_JSON = os.path.join(OUTPUT_DIR, "latest_actual_weight.json")
LOG_CSV = os.path.join(OUTPUT_DIR, "actual_weight_log.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# =========================
# PARAMETER PEMBACAAN
# =========================
READ_SAMPLES = 7
STABLE_FRAME_TARGET = 5

ZERO_THRESHOLD_G = 5.0
MIN_VALID_WEIGHT_G = 20.0

STABILITY_TOLERANCE_G = 8.0
REMOVE_THRESHOLD_G = 15.0
REMOVE_CONFIRM_FRAMES = 5

READ_DELAY_SEC = 0.15


# =====================================================
# LOAD KALIBRASI
# =====================================================

def load_calibration():
    if not os.path.exists(CALIBRATION_FILE):
        raise FileNotFoundError(
            f"{CALIBRATION_FILE} tidak ditemukan. Jalankan Tahap 11 dulu."
        )

    with open(CALIBRATION_FILE, "r") as f:
        data = json.load(f)

    required_keys = [
        "dt_pin_bcm",
        "sck_pin_bcm",
        "calibration_factor",
        "offset_final"
    ]

    for key in required_keys:
        if key not in data:
            raise KeyError(f"Key '{key}' tidak ditemukan di file kalibrasi.")

    return data


# =====================================================
# HX711 INIT
# =====================================================

def init_hx711(dt_pin, sck_pin, calibration_factor):
    hx = HX711(dt_pin, sck_pin)

    hx.setReadingFormat("MSB", "MSB")
    hx.setReferenceUnit(calibration_factor)
    hx.reset()

    time.sleep(0.5)

    return hx


# =====================================================
# READ WEIGHT
# =====================================================

def safe_get_weight(hx):
    try:
        value = hx.getWeight()
        return float(value)
    except Exception:
        return None


def remove_outliers(values):
    if len(values) < 5:
        return values

    median_value = statistics.median(values)
    deviations = [abs(v - median_value) for v in values]
    mad = statistics.median(deviations)

    if mad == 0:
        return values

    threshold = max(mad * 3.0, 8.0)

    filtered = [
        v for v in values
        if abs(v - median_value) <= threshold
    ]

    if len(filtered) < 5:
        return values

    return filtered


def read_actual_weight_once(hx, offset_final):
    readings = []

    while len(readings) < READ_SAMPLES:
        value = safe_get_weight(hx)

        if value is not None:
            readings.append(value)

        time.sleep(0.03)

    filtered = remove_outliers(readings)

    reading_median = statistics.median(filtered)
    reading_mean = statistics.mean(filtered)

    weight_g = reading_median - offset_final

    if abs(weight_g) < ZERO_THRESHOLD_G:
        weight_g = 0.0

    if weight_g < 0:
        weight_g = 0.0

    return {
        "reading_median": float(reading_median),
        "reading_mean": float(reading_mean),
        "actual_weight_g": float(weight_g),
        "actual_weight_kg": float(weight_g / 1000.0),
        "raw_readings": readings,
        "filtered_readings": filtered,
        "sample_count_raw": len(readings),
        "sample_count_filtered": len(filtered)
    }


def is_weight_stable(buffer):
    if len(buffer) < STABLE_FRAME_TARGET:
        return False

    weights = [item["actual_weight_g"] for item in buffer]

    weight_range = max(weights) - min(weights)

    return weight_range <= STABILITY_TOLERANCE_G


def average_weight(buffer):
    weights = [item["actual_weight_g"] for item in buffer]
    readings = [item["reading_median"] for item in buffer]

    return {
        "actual_weight_g": float(statistics.mean(weights)),
        "actual_weight_kg": float(statistics.mean(weights) / 1000.0),
        "reading_median_avg": float(statistics.mean(readings)),
        "weight_min_g": float(min(weights)),
        "weight_max_g": float(max(weights)),
        "weight_range_g": float(max(weights) - min(weights))
    }


# =====================================================
# SAVE OUTPUT
# =====================================================

def append_csv_log(result):
    fieldnames = [
        "measurement_id",
        "timestamp",
        "actual_weight_g",
        "actual_weight_kg",
        "stable",
        "weight_range_g",
        "reading_median_avg",
        "calibration_factor",
        "offset_final",
        "json_file"
    ]

    file_exists = os.path.exists(LOG_CSV)

    row = {key: result.get(key, "") for key in fieldnames}

    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def save_actual_weight(result):
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    measurement_id = f"actual_weight_{timestamp_file}"

    archive_json = os.path.join(
        ARCHIVE_DIR,
        f"{measurement_id}.json"
    )

    result["measurement_id"] = measurement_id
    result["json_file"] = archive_json

    with open(LATEST_JSON, "w") as f:
        json.dump(result, f, indent=4)

    with open(archive_json, "w") as f:
        json.dump(result, f, indent=4)

    append_csv_log(result)

    return archive_json


# =====================================================
# MAIN
# =====================================================

def main():
    print("=====================================================")
    print("TAHAP 12 - BACA BERAT AKTUAL LOADCELL")
    print("=====================================================")

    calibration = load_calibration()

    dt_pin = int(calibration["dt_pin_bcm"])
    sck_pin = int(calibration["sck_pin_bcm"])
    calibration_factor = float(calibration["calibration_factor"])
    offset_final = float(calibration["offset_final"])

    print(f"DT_PIN             : GPIO{dt_pin}")
    print(f"SCK_PIN            : GPIO{sck_pin}")
    print(f"Calibration factor : {calibration_factor:.6f}")
    print(f"Offset final       : {offset_final:.3f}")
    print("=====================================================")
    print("")
    print("Instruksi:")
    print("1. Kosongkan platform. Berat harus mendekati 0 g.")
    print("2. Letakkan paket/beban.")
    print("3. Jika berat stabil, data otomatis disimpan.")
    print("4. Ambil paket untuk reset.")
    print("5. Tekan CTRL + C untuk berhenti.")
    print("=====================================================")
    print("")

    hx = init_hx711(dt_pin, sck_pin, calibration_factor)

    state = "WAITING_OBJECT"
    stable_buffer = []
    remove_counter = 0
    saved_count = 0

    while True:
        data = read_actual_weight_once(hx, offset_final)
        weight_g = data["actual_weight_g"]

        if weight_g < MIN_VALID_WEIGHT_G:
            stable_buffer = []

            if state == "OBJECT_SAVED_WAIT_REMOVAL":
                remove_counter += 1

                print(
                    f"Berat={weight_g:.2f} g | "
                    f"Status: MENUNGGU BEBAN DIANGKAT {remove_counter}/{REMOVE_CONFIRM_FRAMES}"
                )

                if remove_counter >= REMOVE_CONFIRM_FRAMES:
                    state = "WAITING_OBJECT"
                    remove_counter = 0
                    print("Platform kosong. Siap beban baru.")

            else:
                state = "WAITING_OBJECT"
                remove_counter = 0

                print(
                    f"Berat={weight_g:.2f} g | "
                    f"Status: SIAP BEBAN BARU"
                )

            time.sleep(READ_DELAY_SEC)
            continue

        remove_counter = 0

        if state == "WAITING_OBJECT":
            state = "MEASURING"
            stable_buffer = []
            print("Beban terdeteksi. Mulai stabilisasi berat...")

        if state == "MEASURING":
            stable_buffer.append(data)

            if len(stable_buffer) > STABLE_FRAME_TARGET:
                stable_buffer.pop(0)

            print(
                f"Berat={weight_g:.2f} g | "
                f"Status: MENGUKUR... {len(stable_buffer)}/{STABLE_FRAME_TARGET}"
            )

            if is_weight_stable(stable_buffer):
                avg = average_weight(stable_buffer)

                result = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "actual_weight_g": round(avg["actual_weight_g"], 3),
                    "actual_weight_kg": round(avg["actual_weight_kg"], 6),
                    "stable": True,
                    "weight_range_g": round(avg["weight_range_g"], 3),
                    "weight_min_g": round(avg["weight_min_g"], 3),
                    "weight_max_g": round(avg["weight_max_g"], 3),
                    "reading_median_avg": round(avg["reading_median_avg"], 3),

                    "calibration_factor": calibration_factor,
                    "offset_final": offset_final,

                    "dt_pin_bcm": dt_pin,
                    "sck_pin_bcm": sck_pin,

                    "source_calibration_file": CALIBRATION_FILE
                }

                archive_json = save_actual_weight(result)

                saved_count += 1
                state = "OBJECT_SAVED_WAIT_REMOVAL"

                print("")
                print("=====================================================")
                print(f"BERAT AKTUAL TERSIMPAN #{saved_count}")
                print(f"Berat aktual = {result['actual_weight_g']} g")
                print(f"Berat aktual = {result['actual_weight_kg']} kg")
                print(f"Range stabil = {result['weight_range_g']} g")
                print(f"File         = {archive_json}")
                print("Silakan angkat beban dari platform.")
                print("=====================================================")
                print("")

        elif state == "OBJECT_SAVED_WAIT_REMOVAL":
            print(
                f"Berat={weight_g:.2f} g | "
                f"Status: BEBAN SUDAH TERSIMPAN - ANGKAT BEBAN"
            )

        time.sleep(READ_DELAY_SEC)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("")
        print("Program dihentikan oleh user.")