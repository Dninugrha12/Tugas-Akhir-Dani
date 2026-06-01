import cv2
import json
import os
import sys
import csv
import time
import statistics
import numpy as np
from datetime import datetime

import tahap10_measure_pxl_ultrasonic as cvsys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(CURRENT_DIR, "modules")

if MODULES_DIR not in sys.path:
    sys.path.insert(0, MODULES_DIR)

from hx711 import HX711

# =====================================================
# IMPORT TAHAP 15 - SERVO PENDORONG
# =====================================================
from tahap15_servo_trigger import (
    setup_servo,
    proses_dorong_paket,
    cleanup_servo
)


# =====================================================
# TAHAP 14 - INTEGRATED CHARGEABLE WEIGHT
# Kamera + Ultrasonik + Loadcell + Chargeable
# + Trigger Servo Pendorong Tahap 15
# =====================================================

FIXED_CAMERA_DEVICE = "/dev/video0"

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30

LOADCELL_CALIBRATION_FILE = "hasil_tahap11/loadcell_calibration.json"

OUTPUT_DIR = "hasil_tahap14"
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

LATEST_JSON = os.path.join(OUTPUT_DIR, "latest_integrated_chargeable.json")
LATEST_DETECTION = os.path.join(OUTPUT_DIR, "latest_detection.jpg")
LATEST_MASK = os.path.join(OUTPUT_DIR, "latest_mask.jpg")
LOG_CSV = os.path.join(OUTPUT_DIR, "integrated_chargeable_log.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Paket di bawah 50 gram dianggap tidak terbaca.
LOADCELL_READ_SAMPLES = 5
LOADCELL_ZERO_THRESHOLD_G = 50.0
MIN_VALID_ACTUAL_WEIGHT_G = 50.0

STABLE_FRAME_TARGET = 4

STABILITY_TOLERANCE_P_CM = 0.80
STABILITY_TOLERANCE_L_CM = 0.80
STABILITY_TOLERANCE_T_CM = 0.60
STABILITY_TOLERANCE_WEIGHT_G = 12.0

REMOVE_CONFIRM_FRAMES = 6

WINDOW_W = 900
WINDOW_H = 720


# =====================================================
# CAMERA
# =====================================================

def open_fixed_camera(device_path=FIXED_CAMERA_DEVICE):
    print(f"Membuka kamera fixed: {device_path}")

    cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    time.sleep(0.5)

    ret, frame = cap.read()

    if not ret or frame is None:
        cap.release()
        print(f"ERROR: Kamera {device_path} gagal dibuka.")
        return None, device_path, None, None

    h, w = frame.shape[:2]

    print(f"Kamera berhasil dibuka: {device_path}")
    print(f"Resolusi aktual: {w} x {h}")

    return cap, device_path, w, h


# =====================================================
# LOADCELL
# =====================================================

def load_loadcell_calibration():
    if not os.path.exists(LOADCELL_CALIBRATION_FILE):
        raise FileNotFoundError(
            f"{LOADCELL_CALIBRATION_FILE} tidak ditemukan. Jalankan Tahap 11 dulu."
        )

    with open(LOADCELL_CALIBRATION_FILE, "r") as f:
        data = json.load(f)

    required = [
        "dt_pin_bcm",
        "sck_pin_bcm",
        "calibration_factor",
        "offset_final"
    ]

    for key in required:
        if key not in data:
            raise KeyError(f"Key '{key}' tidak ditemukan di {LOADCELL_CALIBRATION_FILE}")

    return data


def init_loadcell(calibration):
    dt_pin = int(calibration["dt_pin_bcm"])
    sck_pin = int(calibration["sck_pin_bcm"])
    calibration_factor = float(calibration["calibration_factor"])

    hx = HX711(dt_pin, sck_pin)

    hx.setReadingFormat("MSB", "MSB")
    hx.setReferenceUnit(calibration_factor)
    hx.reset()

    time.sleep(0.5)

    return hx


def safe_get_weight(hx):
    try:
        return float(hx.getWeight())
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

    if len(filtered) < 3:
        return values

    return filtered


def tare_loadcell_live(hx, sample_count=25):
    print("")
    print("=====================================================")
    print("LIVE TARE LOADCELL")
    print("=====================================================")
    print("Kosongkan platform loadcell.")
    print("Jangan menyentuh platform.")
    print("Tekan ENTER jika platform sudah benar-benar kosong.")
    print("=====================================================")
    input()

    readings = []

    while len(readings) < sample_count:
        value = safe_get_weight(hx)

        if value is not None:
            readings.append(value)

        time.sleep(0.05)

    if len(readings) == 0:
        raise RuntimeError("Gagal membaca loadcell saat live tare.")

    filtered = remove_outliers(readings)
    live_offset = statistics.median(filtered)

    print(f"Live offset loadcell: {live_offset:.3f}")
    print("Loadcell siap digunakan.")
    print("")

    return float(live_offset)


def read_actual_weight_once(hx, offset_final):
    readings = []

    while len(readings) < LOADCELL_READ_SAMPLES:
        value = safe_get_weight(hx)

        if value is not None:
            readings.append(value)

        time.sleep(0.025)

    if len(readings) == 0:
        return {
            "reading_median": 0.0,
            "reading_mean": 0.0,
            "actual_weight_g": 0.0,
            "actual_weight_kg": 0.0,
            "raw_readings": [],
            "filtered_readings": []
        }

    filtered = remove_outliers(readings)

    reading_median = statistics.median(filtered)
    reading_mean = statistics.mean(filtered)

    weight_g = reading_median - offset_final

    # Semua berat di bawah 50 gram dianggap 0 / tidak terbaca.
    if abs(weight_g) < LOADCELL_ZERO_THRESHOLD_G:
        weight_g = 0.0

    if weight_g < 0:
        weight_g = 0.0

    return {
        "reading_median": float(reading_median),
        "reading_mean": float(reading_mean),
        "actual_weight_g": float(weight_g),
        "actual_weight_kg": float(weight_g / 1000.0),
        "raw_readings": readings,
        "filtered_readings": filtered
    }


# =====================================================
# CHARGEABLE
# =====================================================

def decide_chargeable_weight(berat_volumetrik_g, berat_aktual_g):
    if berat_aktual_g >= berat_volumetrik_g:
        return {
            "chargeable_weight_g": float(berat_aktual_g),
            "chargeable_weight_kg": float(berat_aktual_g / 1000.0),
            "chargeable_source": "actual",
            "decision_text": "Berat aktual lebih besar atau sama dengan berat volumetrik."
        }

    return {
        "chargeable_weight_g": float(berat_volumetrik_g),
        "chargeable_weight_kg": float(berat_volumetrik_g / 1000.0),
        "chargeable_source": "volumetric",
        "decision_text": "Berat volumetrik lebih besar dari berat aktual."
    }


# =====================================================
# OBJECT DETECTION
# =====================================================

def detect_object_tahap14(warped, background, scale, sensor_point):
    if hasattr(cvsys, "detect_object_hybrid"):
        contour, mask, detection_mode = cvsys.detect_object_hybrid(
            warped,
            background,
            scale,
            sensor_point
        )
        return contour, mask, detection_mode

    if hasattr(cvsys, "detect_object_general"):
        try:
            result = cvsys.detect_object_general(
                warped,
                background,
                scale,
                sensor_point
            )
        except TypeError:
            result = cvsys.detect_object_general(
                warped,
                background,
                scale
            )

        if len(result) == 2:
            contour, mask = result
        elif len(result) == 3:
            contour, mask, _ = result
        elif len(result) == 4:
            contour, mask, _, _ = result
        else:
            raise RuntimeError("Format return detect_object_general tidak dikenali.")

        return contour, mask, "background_subtraction"

    raise RuntimeError(
        "Fungsi deteksi tidak ditemukan di tahap10_measure_pxl_ultrasonic.py. "
        "Pastikan file Tahap 10 adalah versi final."
    )


# =====================================================
# STABILITY
# =====================================================

def is_integrated_stable(buffer):
    if len(buffer) < STABLE_FRAME_TARGET:
        return False

    p_values = [x["panjang_cm"] for x in buffer]
    l_values = [x["lebar_cm"] for x in buffer]
    t_values = [x["tinggi_cm"] for x in buffer]
    w_values = [x["berat_aktual_g"] for x in buffer]

    p_range = max(p_values) - min(p_values)
    l_range = max(l_values) - min(l_values)
    t_range = max(t_values) - min(t_values)
    w_range = max(w_values) - min(w_values)

    return (
        p_range <= STABILITY_TOLERANCE_P_CM and
        l_range <= STABILITY_TOLERANCE_L_CM and
        t_range <= STABILITY_TOLERANCE_T_CM and
        w_range <= STABILITY_TOLERANCE_WEIGHT_G
    )


def avg(buffer, key):
    return float(statistics.mean([x[key] for x in buffer]))


def average_integrated(buffer):
    result = {}

    keys = [
        "panjang_cm",
        "lebar_cm",
        "tinggi_cm",
        "volume_cm3",
        "berat_volumetrik_g",
        "berat_volumetrik_kg",
        "berat_aktual_g",
        "berat_aktual_kg",
        "chargeable_weight_g",
        "chargeable_weight_kg",
        "panjang_raw_cm",
        "lebar_raw_cm",
        "tinggi_raw_cm",
        "height_correction_factor",
        "panjang_px",
        "lebar_px",
        "angle",
        "distance_cm",
        "reading_median"
    ]

    for key in keys:
        result[key] = avg(buffer, key)

    result["chargeable_source"] = buffer[-1]["chargeable_source"]
    result["decision_text"] = buffer[-1]["decision_text"]
    result["detection_mode"] = buffer[-1]["detection_mode"]

    weights = [x["berat_aktual_g"] for x in buffer]
    result["actual_weight_range_g"] = max(weights) - min(weights)

    return result


# =====================================================
# SAVE
# =====================================================

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

        "actual_weight_range_g",
        "detection_mode",

        "detection_image",
        "mask_image",
        "json_file"
    ]

    file_exists = os.path.exists(LOG_CSV)

    row = {key: result.get(key, "") for key in fieldnames}

    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def save_integrated_result(annotated, mask, result):
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    measurement_id = f"integrated_{timestamp_file}"

    archive_json = os.path.join(ARCHIVE_DIR, f"{measurement_id}.json")
    archive_detection = os.path.join(ARCHIVE_DIR, f"detection_{timestamp_file}.jpg")
    archive_mask = os.path.join(ARCHIVE_DIR, f"mask_{timestamp_file}.jpg")

    result["measurement_id"] = measurement_id
    result["json_file"] = archive_json
    result["detection_image"] = archive_detection
    result["mask_image"] = archive_mask

    cv2.imwrite(LATEST_DETECTION, annotated)
    cv2.imwrite(LATEST_MASK, mask)

    cv2.imwrite(archive_detection, annotated)
    cv2.imwrite(archive_mask, mask)

    with open(LATEST_JSON, "w") as f:
        json.dump(result, f, indent=4)

    with open(archive_json, "w") as f:
        json.dump(result, f, indent=4)

    append_csv_log(result)

    return archive_json


