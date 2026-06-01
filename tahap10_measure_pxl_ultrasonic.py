import cv2
import numpy as np
import json
import os
import glob
import re
import time
import csv
import statistics
from datetime import datetime
import RPi.GPIO as GPIO

# =====================================================
# TAHAP 10 - KAMERA + ULTRASONIK
# FINAL HYBRID STABIL:
# - Deteksi kardus/cokelat pakai HSV
# - Objek warna lain fallback ke background subtraction
# - Deteksi dibatasi di sekitar titik sensor
# - Tinggi ultrasonic dibaca dulu
# - Jika T = 0, visual tidak dihitung
# - Tampilan monitor: P, L, T biru background putih
# - Berat volumetrik merah background putih
# =====================================================

# =========================
# FILE INPUT
# =========================
CALIB_FILE = "camera_calibration.npz"
POINTS_FILE = "hasil_tahap4/points_4_corners_undistorted.json"
SCALE_FILE = "hasil_tahap6/pixel_scale.json"
ULTRASONIC_CALIB_FILE = "hasil_tahap9/ultrasonic_calibration.json"

# =========================
# OUTPUT
# =========================
OUTPUT_DIR = "hasil_tahap10"
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

LOG_CSV = os.path.join(OUTPUT_DIR, "measurements_log.csv")
LOG_JSONL = os.path.join(OUTPUT_DIR, "measurements_log.jsonl")
LIVE_BACKGROUND_PATH = os.path.join(OUTPUT_DIR, "latest_live_background.jpg")
SENSOR_POINT_FILE = os.path.join(OUTPUT_DIR, "sensor_point.json")

# =========================
# KAMERA
# =========================
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30

# =========================
# ULTRASONIK HC-SR04
# =========================
TRIG = 23
ECHO = 24

MIN_DISTANCE_CM = 2.0
MAX_DISTANCE_CM = 400.0
TIMEOUT_SECONDS = 0.04

ULTRASONIC_SAMPLE_COUNT = 5

HEIGHT_DEADBAND_CM = 1.2
MIN_VALID_OBJECT_HEIGHT_CM = 1.2

OUTLIER_MIN_THRESHOLD_CM = 0.45
OUTLIER_MAD_MULTIPLIER = 3.0

# =========================
# UKURAN OBJEK UJI
# Ubah sesuai benda uji.
# =========================
ACTUAL_P_CM = 16.5
ACTUAL_L_CM = 12.8
ACTUAL_T_CM = 8.5

# =========================
# KALIBRASI TINGGI
# =========================
# Dimatikan dulu karena setelah posisi sensor berubah,
# kalibrasi 2 titik sebelumnya membuat T terlalu besar.
ENABLE_HEIGHT_CALIBRATION = False

HEIGHT_RAW_POINT_1 = 5.03
HEIGHT_TRUE_POINT_1 = 5.0

HEIGHT_RAW_POINT_2 = 7.628
HEIGHT_TRUE_POINT_2 = 8.5

HEIGHT_CALIB_A = (HEIGHT_TRUE_POINT_2 - HEIGHT_TRUE_POINT_1) / (
    HEIGHT_RAW_POINT_2 - HEIGHT_RAW_POINT_1
)
HEIGHT_CALIB_B = HEIGHT_TRUE_POINT_1 - (HEIGHT_CALIB_A * HEIGHT_RAW_POINT_1)

# =========================
# DETEKSI HSV KARDUS
# =========================
LOWER_BROWN = np.array([5, 25, 25])
UPPER_BROWN = np.array([35, 255, 255])

# =========================
# DETEKSI BACKGROUND FALLBACK
# =========================
DIFF_THRESHOLD = 26

# =========================
# FILTER CONTOUR
# =========================
MIN_CONTOUR_AREA = 3000
MAX_ASPECT_RATIO = 6.0

HSV_KERNEL_SIZE = 5
BG_KERNEL_SIZE = 7

BACKGROUND_SAMPLE_COUNT = 20

# Area pencarian sekitar titik sensor.
# Ini mencegah rangka luar ikut menjadi contour.
SEARCH_HALF_W_PX = 430
SEARCH_HALF_H_PX = 340

SENSOR_CONTOUR_TOLERANCE_PX = 60

# =========================
# STABILISASI
# =========================
STABLE_FRAME_TARGET = 4
STABILITY_TOLERANCE_PL_CM = 0.75
STABILITY_TOLERANCE_T_CM = 0.50

# =========================
# RUMUS IATA
# =========================
IATA_DIVISOR = 6000.0


# =====================================================
# UTIL CAMERA
# =====================================================

def sort_video_device(path):
    match = re.search(r"video(\d+)", path)
    return int(match.group(1)) if match else 999


