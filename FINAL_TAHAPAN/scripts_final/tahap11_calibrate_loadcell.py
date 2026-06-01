import time
import json
import os
import sys
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
# TAHAP 11 - KALIBRASI LOADCELL HX711
# VERSI SESUAI PROGRAM LAMA YANG SUDAH BERHASIL
# =====================================================
# Output:
# hasil_tahap11/loadcell_calibration.json
#
# Konsep:
# Program lama memakai CALIBRATION_FACTOR = 373.
# Tahap ini mencari faktor baru berdasarkan beban acuan.
# =====================================================

# =========================
# PIN HX711
# Sesuai program lama Anda
# =========================
DT_PIN = 5
SCK_PIN = 6

# =========================
# FAKTOR AWAL
# Dari program lama Anda
# =========================
INITIAL_CALIBRATION_FACTOR = 373.0

# =========================
# SAMPLING
# =========================
OFFSET_SAMPLES = 20
REFERENCE_SAMPLES = 30
FINAL_OFFSET_SAMPLES = 20
TEST_SAMPLES = 7

ZERO_THRESHOLD_G = 5.0

# =========================
# OUTPUT
# =========================
OUTPUT_DIR = "hasil_tahap11"
CALIBRATION_FILE = os.path.join(OUTPUT_DIR, "loadcell_calibration.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# =====================================================
# HX711 INIT
# =====================================================

def init_hx711(calibration_factor):
    hx = HX711(DT_PIN, SCK_PIN)

    hx.setReadingFormat("MSB", "MSB")
    hx.setReferenceUnit(calibration_factor)
    hx.reset()

    time.sleep(0.5)

    return hx


# =====================================================
# READ FUNCTION
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

    threshold = max(mad * 3.0, 10.0)

    filtered = [
        v for v in values
        if abs(v - median_value) <= threshold
    ]

    if len(filtered) < 5:
        return values

    return filtered


def read_stable_weight(hx, sample_count):
    readings = []

    while len(readings) < sample_count:
        value = safe_get_weight(hx)

        if value is not None:
            readings.append(value)

        time.sleep(0.08)

    filtered = remove_outliers(readings)

    return {
        "median": float(statistics.median(filtered)),
        "mean": float(statistics.mean(filtered)),
        "raw_readings": readings,
        "filtered_readings": filtered,
        "sample_count_raw": len(readings),
        "sample_count_filtered": len(filtered)
    }


def calculate_weight_with_offset(value, offset):
    weight = value - offset

    if abs(weight) < ZERO_THRESHOLD_G:
        weight = 0.0

    return weight


def save_calibration(data):
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, indent=4)

    print("")
    print("File kalibrasi berhasil disimpan:")
    print(CALIBRATION_FILE)


# =====================================================
# MAIN
# =====================================================