# =====================================================
# DRAWING
# =====================================================

def draw_text_box(img, text, x, y, text_color, bg_color=(255, 255, 255),
                  font_scale=0.70, thickness=2, padding=6):
    font = cv2.FONT_HERSHEY_SIMPLEX

    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    x1 = x - padding
    y1 = y - th - padding
    x2 = x + tw + padding
    y2 = y + baseline + padding

    cv2.rectangle(img, (x1, y1), (x2, y2), bg_color, -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), 1)

    cv2.putText(
        img,
        text,
        (x, y),
        font,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA
    )


def draw_integrated_panel(img, data):
    BLUE = (255, 0, 0)
    RED = (0, 0, 255)
    BLACK = (0, 0, 0)
    GREEN = (0, 140, 0)
    WHITE = (255, 255, 255)

    x = 20
    y = 35
    gap = 39

    draw_text_box(img, f"P = {data['panjang_cm']:.2f} cm", x, y, BLUE, WHITE)
    draw_text_box(img, f"L = {data['lebar_cm']:.2f} cm", x, y + gap, BLUE, WHITE)
    draw_text_box(img, f"T = {data['tinggi_cm']:.2f} cm", x, y + 2 * gap, BLUE, WHITE)

    draw_text_box(
        img,
        f"Berat Volumetrik = {data['berat_volumetrik_g']:.2f} g",
        x,
        y + 3 * gap,
        RED,
        WHITE
    )

    draw_text_box(
        img,
        f"Berat Aktual = {data['berat_aktual_g']:.2f} g",
        x,
        y + 4 * gap,
        BLACK,
        WHITE
    )

    draw_text_box(
        img,
        f"Chargeable = {data['chargeable_weight_g']:.2f} g ({data['chargeable_source']})",
        x,
        y + 5 * gap,
        GREEN,
        WHITE
    )