def open_camera():
    devices = sorted(glob.glob("/dev/video*"), key=sort_video_device)

    print("Mencari kamera...")
    print("Device yang dicek:", devices)

    for dev in devices:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        time.sleep(0.3)

        ret, frame = cap.read()

        if ret and frame is not None:
            h, w = frame.shape[:2]
            print(f"Kamera berhasil dibuka: {dev}")
            print(f"Resolusi aktual: {w} x {h}")
            return cap, dev, w, h

        cap.release()

    return None, None, None, None


def load_calibration(frame_w, frame_h):
    if not os.path.exists(CALIB_FILE):
        raise FileNotFoundError(f"{CALIB_FILE} tidak ditemukan.")

    data = np.load(CALIB_FILE)

    camera_matrix = data["camera_matrix"]
    dist_coeffs = data["dist_coeffs"]

    new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (frame_w, frame_h),
        1,
        (frame_w, frame_h)
    )

    return camera_matrix, dist_coeffs, new_camera_matrix


def load_points():
    if not os.path.exists(POINTS_FILE):
        raise FileNotFoundError(f"{POINTS_FILE} tidak ditemukan.")

    with open(POINTS_FILE, "r") as f:
        points = json.load(f)

    if len(points) != 4:
        raise ValueError("File points harus berisi 4 titik.")

    return np.array(points, dtype=np.float32)


def load_scale():
    if not os.path.exists(SCALE_FILE):
        raise FileNotFoundError(f"{SCALE_FILE} tidak ditemukan.")

    with open(SCALE_FILE, "r") as f:
        return json.load(f)


def undistort_frame(frame, camera_matrix, dist_coeffs, new_camera_matrix):
    return cv2.undistort(
        frame,
        camera_matrix,
        dist_coeffs,
        None,
        new_camera_matrix
    )