def main():
    print("=====================================================")
    print("TAHAP 11 - KALIBRASI LOADCELL HX711")
    print("VERSI SESUAI loadcell.py LAMA")
    print("=====================================================")
    print(f"DT_PIN                  : GPIO{DT_PIN}")
    print(f"SCK_PIN                 : GPIO{SCK_PIN}")
    print(f"Initial calibration     : {INITIAL_CALIBRATION_FACTOR}")
    print("Format                  : MSB / MSB")
    print("=====================================================")
    print("")

    print("Instruksi:")
    print("1. Pastikan platform loadcell stabil.")
    print("2. Jangan menyentuh platform saat tare.")
    print("3. Siapkan beban acuan yang diketahui, misalnya 500 g atau 588 g.")
    print("4. Beban acuan harus benar-benar menekan loadcell.")
    print("")

    hx = init_hx711(INITIAL_CALIBRATION_FACTOR)

    input("Kosongkan platform loadcell, lalu tekan ENTER untuk tare awal...")

    print("")
    print("Membaca offset awal tanpa beban...")
    offset_initial_data = read_stable_weight(hx, OFFSET_SAMPLES)
    offset_initial = offset_initial_data["median"]

    print(f"Offset awal median : {offset_initial:.3f}")
    print(f"Offset awal mean   : {offset_initial_data['mean']:.3f}")

    print("")
    reference_weight_g = float(
        input("Masukkan berat acuan dalam gram, contoh 500 atau 588: ").strip()
    )

    if reference_weight_g <= 0:
        print("ERROR: Berat acuan harus lebih dari 0 gram.")
        return

    print("")
    print(f"Letakkan beban acuan {reference_weight_g:.2f} gram di atas platform.")
    input("Jika beban sudah stabil, tekan ENTER...")

    print("")
    print("Membaca berat acuan dengan faktor awal...")
    reference_data = read_stable_weight(hx, REFERENCE_SAMPLES)
    reference_reading = reference_data["median"]

    measured_with_initial_factor = reference_reading - offset_initial

    print(f"Reading beban median    : {reference_reading:.3f}")
    print(f"Reading beban mean      : {reference_data['mean']:.3f}")
    print(f"Hasil terbaca awal      : {measured_with_initial_factor:.3f} g")
    print(f"Berat acuan asli        : {reference_weight_g:.3f} g")

    if abs(measured_with_initial_factor) < 5:
        print("")
        print("ERROR: Perubahan pembacaan terlalu kecil.")
        print("Padahal file loadcell.py bisa membaca, jadi cek apakah beban benar-benar di atas platform.")
        return

    # =================================================
    # RUMUS KALIBRASI
    # =================================================
    # getWeight() ≈ raw / calibration_factor
    #
    # Jika faktor awal 373 membaca 672 g,
    # padahal berat asli 588 g,
    # maka faktor baru = 373 * 672 / 588
    # =================================================

    new_calibration_factor = (
        INITIAL_CALIBRATION_FACTOR
        * measured_with_initial_factor
        / reference_weight_g
    )

    print("")
    print("=====================================================")
    print("HASIL HITUNG FAKTOR BARU")
    print("=====================================================")
    print(f"Faktor awal             : {INITIAL_CALIBRATION_FACTOR:.6f}")
    print(f"Hasil terbaca awal      : {measured_with_initial_factor:.3f} g")
    print(f"Berat acuan asli        : {reference_weight_g:.3f} g")
    print(f"Faktor baru             : {new_calibration_factor:.6f}")
    print("=====================================================")

    print("")
    print("Sekarang sistem akan memakai faktor baru.")
    print("Angkat beban dari platform untuk mengambil offset final.")
    input("Jika platform sudah kosong, tekan ENTER...")

    hx = init_hx711(new_calibration_factor)

    print("")
    print("Membaca offset final dengan faktor baru...")
    final_offset_data = read_stable_weight(hx, FINAL_OFFSET_SAMPLES)
    final_offset = final_offset_data["median"]

    print(f"Offset final median : {final_offset:.3f}")
    print(f"Offset final mean   : {final_offset_data['mean']:.3f}")

    calibration_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "dt_pin_bcm": DT_PIN,
        "sck_pin_bcm": SCK_PIN,
        "reading_format": "MSB/MSB",

        "initial_calibration_factor": INITIAL_CALIBRATION_FACTOR,
        "calibration_factor": new_calibration_factor,

        "reference_weight_g": reference_weight_g,
        "measured_with_initial_factor_g": measured_with_initial_factor,

        "offset_initial": offset_initial,
        "offset_final": final_offset,

        "zero_threshold_g": ZERO_THRESHOLD_G,

        "offset_initial_data": offset_initial_data,
        "reference_data": reference_data,
        "final_offset_data": final_offset_data,

        "formula": "weight_g = hx.getWeight() - offset_final, with hx.setReferenceUnit(calibration_factor)"
    }

    save_calibration(calibration_data)

    print("")
    print("=====================================================")
    print("MODE TEST")
    print("=====================================================")
    print("Letakkan dan angkat beban untuk mengetes hasil.")
    print("Tekan CTRL + C untuk berhenti.")
    print("=====================================================")
    print("")

    while True:
        test_data = read_stable_weight(hx, TEST_SAMPLES)
        reading_now = test_data["median"]

        weight_g = calculate_weight_with_offset(reading_now, final_offset)
        weight_kg = weight_g / 1000.0

        print(
            f"Reading={reading_now:.2f} | "
            f"Berat={weight_g:.2f} g | "
            f"{weight_kg:.4f} kg | "
            f"Factor={new_calibration_factor:.3f}"
        )

        time.sleep(0.35)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("")
        print("Program dihentikan oleh user.")

    except Exception as e:
        print("")
        print("ERROR:", e)