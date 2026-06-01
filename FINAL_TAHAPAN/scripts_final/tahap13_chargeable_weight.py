import json
import os
import csv
from datetime import datetime

# =====================================================
# TAHAP 13 - CHARGEABLE WEIGHT
# =====================================================
# Input:
# 1. hasil_tahap10/latest_measurement.json
# 2. hasil_tahap12/latest_actual_weight.json
#
# Output:
# 1. hasil_tahap13/latest_chargeable_weight.json
# 2. hasil_tahap13/chargeable_log.csv
# 3. hasil_tahap13/archive/chargeable_YYYYMMDD_HHMMSS.json
#
# Rumus:
# chargeable_weight_g = max(berat_volumetrik_g, actual_weight_g)
# =====================================================

VOLUMETRIC_FILE = "hasil_tahap10/latest_measurement.json"
ACTUAL_WEIGHT_FILE = "hasil_tahap12/latest_actual_weight.json"

OUTPUT_DIR = "hasil_tahap13"
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

LATEST_JSON = os.path.join(OUTPUT_DIR, "latest_chargeable_weight.json")
LOG_CSV = os.path.join(OUTPUT_DIR, "chargeable_log.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    with open(path, "r") as f:
        return json.load(f)


def get_required_value(data, key, source_name):
    if key not in data:
        raise KeyError(f"Key '{key}' tidak ditemukan di {source_name}")

    return data[key]


def decide_chargeable_weight(volumetric_data, actual_data):
    panjang_cm = float(get_required_value(volumetric_data, "panjang_cm", VOLUMETRIC_FILE))
    lebar_cm = float(get_required_value(volumetric_data, "lebar_cm", VOLUMETRIC_FILE))
    tinggi_cm = float(get_required_value(volumetric_data, "tinggi_cm", VOLUMETRIC_FILE))

    volume_cm3 = float(get_required_value(volumetric_data, "volume_cm3", VOLUMETRIC_FILE))
    berat_volumetrik_g = float(get_required_value(volumetric_data, "berat_volumetrik_g", VOLUMETRIC_FILE))

    actual_weight_g = float(get_required_value(actual_data, "actual_weight_g", ACTUAL_WEIGHT_FILE))
    actual_weight_kg = actual_weight_g / 1000.0

    if actual_weight_g >= berat_volumetrik_g:
        chargeable_weight_g = actual_weight_g
        chargeable_source = "actual"
        decision_text = "Berat aktual lebih besar atau sama dengan berat volumetrik."
    else:
        chargeable_weight_g = berat_volumetrik_g
        chargeable_source = "volumetric"
        decision_text = "Berat volumetrik lebih besar dari berat aktual."

    chargeable_weight_kg = chargeable_weight_g / 1000.0

    difference_g = abs(actual_weight_g - berat_volumetrik_g)

    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "panjang_cm": round(panjang_cm, 3),
        "lebar_cm": round(lebar_cm, 3),
        "tinggi_cm": round(tinggi_cm, 3),
        "volume_cm3": round(volume_cm3, 3),

        "berat_volumetrik_g": round(berat_volumetrik_g, 3),
        "berat_volumetrik_kg": round(berat_volumetrik_g / 1000.0, 6),

        "berat_aktual_g": round(actual_weight_g, 3),
        "berat_aktual_kg": round(actual_weight_kg, 6),

        "chargeable_weight_g": round(chargeable_weight_g, 3),
        "chargeable_weight_kg": round(chargeable_weight_kg, 6),
        "chargeable_source": chargeable_source,

        "difference_g": round(difference_g, 3),
        "decision_text": decision_text,

        "source_volumetric_file": VOLUMETRIC_FILE,
        "source_actual_weight_file": ACTUAL_WEIGHT_FILE,

        "formula": "chargeable_weight_g = max(berat_volumetrik_g, berat_aktual_g)"
    }

    return result


def append_csv_log(result):
    fieldnames = [
        "measurement_id",
        "timestamp",

        "panjang_cm",
        "lebar_cm",
        "tinggi_cm",
        "volume_cm3",

        "berat_volumetrik_g",
        "berat_aktual_g",

        "chargeable_weight_g",
        "chargeable_weight_kg",
        "chargeable_source",

        "difference_g",
        "decision_text",

        "json_file"
    ]

    file_exists = os.path.exists(LOG_CSV)

    row = {key: result.get(key, "") for key in fieldnames}

    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def save_result(result):
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    measurement_id = f"chargeable_{timestamp_file}"

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


def main():
    print("=====================================================")
    print("TAHAP 13 - CHARGEABLE WEIGHT")
    print("=====================================================")
    print(f"Input volumetrik : {VOLUMETRIC_FILE}")
    print(f"Input aktual     : {ACTUAL_WEIGHT_FILE}")
    print("=====================================================")

    volumetric_data = load_json(VOLUMETRIC_FILE)
    actual_data = load_json(ACTUAL_WEIGHT_FILE)

    result = decide_chargeable_weight(volumetric_data, actual_data)

    archive_json = save_result(result)

    print("")
    print("=====================================================")
    print("HASIL KEPUTUSAN CHARGEABLE WEIGHT")
    print("=====================================================")
    print(f"Panjang              : {result['panjang_cm']} cm")
    print(f"Lebar                : {result['lebar_cm']} cm")
    print(f"Tinggi               : {result['tinggi_cm']} cm")
    print(f"Volume               : {result['volume_cm3']} cm3")
    print("")
    print(f"Berat volumetrik     : {result['berat_volumetrik_g']} g")
    print(f"Berat aktual         : {result['berat_aktual_g']} g")
    print("")
    print(f"Chargeable weight    : {result['chargeable_weight_g']} g")
    print(f"Chargeable source    : {result['chargeable_source']}")
    print(f"Selisih              : {result['difference_g']} g")
    print(f"Keputusan            : {result['decision_text']}")
    print("")
    print(f"File latest          : {LATEST_JSON}")
    print(f"File archive         : {archive_json}")
    print("=====================================================")


if __name__ == "__main__":
    try:
        main()

    except Exception as e:
        print("")
        print("ERROR:", e)