def warp_workspace_margin(undistorted, points, scale):
    output_w = int(scale["output_width_px"])
    output_h = int(scale["output_height_px"])

    workspace_x0 = int(scale["workspace_x0"])
    workspace_y0 = int(scale["workspace_y0"])
    workspace_x1 = int(scale["workspace_x1"])
    workspace_y1 = int(scale["workspace_y1"])

    dst = np.array([
        [workspace_x0, workspace_y0],
        [workspace_x1, workspace_y0],
        [workspace_x1, workspace_y1],
        [workspace_x0, workspace_y1]
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(points, dst)

    warped = cv2.warpPerspective(
        undistorted,
        matrix,
        (output_w, output_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    return warped


def get_workspace_box(scale):
    x0 = int(scale["workspace_x0"])
    y0 = int(scale["workspace_y0"])
    x1 = int(scale["workspace_x1"])
    y1 = int(scale["workspace_y1"])
    return x0, y0, x1, y1


def get_default_sensor_point(scale):
    x0, y0, x1, y1 = get_workspace_box(scale)
    return int((x0 + x1) / 2), int((y0 + y1) / 2)


def capture_live_background(cap, camera_matrix, dist_coeffs, new_camera_matrix, points, scale):
    print("")
    print("=====================================================")
    print("KALIBRASI BACKGROUND KOSONG")
    print("=====================================================")
    print("Kosongkan area kerja dari semua benda.")
    print("Jangan ada tangan, kardus, kabel, atau benda lain.")
    print("Setelah area kerja kosong, tekan ENTER.")
    print("=====================================================")
    input()

    print("Mengambil background kosong dari kamera live...")

    frames = []

    for _ in range(10):
        cap.read()
        time.sleep(0.03)

    for i in range(BACKGROUND_SAMPLE_COUNT):
        ret, frame = cap.read()

        if not ret or frame is None:
            continue

        undistorted = undistort_frame(
            frame,
            camera_matrix,
            dist_coeffs,
            new_camera_matrix
        )

        warped = warp_workspace_margin(
            undistorted,
            points,
            scale
        )

        frames.append(warped)
        print(f"Background sample {i + 1}/{BACKGROUND_SAMPLE_COUNT}")
        time.sleep(0.03)

    if len(frames) < 5:
        raise RuntimeError("Gagal mengambil background kosong.")

    background = np.median(np.stack(frames, axis=0), axis=0).astype(np.uint8)

    cv2.imwrite(LIVE_BACKGROUND_PATH, background)

    print(f"Background live disimpan: {LIVE_BACKGROUND_PATH}")
    print("")

    return background


# =====================================================
# SENSOR POINT
# =====================================================

def load_sensor_point():
    if not os.path.exists(SENSOR_POINT_FILE):
        return None

    with open(SENSOR_POINT_FILE, "r") as f:
        data = json.load(f)

    return int(data["x"]), int(data["y"])


def save_sensor_point(point):
    x, y = point

    data = {
        "x": int(x),
        "y": int(y),
        "note": "Titik jatuh sensor ultrasonik pada gambar warp."
    }

    with open(SENSOR_POINT_FILE, "w") as f:
        json.dump(data, f, indent=4)


def calibrate_sensor_point(background, scale):
    existing = load_sensor_point()

    if existing is not None:
        print("")
        print("File titik sensor ditemukan:")
        print(f"x={existing[0]}, y={existing[1]}")
        print("Pilih:")
        print("1 = pakai titik lama")
        print("2 = klik ulang titik sensor")
        choice = input("Masukkan pilihan [1/2]: ").strip()

        if choice != "2":
            return existing

    point = list(get_default_sensor_point(scale))
    clicked = {"point": point}

    window_name = "Kalibrasi Titik Sensor Ultrasonik"

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicked["point"] = [x, y]

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 672)
    cv2.setMouseCallback(window_name, mouse_callback)

    print("")
    print("=====================================================")
    print("KALIBRASI TITIK SENSOR ULTRASONIK")
    print("=====================================================")
    print("Klik titik pada gambar yang sesuai dengan posisi jatuh sensor ultrasonik.")
    print("Tekan S untuk simpan.")
    print("Tekan C untuk kembali ke tengah area kerja.")
    print("Tekan Q untuk batal dan pakai tengah.")
    print("=====================================================")

    while True:
        preview = background.copy()

        draw_workspace_box(preview, scale)

        x, y = clicked["point"]

        cv2.drawMarker(
            preview,
            (int(x), int(y)),
            (0, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=2
        )

        cv2.putText(
            preview,
            "Klik titik sensor ultrasonik lalu tekan S",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        cv2.imshow(window_name, preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            final_point = (int(clicked["point"][0]), int(clicked["point"][1]))
            save_sensor_point(final_point)
            cv2.destroyWindow(window_name)
            print(f"Titik sensor disimpan: x={final_point[0]}, y={final_point[1]}")
            return final_point

        if key == ord("c"):
            clicked["point"] = list(get_default_sensor_point(scale))

        if key == ord("q"):
            final_point = get_default_sensor_point(scale)
            save_sensor_point(final_point)
            cv2.destroyWindow(window_name)
            print(f"Pakai titik tengah: x={final_point[0]}, y={final_point[1]}")
            return final_point


# =====================================================
# UTIL ULTRASONIK
# =====================================================

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)

    GPIO.output(TRIG, False)
    time.sleep(0.5)


def cleanup_gpio():
    GPIO.cleanup()


def load_ultrasonic_base_distance():
    if not os.path.exists(ULTRASONIC_CALIB_FILE):
        raise FileNotFoundError(
            f"{ULTRASONIC_CALIB_FILE} tidak ditemukan. Jalankan Tahap 9 dulu."
        )

    with open(ULTRASONIC_CALIB_FILE, "r") as f:
        data = json.load(f)

    return float(data["base_distance_cm"])


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


def read_distance_filtered(sample_count=ULTRASONIC_SAMPLE_COUNT):
    samples = []

    for _ in range(sample_count):
        distance = read_distance_once()

        if distance is not None:
            samples.append(distance)

        time.sleep(0.015)

    if len(samples) == 0:
        return None, [], []

    filtered = remove_outliers(samples)
    distance_cm = statistics.median(filtered)

    return distance_cm, samples, filtered


def calculate_height_raw(base_distance_cm, distance_cm):
    height_cm = base_distance_cm - distance_cm

    if height_cm <= HEIGHT_DEADBAND_CM:
        return 0.0

    if height_cm < 0:
        return 0.0

    return height_cm


def calibrate_height(height_raw_cm):
    if height_raw_cm <= MIN_VALID_OBJECT_HEIGHT_CM:
        return 0.0

    if not ENABLE_HEIGHT_CALIBRATION:
        return height_raw_cm

    height_calibrated = (HEIGHT_CALIB_A * height_raw_cm) + HEIGHT_CALIB_B

    if height_calibrated < 0:
        height_calibrated = 0.0

    return height_calibrated


def read_height_ultrasonic(base_distance_cm):
    distance_cm, raw_samples, filtered_samples = read_distance_filtered()

    if distance_cm is None:
        return None

    height_raw_cm = calculate_height_raw(base_distance_cm, distance_cm)
    height_cm = calibrate_height(height_raw_cm)

    return {
        "base_distance_cm": float(base_distance_cm),
        "distance_cm": float(distance_cm),
        "height_raw_cm": float(height_raw_cm),
        "height_cm": float(height_cm),
        "height_calib_enabled": ENABLE_HEIGHT_CALIBRATION,
        "height_calib_a": float(HEIGHT_CALIB_A),
        "height_calib_b": float(HEIGHT_CALIB_B),
        "raw_samples": raw_samples,
        "filtered_samples": filtered_samples,
        "sample_count_raw": len(raw_samples),
        "sample_count_filtered": len(filtered_samples)
    }


# =====================================================
# DETEKSI OBJEK
# =====================================================

def create_search_roi_mask(shape, scale, sensor_point):
    h, w = shape[:2]

    sx, sy = sensor_point

    x0 = max(0, sx - SEARCH_HALF_W_PX)
    y0 = max(0, sy - SEARCH_HALF_H_PX)
    x1 = min(w - 1, sx + SEARCH_HALF_W_PX)
    y1 = min(h - 1, sy + SEARCH_HALF_H_PX)

    # Jangan izinkan area terlalu ekstrem di luar frame.
    x0 = max(10, x0)
    y0 = max(10, y0)
    x1 = min(w - 10, x1)
    y1 = min(h - 10, y1)

    roi_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(roi_mask, (x0, y0), (x1, y1), 255, -1)

    return roi_mask


def contour_center(cnt):
    m = cv2.moments(cnt)

    if m["m00"] == 0:
        x, y, w, h = cv2.boundingRect(cnt)
        return x + w / 2, y + h / 2

    cx = m["m10"] / m["m00"]
    cy = m["m01"] / m["m00"]

    return cx, cy


def is_valid_contour(cnt, sensor_point):
    area = cv2.contourArea(cnt)

    if area < MIN_CONTOUR_AREA:
        return False

    x, y, w, h = cv2.boundingRect(cnt)

    if w < 45 or h < 45:
        return False

    ratio = max(w, h) / max(1, min(w, h))

    if ratio > MAX_ASPECT_RATIO:
        return False

    sx, sy = sensor_point

    sensor_test = cv2.pointPolygonTest(
        cnt,
        (float(sx), float(sy)),
        True
    )

    # Contour harus dekat atau melewati titik sensor.
    if sensor_test < -SENSOR_CONTOUR_TOLERANCE_PX:
        return False

    return True


def choose_best_contour(contours, sensor_point):
    valid = []

    sx, sy = sensor_point

    for cnt in contours:
        if not is_valid_contour(cnt, sensor_point):
            continue

        area = cv2.contourArea(cnt)
        cx, cy = contour_center(cnt)
        dist = ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5

        valid.append({
            "cnt": cnt,
            "area": area,
            "dist": dist
        })

    if len(valid) == 0:
        return None

    best = max(valid, key=lambda v: v["area"] - (v["dist"] * 6))

    return best["cnt"]


def detect_by_hsv_cardboard(warped, scale, sensor_point):
    roi_mask = create_search_roi_mask(warped.shape, scale, sensor_point)

    hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)

    mask = cv2.inRange(hsv, LOWER_BROWN, UPPER_BROWN)
    mask = cv2.bitwise_and(mask, roi_mask)

    kernel = np.ones((HSV_KERNEL_SIZE, HSV_KERNEL_SIZE), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    selected = choose_best_contour(contours, sensor_point)

    selected_mask = np.zeros_like(mask)

    if selected is not None:
        cv2.drawContours(selected_mask, [selected], -1, 255, -1)

    return selected, selected_mask


def detect_by_background(warped, background, scale, sensor_point):
    if background.shape[:2] != warped.shape[:2]:
        background = cv2.resize(background, (warped.shape[1], warped.shape[0]))

    roi_mask = create_search_roi_mask(warped.shape, scale, sensor_point)

    diff = cv2.absdiff(warped, background)

    diff_max = np.max(diff, axis=2).astype(np.uint8)
    diff_blur = cv2.GaussianBlur(diff_max, (5, 5), 0)

    _, mask = cv2.threshold(
        diff_blur,
        DIFF_THRESHOLD,
        255,
        cv2.THRESH_BINARY
    )

    mask = cv2.bitwise_and(mask, roi_mask)

    kernel = np.ones((BG_KERNEL_SIZE, BG_KERNEL_SIZE), np.uint8)

    # Jangan pakai dilate berlebihan. Ini yang sebelumnya bikin garis melebar.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    selected = choose_best_contour(contours, sensor_point)

    selected_mask = np.zeros_like(mask)

    if selected is not None:
        cv2.drawContours(selected_mask, [selected], -1, 255, -1)

    return selected, selected_mask


def detect_object_hybrid(warped, background, scale, sensor_point):
    # Prioritas 1: HSV kardus/cokelat.
    contour, mask = detect_by_hsv_cardboard(warped, scale, sensor_point)

    if contour is not None:
        return contour, mask, "hsv_cardboard"

    # Prioritas 2: background subtraction untuk objek warna lain.
    contour, mask = detect_by_background(warped, background, scale, sensor_point)

    if contour is not None:
        return contour, mask, "background_subtraction"

    empty = np.zeros(warped.shape[:2], dtype=np.uint8)
    return None, empty, "not_detected"


def measure_contour(cnt, px_per_cm_x, px_per_cm_y):
    rect = cv2.minAreaRect(cnt)
    box = cv2.boxPoints(rect)
    box = np.intp(box)

    (cx, cy), (w_px, h_px), angle = rect

    panjang_px = max(w_px, h_px)
    lebar_px = min(w_px, h_px)

    panjang_raw_cm = panjang_px / px_per_cm_x
    lebar_raw_cm = lebar_px / px_per_cm_y

    return {
        "box": box,
        "center_x": cx,
        "center_y": cy,
        "w_px": w_px,
        "h_px": h_px,
        "angle": angle,
        "panjang_px": panjang_px,
        "lebar_px": lebar_px,
        "panjang_raw_cm": panjang_raw_cm,
        "lebar_raw_cm": lebar_raw_cm
    }


def apply_height_correction(panjang_raw_cm, lebar_raw_cm, height_cm, base_distance_cm):
    if base_distance_cm <= 0:
        factor = 1.0
    else:
        factor = (base_distance_cm - height_cm) / base_distance_cm

    if factor <= 0:
        factor = 1.0

    panjang_cm = panjang_raw_cm * factor
    lebar_cm = lebar_raw_cm * factor

    return panjang_cm, lebar_cm, factor


def calc_error(measured, actual):
    if actual == 0:
        return 0.0

    return abs(measured - actual) / actual * 100


def calculate_volume_and_volumetric_weight(p_cm, l_cm, t_cm):
    volume_cm3 = p_cm * l_cm * t_cm
    berat_volumetrik_kg = volume_cm3 / IATA_DIVISOR
    berat_volumetrik_g = berat_volumetrik_kg * 1000.0

    return volume_cm3, berat_volumetrik_kg, berat_volumetrik_g


# =====================================================
# STABILISASI
# =====================================================

def is_measurement_stable(buffer):
    if len(buffer) < STABLE_FRAME_TARGET:
        return False

    p_values = [item["panjang_cm"] for item in buffer]
    l_values = [item["lebar_cm"] for item in buffer]
    t_values = [item["tinggi_cm"] for item in buffer]

    p_range = max(p_values) - min(p_values)
    l_range = max(l_values) - min(l_values)
    t_range = max(t_values) - min(t_values)

    return (
        p_range <= STABILITY_TOLERANCE_PL_CM and
        l_range <= STABILITY_TOLERANCE_PL_CM and
        t_range <= STABILITY_TOLERANCE_T_CM
    )


def average_measurements(buffer):
    keys = [
        "panjang_raw_cm",
        "lebar_raw_cm",
        "panjang_cm",
        "lebar_cm",
        "tinggi_raw_cm",
        "tinggi_cm",
        "volume_cm3",
        "berat_volumetrik_kg",
        "berat_volumetrik_g",
        "panjang_px",
        "lebar_px",
        "angle",
        "height_correction_factor",
        "error_persen_panjang",
        "error_persen_lebar",
        "error_persen_tinggi",
        "distance_cm"
    ]

    avg = {}

    for key in keys:
        avg[key] = float(np.mean([item[key] for item in buffer]))

    return avg


# =====================================================
# SIMPAN DATA
# =====================================================

def append_csv_log(csv_path, result):
    fieldnames = [
        "measurement_id",
        "timestamp",
        "object_detected",
        "metode_deteksi",

        "panjang_cm",
        "lebar_cm",
        "tinggi_cm",
        "tinggi_raw_cm",

        "volume_cm3",
        "berat_volumetrik_kg",
        "berat_volumetrik_g",

        "panjang_raw_cm",
        "lebar_raw_cm",
        "height_correction_factor",

        "actual_panjang_cm",
        "actual_lebar_cm",
        "actual_tinggi_cm",

        "error_persen_panjang",
        "error_persen_lebar",
        "error_persen_tinggi",

        "base_distance_cm",
        "distance_cm",

        "px_per_cm_x",
        "px_per_cm_y",

        "panjang_px",
        "lebar_px",
        "angle",

        "height_calib_enabled",
        "height_calib_a",
        "height_calib_b",

        "warp_output_width_px",
        "warp_output_height_px",
        "margin_px",

        "diff_threshold",
        "sensor_point_x",
        "sensor_point_y",

        "detection_image",
        "mask_image",
        "json_file"
    ]

    file_exists = os.path.exists(csv_path)

    row = {key: result.get(key, "") for key in fieldnames}

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def append_jsonl_log(jsonl_path, result):
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(result) + "\n")


def save_measurement_files(annotated, mask, result):
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    measurement_id = f"measurement_{timestamp_file}"

    result["measurement_id"] = measurement_id

    latest_detection_path = os.path.join(OUTPUT_DIR, "latest_detection.jpg")
    latest_mask_path = os.path.join(OUTPUT_DIR, "latest_mask.jpg")
    latest_json_path = os.path.join(OUTPUT_DIR, "latest_measurement.json")

    archive_detection_path = os.path.join(
        ARCHIVE_DIR,
        f"detection_{timestamp_file}.jpg"
    )

    archive_mask_path = os.path.join(
        ARCHIVE_DIR,
        f"mask_{timestamp_file}.jpg"
    )

    archive_json_path = os.path.join(
        ARCHIVE_DIR,
        f"measurement_{timestamp_file}.json"
    )

    cv2.imwrite(latest_detection_path, annotated)
    cv2.imwrite(latest_mask_path, mask)

    cv2.imwrite(archive_detection_path, annotated)
    cv2.imwrite(archive_mask_path, mask)

    result["detection_image"] = archive_detection_path
    result["mask_image"] = archive_mask_path
    result["json_file"] = archive_json_path

    with open(latest_json_path, "w") as f:
        json.dump(result, f, indent=4)

    with open(archive_json_path, "w") as f:
        json.dump(result, f, indent=4)

    append_csv_log(LOG_CSV, result)
    append_jsonl_log(LOG_JSONL, result)


# =====================================================
# DRAWING
# =====================================================

def draw_text_box(img, text, x, y, text_color, bg_color=(255, 255, 255),
                  font_scale=0.80, thickness=2, padding=6):
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


def draw_measurement_panel(annotated, p_cm, l_cm, t_cm, bv_g):
    BLUE = (255, 0, 0)
    RED = (0, 0, 255)
    WHITE = (255, 255, 255)

    x = 20
    y = 38
    gap = 44

    draw_text_box(annotated, f"P = {p_cm:.2f} cm", x, y, BLUE, WHITE)
    draw_text_box(annotated, f"L = {l_cm:.2f} cm", x, y + gap, BLUE, WHITE)
    draw_text_box(annotated, f"T = {t_cm:.2f} cm", x, y + 2 * gap, BLUE, WHITE)
    draw_text_box(
        annotated,
        f"Berat Volumetrik = {bv_g:.2f} g",
        x,
        y + 3 * gap,
        RED,
        WHITE
    )


def draw_status(annotated, status_text, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.72
    thickness = 2
    padding = 8

    (tw, th), baseline = cv2.getTextSize(status_text, font, font_scale, thickness)

    x = 20
    y = annotated.shape[0] - 20

    x1 = x - padding
    y1 = y - th - padding
    x2 = x + tw + padding
    y2 = y + baseline + padding

    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 0), -1)
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 255, 255), 1)

    cv2.putText(
        annotated,
        status_text,
        (x, y),
        font,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA
    )


def draw_workspace_box(annotated, scale):
    x0, y0, x1, y1 = get_workspace_box(scale)

    cv2.rectangle(
        annotated,
        (x0, y0),
        (x1, y1),
        (255, 255, 0),
        2
    )


def draw_sensor_point(annotated, sensor_point):
    sx, sy = sensor_point

    cv2.drawMarker(
        annotated,
        (sx, sy),
        (0, 0, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=18,
        thickness=2
    )


# =====================================================
# MAIN
# =====================================================

def main():
    print("=====================================================")
    print("TAHAP 10 - KAMERA + ULTRASONIK")
    print("FINAL HYBRID STABIL")
    print("MODE: SIMPAN 1 KALI PER OBJEK")
    print("=====================================================")
    print("Pastikan tahap9_ultrasonic_height.py tidak sedang berjalan.")
    print("=====================================================")
    print("")

    cap = None

    try:
        setup_gpio()

        ultrasonic_base_cm = load_ultrasonic_base_distance()

        print(f"Base ultrasonik dari Tahap 9: {ultrasonic_base_cm:.3f} cm")
        print(f"Height calibration enabled: {ENABLE_HEIGHT_CALIBRATION}")
        print(f"Height calibration: A={HEIGHT_CALIB_A:.4f}, B={HEIGHT_CALIB_B:.4f}")

        cap, device, frame_w, frame_h = open_camera()

        if cap is None:
            print("ERROR: Kamera tidak bisa dibuka.")
            return

        camera_matrix, dist_coeffs, new_camera_matrix = load_calibration(frame_w, frame_h)
        points = load_points()
        scale = load_scale()

        output_w = int(scale["output_width_px"])
        output_h = int(scale["output_height_px"])

        px_per_cm_x = float(scale["px_per_cm_x"])
        px_per_cm_y = float(scale["px_per_cm_y"])

        print("")
        print("Konfigurasi:")
        print(f"Device kamera              : {device}")
        print(f"Warp output                : {output_w} x {output_h} px")
        print(f"Workspace                  : x={scale['workspace_x0']}..{scale['workspace_x1']}, y={scale['workspace_y0']}..{scale['workspace_y1']}")
        print(f"PX_PER_CM_X                : {px_per_cm_x}")
        print(f"PX_PER_CM_Y                : {px_per_cm_y}")
        print(f"Base ultrasonik            : {ultrasonic_base_cm:.3f} cm")
        print(f"Actual object              : {ACTUAL_P_CM} x {ACTUAL_L_CM} x {ACTUAL_T_CM} cm")
        print(f"DIFF_THRESHOLD             : {DIFF_THRESHOLD}")
        print("")

        background = capture_live_background(
            cap,
            camera_matrix,
            dist_coeffs,
            new_camera_matrix,
            points,
            scale
        )

        sensor_point = calibrate_sensor_point(background, scale)

        print("Instruksi:")
        print("1. Letakkan objek sehingga bagian atasnya tepat di bawah titik sensor merah.")
        print("2. Untuk kardus cokelat, sistem memakai HSV agar garis hijau tidak melebar.")
        print("3. Untuk objek warna lain, sistem fallback ke background subtraction.")
        print("4. Tunggu sampai status OBJEK TERSIMPAN.")
        print("5. Tekan Q untuk keluar.")
        print("=====================================================")
        print("")

        cv2.namedWindow("Tahap 10 - Kamera + Ultrasonik", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tahap 10 - Kamera + Ultrasonik", 800, 672)

        cv2.namedWindow("Tahap 10 - Mask Objek", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tahap 10 - Mask Objek", 800, 672)

        state = "WAITING_OBJECT"
        measurement_buffer = []
        saved_count = 0

        empty_mask = np.zeros((output_h, output_w), dtype=np.uint8)

        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("WARNING: Frame kamera gagal dibaca.")
                continue

            undistorted = undistort_frame(
                frame,
                camera_matrix,
                dist_coeffs,
                new_camera_matrix
            )

            warped = warp_workspace_margin(
                undistorted,
                points,
                scale
            )

            annotated = warped.copy()
            draw_workspace_box(annotated, scale)
            draw_sensor_point(annotated, sensor_point)

            height_data = read_height_ultrasonic(ultrasonic_base_cm)

            if height_data is None:
                draw_status(
                    annotated,
                    "Status: ULTRASONIK GAGAL MEMBACA",
                    (0, 0, 255)
                )

                cv2.imshow("Tahap 10 - Kamera + Ultrasonik", annotated)
                cv2.imshow("Tahap 10 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break

                continue

            tinggi_raw_cm = float(height_data["height_raw_cm"])
            tinggi_cm = float(height_data["height_cm"])

            if tinggi_cm <= MIN_VALID_OBJECT_HEIGHT_CM:
                measurement_buffer = []
                state = "WAITING_OBJECT"

                draw_status(
                    annotated,
                    "Status: SIAP OBJEK BARU",
                    (0, 255, 255)
                )

                draw_text_box(
                    annotated,
                    "T = 0.00 cm",
                    20,
                    38,
                    (255, 0, 0),
                    (255, 255, 255)
                )

                cv2.imshow("Tahap 10 - Kamera + Ultrasonik", annotated)
                cv2.imshow("Tahap 10 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("Keluar dari Tahap 10.")
                    break

                continue

            contour, mask, detection_mode = detect_object_hybrid(
                warped,
                background,
                scale,
                sensor_point
            )

            if contour is None:
                measurement_buffer = []
                state = "WAITING_OBJECT"

                draw_status(
                    annotated,
                    "Status: OBJEK HARUS MENUTUP TITIK SENSOR MERAH",
                    (0, 0, 255)
                )

                draw_text_box(
                    annotated,
                    f"T = {tinggi_cm:.2f} cm",
                    20,
                    38,
                    (255, 0, 0),
                    (255, 255, 255)
                )

                cv2.imshow("Tahap 10 - Kamera + Ultrasonik", annotated)
                cv2.imshow("Tahap 10 - Mask Objek", empty_mask)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("Keluar dari Tahap 10.")
                    break

                continue

            measurement = measure_contour(
                contour,
                px_per_cm_x,
                px_per_cm_y
            )

            panjang_raw_cm = measurement["panjang_raw_cm"]
            lebar_raw_cm = measurement["lebar_raw_cm"]

            panjang_cm, lebar_cm, factor = apply_height_correction(
                panjang_raw_cm,
                lebar_raw_cm,
                tinggi_cm,
                ultrasonic_base_cm
            )

            volume_cm3, berat_volumetrik_kg, berat_volumetrik_g = calculate_volume_and_volumetric_weight(
                panjang_cm,
                lebar_cm,
                tinggi_cm
            )

            error_p = calc_error(panjang_cm, ACTUAL_P_CM)
            error_l = calc_error(lebar_cm, ACTUAL_L_CM)
            error_t = calc_error(tinggi_cm, ACTUAL_T_CM)

            current_data = {
                "panjang_raw_cm": float(panjang_raw_cm),
                "lebar_raw_cm": float(lebar_raw_cm),

                "panjang_cm": float(panjang_cm),
                "lebar_cm": float(lebar_cm),

                "tinggi_raw_cm": float(tinggi_raw_cm),
                "tinggi_cm": float(tinggi_cm),

                "volume_cm3": float(volume_cm3),
                "berat_volumetrik_kg": float(berat_volumetrik_kg),
                "berat_volumetrik_g": float(berat_volumetrik_g),

                "panjang_px": float(measurement["panjang_px"]),
                "lebar_px": float(measurement["lebar_px"]),
                "angle": float(measurement["angle"]),

                "height_correction_factor": float(factor),

                "error_persen_panjang": float(error_p),
                "error_persen_lebar": float(error_l),
                "error_persen_tinggi": float(error_t),

                "distance_cm": float(height_data["distance_cm"])
            }

            cv2.drawContours(annotated, [measurement["box"]], 0, (0, 255, 0), 2)

            draw_measurement_panel(
                annotated,
                panjang_cm,
                lebar_cm,
                tinggi_cm,
                berat_volumetrik_g
            )

            if state == "WAITING_OBJECT":
                state = "MEASURING"
                measurement_buffer = []
                print(f"Objek terdeteksi. Mode deteksi: {detection_mode}. Mulai stabilisasi P, L, T...")

            if state == "MEASURING":
                measurement_buffer.append(current_data)

                if len(measurement_buffer) > STABLE_FRAME_TARGET:
                    measurement_buffer.pop(0)

                draw_status(
                    annotated,
                    f"Status: MENGUKUR... {len(measurement_buffer)}/{STABLE_FRAME_TARGET}",
                    (0, 255, 255)
                )

                if is_measurement_stable(measurement_buffer):
                    avg = average_measurements(measurement_buffer)

                    result = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "object_detected": True,
                        "metode_deteksi": detection_mode,

                        "panjang_cm": round(avg["panjang_cm"], 3),
                        "lebar_cm": round(avg["lebar_cm"], 3),

                        "tinggi_raw_cm": round(avg["tinggi_raw_cm"], 3),
                        "tinggi_cm": round(avg["tinggi_cm"], 3),

                        "volume_cm3": round(avg["volume_cm3"], 3),
                        "berat_volumetrik_kg": round(avg["berat_volumetrik_kg"], 6),
                        "berat_volumetrik_g": round(avg["berat_volumetrik_g"], 3),

                        "panjang_raw_cm": round(avg["panjang_raw_cm"], 3),
                        "lebar_raw_cm": round(avg["lebar_raw_cm"], 3),

                        "height_correction_factor": round(avg["height_correction_factor"], 6),

                        "actual_panjang_cm": ACTUAL_P_CM,
                        "actual_lebar_cm": ACTUAL_L_CM,
                        "actual_tinggi_cm": ACTUAL_T_CM,

                        "error_persen_panjang": round(avg["error_persen_panjang"], 3),
                        "error_persen_lebar": round(avg["error_persen_lebar"], 3),
                        "error_persen_tinggi": round(avg["error_persen_tinggi"], 3),

                        "base_distance_cm": round(float(height_data["base_distance_cm"]), 3),
                        "distance_cm": round(avg["distance_cm"], 3),

                        "px_per_cm_x": px_per_cm_x,
                        "px_per_cm_y": px_per_cm_y,

                        "panjang_px": round(avg["panjang_px"], 3),
                        "lebar_px": round(avg["lebar_px"], 3),
                        "angle": round(avg["angle"], 3),

                        "height_calib_enabled": ENABLE_HEIGHT_CALIBRATION,
                        "height_calib_a": round(HEIGHT_CALIB_A, 6),
                        "height_calib_b": round(HEIGHT_CALIB_B, 6),

                        "sensor_point_x": int(sensor_point[0]),
                        "sensor_point_y": int(sensor_point[1]),

                        "warp_output_width_px": output_w,
                        "warp_output_height_px": output_h,
                        "margin_px": int(scale["margin_px"]),

                        "diff_threshold": DIFF_THRESHOLD,

                        "rumus_berat_volumetrik": "P x L x T / 6000 kg atau P x L x T / 6 gram"
                    }

                    save_measurement_files(annotated, mask, result)

                    saved_count += 1
                    state = "OBJECT_SAVED_WAIT_REMOVAL"

                    print("")
                    print("=====================================================")
                    print(f"OBJEK TERSIMPAN #{saved_count}")
                    print(f"Mode deteksi = {detection_mode}")
                    print(f"P = {result['panjang_cm']} cm")
                    print(f"L = {result['lebar_cm']} cm")
                    print(f"T = {result['tinggi_cm']} cm")
                    print(f"T raw = {result['tinggi_raw_cm']} cm")
                    print(f"Volume = {result['volume_cm3']} cm3")
                    print(f"Berat Volumetrik = {result['berat_volumetrik_g']} g")
                    print(f"Err P = {result['error_persen_panjang']}%")
                    print(f"Err L = {result['error_persen_lebar']}%")
                    print(f"Err T = {result['error_persen_tinggi']}%")
                    print("Silakan ambil objek dari area kerja.")
                    print("=====================================================")
                    print("")

            elif state == "OBJECT_SAVED_WAIT_REMOVAL":
                draw_status(
                    annotated,
                    "Status: OBJEK SUDAH TERSIMPAN - AMBIL OBJEK",
                    (0, 255, 0)
                )

            cv2.imshow("Tahap 10 - Kamera + Ultrasonik", annotated)
            cv2.imshow("Tahap 10 - Mask Objek", mask)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("Keluar dari Tahap 10.")
                break

    except KeyboardInterrupt:
        print("")
        print("Program dihentikan oleh user.")

    except Exception as e:
        print("ERROR:", e)

    finally:
        if cap is not None:
            cap.release()

        cv2.destroyAllWindows()
        cleanup_gpio()
        print("GPIO cleanup selesai.")


if __name__ == "__main__":
    main()