def draw_zero_panel(img):
    draw_text_box(
        img,
        "T = 0.00 cm",
        20,
        35,
        (255, 0, 0),
        (255, 255, 255)
    )

    draw_text_box(
        img,
        "Berat Aktual = 0.00 g",
        20,
        74,
        (0, 0, 0),
        (255, 255, 255)
    )


def draw_status(img, text, color):
    if hasattr(cvsys, "draw_status"):
        cvsys.draw_status(img, text, color)
        return

    cv2.putText(
        img,
        text,
        (20, img.shape[0] - 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA
    )


def make_frozen_frame(warped, scale, sensor_point, measurement_box, final_data):
    frozen = warped.copy()

    cvsys.draw_workspace_box(frozen, scale)
    cvsys.draw_sensor_point(frozen, sensor_point)

    if measurement_box is not None:
        cv2.drawContours(frozen, [measurement_box], 0, (0, 255, 0), 2)

    draw_integrated_panel(frozen, final_data)

    return frozen


# =====================================================
# MAIN
# =====================================================

def main():
    print("=====================================================")
    print("TAHAP 14 - INTEGRATED CHARGEABLE WEIGHT")
    print("1x RUN: Kamera + Ultrasonik + Loadcell + Chargeable + Servo Pendorong")
    print("=====================================================")
    print("ATURAN FINAL:")
    print("- Paket di bawah 50 gram dianggap tidak terbaca.")
    print("- Setelah data final tersimpan, servo pendorong tahap 15 aktif otomatis.")
    print("- Setelah servo mendorong paket, sistem menunggu loadcell < 50 gram.")
    print("=====================================================")

    cap = None

    try:
        cvsys.setup_gpio()

        # =====================================================
        # SETUP SERVO PENDORONG TAHAP 15
        # =====================================================
        setup_servo()

        ultrasonic_base_cm = cvsys.load_ultrasonic_base_distance()

        print(f"Base ultrasonik : {ultrasonic_base_cm:.3f} cm")

        loadcell_calibration = load_loadcell_calibration()
        hx = init_loadcell(loadcell_calibration)

        offset_calibration = float(loadcell_calibration["offset_final"])
        calibration_factor = float(loadcell_calibration["calibration_factor"])

        print(f"Loadcell factor          : {calibration_factor:.6f}")
        print(f"Loadcell offset kalibrasi: {offset_calibration:.3f}")

        offset_final = tare_loadcell_live(hx)

        print(f"Loadcell offset live     : {offset_final:.3f}")

        cap, device, frame_w, frame_h = open_fixed_camera(FIXED_CAMERA_DEVICE)

        if cap is None:
            print("ERROR: Kamera tidak bisa dibuka.")
            return

        camera_matrix, dist_coeffs, new_camera_matrix = cvsys.load_calibration(frame_w, frame_h)
        points = cvsys.load_points()
        scale = cvsys.load_scale()

        output_w = int(scale["output_width_px"])
        output_h = int(scale["output_height_px"])

        px_per_cm_x = float(scale["px_per_cm_x"])
        px_per_cm_y = float(scale["px_per_cm_y"])

        print("")
        print("Konfigurasi:")
        print(f"Kamera              : {device}")
        print(f"Warp output         : {output_w} x {output_h}")
        print(f"PX_PER_CM_X         : {px_per_cm_x}")
        print(f"PX_PER_CM_Y         : {px_per_cm_y}")
        print("=====================================================")

        background = cvsys.capture_live_background(
            cap,
            camera_matrix,
            dist_coeffs,
            new_camera_matrix,
            points,
            scale
        )

        sensor_point = cvsys.calibrate_sensor_point(background, scale)

        print("")
        print("Instruksi:")
        print("1. Letakkan paket di area kamera dan pastikan paket menekan platform loadcell.")
        print("2. Paket harus memiliki berat aktual minimal 50 gram.")
        print("3. Pastikan bagian atas paket berada di bawah titik sensor merah.")
        print("4. Tunggu sampai status DATA FINAL TERSIMPAN.")
        print("5. Setelah data final tersimpan, servo akan mendorong paket otomatis.")
        print("6. Setelah paket keluar dari loadcell, sistem siap paket baru.")
        print("7. Tekan Q untuk keluar.")
        print("=====================================================")

        cv2.namedWindow("Tahap 14 - Integrated Chargeable", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tahap 14 - Integrated Chargeable", WINDOW_W, WINDOW_H)

        cv2.namedWindow("Tahap 14 - Mask Objek", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tahap 14 - Mask Objek", WINDOW_W, WINDOW_H)

        empty_mask = np.zeros((output_h, output_w), dtype=np.uint8)

        state = "WAITING_OBJECT"
        stable_buffer = []
        remove_counter = 0
        saved_count = 0

        frozen_base_frame = None
        frozen_mask = None

        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("WARNING: Frame kamera gagal dibaca.")
                continue

            undistorted = cvsys.undistort_frame(
                frame,
                camera_matrix,
                dist_coeffs,
                new_camera_matrix
            )

            warped = cvsys.warp_workspace_margin(
                undistorted,
                points,
                scale
            )

            annotated = warped.copy()

            cvsys.draw_workspace_box(annotated, scale)
            cvsys.draw_sensor_point(annotated, sensor_point)

            actual_data = read_actual_weight_once(hx, offset_final)
            actual_weight_g = actual_data["actual_weight_g"]

            # =====================================================
            # MODE SETELAH DATA FINAL TERSIMPAN
            # Tampilan nilai P/L/T/Berat/Chargeable dikunci.
            # Program hanya memantau apakah paket sudah keluar dari loadcell.
            # =====================================================
            if state == "OBJECT_SAVED_WAIT_REMOVAL":
                if actual_weight_g < MIN_VALID_ACTUAL_WEIGHT_G:
                    remove_counter += 1
                else:
                    remove_counter = 0

                if frozen_base_frame is not None:
                    display = frozen_base_frame.copy()
                else:
                    display = annotated.copy()

                if actual_weight_g < MIN_VALID_ACTUAL_WEIGHT_G:
                    status_text = f"Status: MENUNGGU AREA KOSONG {remove_counter}/{REMOVE_CONFIRM_FRAMES}"
                    status_color = (0, 255, 255)
                else:
                    status_text = "Status: PAKET SUDAH DIDORONG - MENUNGGU LOADCELL KOSONG"
                    status_color = (0, 255, 0)

                draw_status(display, status_text, status_color)

                cv2.imshow("Tahap 14 - Integrated Chargeable", display)
                cv2.imshow("Tahap 14 - Mask Objek", frozen_mask if frozen_mask is not None else empty_mask)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("Keluar dari Tahap 14.")
                    break

                if remove_counter >= REMOVE_CONFIRM_FRAMES:
                    state = "WAITING_OBJECT"
                    stable_buffer = []
                    remove_counter = 0
                    frozen_base_frame = None
                    frozen_mask = None
                    print("Area loadcell sudah kosong. Sistem siap paket baru.")

                continue

            # =====================================================
            # MODE NORMAL
            # =====================================================

            height_data = cvsys.read_height_ultrasonic(ultrasonic_base_cm)

            if height_data is None:
                stable_buffer = []
                state = "WAITING_OBJECT"

                draw_zero_panel(annotated)

                draw_status(
                    annotated,
                    "Status: ULTRASONIK GAGAL MEMBACA",
                    (0, 0, 255)
                )

                cv2.imshow("Tahap 14 - Integrated Chargeable", annotated)
                cv2.imshow("Tahap 14 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

                continue

            tinggi_raw_cm = float(height_data.get("height_raw_cm", height_data["height_cm"]))
            tinggi_cm = float(height_data["height_cm"])

            # Paket < 50 gram dianggap tidak terbaca.
            if actual_weight_g < MIN_VALID_ACTUAL_WEIGHT_G:
                stable_buffer = []
                state = "WAITING_OBJECT"
                remove_counter = 0

                draw_zero_panel(annotated)

                draw_status(
                    annotated,
                    "Status: PAKET < 50 g TIDAK TERBACA - SIAP PAKET BARU",
                    (0, 255, 255)
                )

                cv2.imshow("Tahap 14 - Integrated Chargeable", annotated)
                cv2.imshow("Tahap 14 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

                continue

            contour, mask, detection_mode = detect_object_tahap14(
                warped,
                background,
                scale,
                sensor_point
            )

            if contour is None:
                stable_buffer = []
                state = "WAITING_OBJECT"

                draw_status(
                    annotated,
                    "Status: OBJEK VISUAL BELUM VALID - POSISIKAN DI TITIK SENSOR",
                    (0, 0, 255)
                )

                draw_text_box(
                    annotated,
                    f"T = {tinggi_cm:.2f} cm",
                    20,
                    35,
                    (255, 0, 0),
                    (255, 255, 255)
                )

                draw_text_box(
                    annotated,
                    f"Berat Aktual = {actual_weight_g:.2f} g",
                    20,
                    74,
                    (0, 0, 0),
                    (255, 255, 255)
                )

                cv2.imshow("Tahap 14 - Integrated Chargeable", annotated)
                cv2.imshow("Tahap 14 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

                continue

            measurement = cvsys.measure_contour(
                contour,
                px_per_cm_x,
                px_per_cm_y
            )

            panjang_raw_cm = float(measurement["panjang_raw_cm"])
            lebar_raw_cm = float(measurement["lebar_raw_cm"])

            panjang_cm, lebar_cm, height_factor = cvsys.apply_height_correction(
                panjang_raw_cm,
                lebar_raw_cm,
                tinggi_cm,
                ultrasonic_base_cm
            )

            volume_cm3, berat_volumetrik_kg, berat_volumetrik_g = cvsys.calculate_volume_and_volumetric_weight(
                panjang_cm,
                lebar_cm,
                tinggi_cm
            )

            decision = decide_chargeable_weight(
                berat_volumetrik_g,
                actual_weight_g
            )

            current_data = {
                "panjang_cm": float(panjang_cm),
                "lebar_cm": float(lebar_cm),
                "tinggi_cm": float(tinggi_cm),

                "volume_cm3": float(volume_cm3),

                "berat_volumetrik_g": float(berat_volumetrik_g),
                "berat_volumetrik_kg": float(berat_volumetrik_kg),

                "berat_aktual_g": float(actual_weight_g),
                "berat_aktual_kg": float(actual_weight_g / 1000.0),

                "chargeable_weight_g": float(decision["chargeable_weight_g"]),
                "chargeable_weight_kg": float(decision["chargeable_weight_kg"]),
                "chargeable_source": decision["chargeable_source"],
                "decision_text": decision["decision_text"],

                "panjang_raw_cm": float(panjang_raw_cm),
                "lebar_raw_cm": float(lebar_raw_cm),
                "tinggi_raw_cm": float(tinggi_raw_cm),

                "height_correction_factor": float(height_factor),

                "panjang_px": float(measurement["panjang_px"]),
                "lebar_px": float(measurement["lebar_px"]),
                "angle": float(measurement["angle"]),

                "distance_cm": float(height_data["distance_cm"]),
                "reading_median": float(actual_data["reading_median"]),

                "detection_mode": detection_mode
            }

            cv2.drawContours(annotated, [measurement["box"]], 0, (0, 255, 0), 2)

            draw_integrated_panel(annotated, current_data)

            if state == "WAITING_OBJECT":
                state = "MEASURING"
                stable_buffer = []
                remove_counter = 0
                print("Paket valid terdeteksi. Mulai stabilisasi data final...")

            if state == "MEASURING":
                stable_buffer.append(current_data)

                if len(stable_buffer) > STABLE_FRAME_TARGET:
                    stable_buffer.pop(0)

                draw_status(
                    annotated,
                    f"Status: MENGUKUR DATA FINAL... {len(stable_buffer)}/{STABLE_FRAME_TARGET}",
                    (0, 255, 255)
                )

                if is_integrated_stable(stable_buffer):
                    avg_data = average_integrated(stable_buffer)

                    final_result = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

                        "panjang_cm": round(avg_data["panjang_cm"], 3),
                        "lebar_cm": round(avg_data["lebar_cm"], 3),
                        "tinggi_cm": round(avg_data["tinggi_cm"], 3),

                        "volume_cm3": round(avg_data["volume_cm3"], 3),

                        "berat_volumetrik_g": round(avg_data["berat_volumetrik_g"], 3),
                        "berat_volumetrik_kg": round(avg_data["berat_volumetrik_kg"], 6),

                        "berat_aktual_g": round(avg_data["berat_aktual_g"], 3),
                        "berat_aktual_kg": round(avg_data["berat_aktual_kg"], 6),

                        "chargeable_weight_g": round(avg_data["chargeable_weight_g"], 3),
                        "chargeable_weight_kg": round(avg_data["chargeable_weight_kg"], 6),
                        "chargeable_source": avg_data["chargeable_source"],
                        "decision_text": avg_data["decision_text"],

                        "panjang_raw_cm": round(avg_data["panjang_raw_cm"], 3),
                        "lebar_raw_cm": round(avg_data["lebar_raw_cm"], 3),
                        "tinggi_raw_cm": round(avg_data["tinggi_raw_cm"], 3),

                        "height_correction_factor": round(avg_data["height_correction_factor"], 6),

                        "actual_weight_range_g": round(avg_data["actual_weight_range_g"], 3),

                        "panjang_px": round(avg_data["panjang_px"], 3),
                        "lebar_px": round(avg_data["lebar_px"], 3),
                        "angle": round(avg_data["angle"], 3),

                        "distance_cm": round(avg_data["distance_cm"], 3),
                        "reading_median": round(avg_data["reading_median"], 3),

                        "detection_mode": avg_data["detection_mode"],

                        "ultrasonic_base_cm": round(ultrasonic_base_cm, 3),
                        "loadcell_calibration_factor": calibration_factor,
                        "loadcell_offset_calibration": offset_calibration,
                        "loadcell_offset_live": offset_final,

                        "min_valid_actual_weight_g": MIN_VALID_ACTUAL_WEIGHT_G,
                        "loadcell_zero_threshold_g": LOADCELL_ZERO_THRESHOLD_G,

                        "sensor_point_x": int(sensor_point[0]),
                        "sensor_point_y": int(sensor_point[1]),

                        "source_loadcell_calibration_file": LOADCELL_CALIBRATION_FILE,

                        "formula_volumetric": "berat_volumetrik_g = P x L x T / 6",
                        "formula_chargeable": "chargeable_weight_g = max(berat_volumetrik_g, berat_aktual_g)"
                    }

                    frozen_base_frame = make_frozen_frame(
                        warped,
                        scale,
                        sensor_point,
                        measurement["box"],
                        final_result
                    )

                    frozen_mask = mask.copy()

                    file_frame = frozen_base_frame.copy()

                    draw_status(
                        file_frame,
                        "Status: DATA FINAL TERSIMPAN - SERVO MENDORONG PAKET",
                        (0, 255, 0)
                    )

                    archive_json = save_integrated_result(
                        file_frame,
                        frozen_mask,
                        final_result
                    )

                    # =====================================================
                    # TRIGGER TAHAP 15 - SERVO PENDORONG
                    # Servo aktif setelah data final berhasil tersimpan.
                    # =====================================================
                    print("")
                    print("=====================================================")
                    print("MEMANGGIL TAHAP 15 - SERVO PENDORONG")
                    print("=====================================================")

                    hasil_servo = proses_dorong_paket(
                        final_result["chargeable_weight_g"]
                    )

                    if hasil_servo["status"]:
                        print(f"Servo berhasil mendorong paket layanan {hasil_servo['layanan']}.")
                    else:
                        print(f"Servo tidak aktif: {hasil_servo['pesan']}")

                    print("=====================================================")
                    print("")

                    saved_count += 1
                    state = "OBJECT_SAVED_WAIT_REMOVAL"
                    remove_counter = 0

                    print("")
                    print("=====================================================")
                    print(f"DATA FINAL TERSIMPAN #{saved_count}")
                    print("=====================================================")
                    print(f"Panjang              : {final_result['panjang_cm']} cm")
                    print(f"Lebar                : {final_result['lebar_cm']} cm")
                    print(f"Tinggi               : {final_result['tinggi_cm']} cm")
                    print(f"Volume               : {final_result['volume_cm3']} cm3")
                    print("")
                    print(f"Berat volumetrik     : {final_result['berat_volumetrik_g']} g")
                    print(f"Berat aktual         : {final_result['berat_aktual_g']} g")
                    print(f"Chargeable weight    : {final_result['chargeable_weight_g']} g")
                    print(f"Chargeable source    : {final_result['chargeable_source']}")
                    print(f"Keputusan            : {final_result['decision_text']}")
                    print("")
                    print(f"File latest          : {LATEST_JSON}")
                    print(f"File archive         : {archive_json}")
                    print("Paket sudah didorong oleh servo.")
                    print("Menunggu area loadcell kosong.")
                    print("=====================================================")
                    print("")

            cv2.imshow("Tahap 14 - Integrated Chargeable", annotated)
            cv2.imshow("Tahap 14 - Mask Objek", mask)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("Keluar dari Tahap 14.")
                break

    except KeyboardInterrupt:
        print("")
        print("Program dihentikan oleh user.")

    except Exception as e:
        print("")
        print("ERROR:", e)

    finally:
        if cap is not None:
            cap.release()

        cv2.destroyAllWindows()

        try:
            cleanup_servo()
        except Exception:
            pass

        try:
            cvsys.cleanup_gpio()
        except Exception:
            pass

        print("Cleanup selesai.")


if __name__ == "__main__":
    main()