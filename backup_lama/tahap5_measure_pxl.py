import cv2
import numpy as np
import RPi.GPIO as GPIO
import time
import json
import os
import glob
import statistics
import re
from datetime import datetime

# =====================================================
# TAHAP 5 FINAL - OTOMATIS P x L x T + IATA
# Revisi: HSV cokelat + deteksi objek terang + ROI area kerja
# =====================================================

# -----------------------------
# KONFIGURASI AREA KERJA
# -----------------------------
WORKSPACE_P_CM = 19.0
WORKSPACE_L_CM = 15.0

# Output warp proporsional dengan area kerja 19 x 15 cm
# 608 / 19 = 32 px/cm
# 480 / 15 = 32 px/cm
WARP_WIDTH = 608
WARP_HEIGHT = 480

PX_PER_CM_X = WARP_WIDTH / WORKSPACE_P_CM
PX_PER_CM_Y = WARP_HEIGHT / WORKSPACE_L_CM

# Jarak kamera ke alas area kerja
CAMERA_TO_AREA_CM = 32.0

# -----------------------------
# KONFIGURASI ULTRASONIK
# -----------------------------
TRIG = 23
ECHO = 24

ULTRASONIC_TO_AREA_CM = 31.5

# Kalibrasi tinggi.
# Jika tinggi asli 15.5 cm tetapi terbaca 14.5 cm, berarti kurang 1 cm.
HEIGHT_OFFSET_CM = 1.0

# -----------------------------
# KONFIGURASI KAMERA
# -----------------------------
# Biarkan None agar program mencari kamera otomatis.
# Kalau ingin paksa device tertentu, isi contoh:
# CAMERA_DEVICE = "/dev/video23"
CAMERA_DEVICE = None

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30

# Resolusi saat titik 4 sudut dibuat pada Tahap 3
POINTS_SOURCE_WIDTH = 1920
POINTS_SOURCE_HEIGHT = 1080

# -----------------------------
# PATH FILE
# -----------------------------
POINTS_PATH = "hasil_tahap2/points_4_corners.json"
OUTPUT_DIR = "hasil_tahap5"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------
# DETEKSI WARNA DAN OBJEK
# -----------------------------
# HSV cokelat kardus, dibuat lebih longgar
LOWER_BROWN = np.array([5, 25, 35])
UPPER_BROWN = np.array([40, 255, 255])

# Threshold grayscale untuk objek yang lebih terang dari alas hitam
BRIGHT_THRESHOLD = 45

# Area minimal contour agar noise kecil tidak dihitung sebagai objek
MIN_CONTOUR_AREA = 1200

# Margin untuk mengabaikan lakban / border putih
ROI_MARGIN_X = 55
ROI_MARGIN_Y = 45

# -----------------------------
# STABILISASI OBJEK
# -----------------------------
STABLE_REQUIRED_FRAMES = 15
CENTER_TOLERANCE_PX = 8
SIZE_TOLERANCE_PX = 10
REMOVE_REQUIRED_FRAMES = 15


# =====================================================
# FUNGSI KAMERA
# =====================================================

def sort_video_device(path):
    match = re.search(r"video(\d+)", path)
    return int(match.group(1)) if match else 999


def open_camera():
    if CAMERA_DEVICE is not None:
        devices = [CAMERA_DEVICE]
    else:
        devices = sorted(glob.glob("/dev/video*"), key=sort_video_device)

    print("Mencari kamera...")
    print("Device yang dicek:", devices)

    for dev in devices:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)

        time.sleep(0.2)

        ret, frame = cap.read()

        if ret and frame is not None:
            h, w = frame.shape[:2]
            print(f"Kamera berhasil dibuka: {dev}")
            print(f"Resolusi aktual: {w} x {h}")
            return cap, dev, w, h

        cap.release()

    return None, None, None, None


# =====================================================
# FUNGSI ULTRASONIK
# =====================================================

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)
    GPIO.output(TRIG, False)
    time.sleep(0.5)


def read_distance_once(timeout=0.04):
    GPIO.output(TRIG, False)
    time.sleep(0.000002)

    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_wait = time.time()

    while GPIO.input(ECHO) == 0:
        if time.time() - start_wait > timeout:
            return None

    pulse_start = time.time()
    start_wait = time.time()

    while GPIO.input(ECHO) == 1:
        if time.time() - start_wait > timeout:
            return None

    pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance_cm = pulse_duration * 17150

    if distance_cm <= 0:
        return None

    return distance_cm


def read_height_cm(samples=15):
    distances = []

    for _ in range(samples):
        d = read_distance_once()

        if d is not None and 1.0 <= d <= ULTRASONIC_TO_AREA_CM + 5:
            distances.append(d)

        time.sleep(0.03)

    if len(distances) < 5:
        return None, None

    median_distance = statistics.median(distances)
    height_cm = ULTRASONIC_TO_AREA_CM - median_distance + HEIGHT_OFFSET_CM

    if height_cm < 0:
        height_cm = 0

    return round(height_cm, 2), round(median_distance, 2)


# =====================================================
# FUNGSI WARP AREA KERJA
# =====================================================

def load_points(frame_w, frame_h):
    if not os.path.exists(POINTS_PATH):
        print("ERROR: File points_4_corners.json tidak ditemukan.")
        print("Pastikan file ada di:", POINTS_PATH)
        return None

    with open(POINTS_PATH, "r") as f:
        pts = np.array(json.load(f), dtype=np.float32)

    scale_x = frame_w / POINTS_SOURCE_WIDTH
    scale_y = frame_h / POINTS_SOURCE_HEIGHT

    pts[:, 0] *= scale_x
    pts[:, 1] *= scale_y

    return pts


def get_warp_matrix(src_points):
    dst_points = np.array([
        [0, 0],
        [WARP_WIDTH - 1, 0],
        [WARP_WIDTH - 1, WARP_HEIGHT - 1],
        [0, WARP_HEIGHT - 1]
    ], dtype=np.float32)

    return cv2.getPerspectiveTransform(src_points, dst_points)


def warp_workspace(frame, matrix):
    return cv2.warpPerspective(frame, matrix, (WARP_WIDTH, WARP_HEIGHT))


# =====================================================
# FUNGSI DETEKSI OBJEK - REVISI HSV
# =====================================================

def detect_cardboard(warped):
    hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # 1. Mask warna cokelat kardus
    mask_brown = cv2.inRange(hsv, LOWER_BROWN, UPPER_BROWN)

    # 2. Mask objek terang di atas alas hitam
    _, mask_bright = cv2.threshold(
        gray,
        BRIGHT_THRESHOLD,
        255,
        cv2.THRESH_BINARY
    )

    # 3. Gabungkan deteksi warna cokelat dan deteksi objek terang
    mask = cv2.bitwise_or(mask_brown, mask_bright)

    # 4. Batasi deteksi hanya area tengah agar border/lakban putih tidak ikut
    roi_mask = np.zeros_like(mask)

    roi_mask[
        ROI_MARGIN_Y:WARP_HEIGHT - ROI_MARGIN_Y,
        ROI_MARGIN_X:WARP_WIDTH - ROI_MARGIN_X
    ] = 255

    mask = cv2.bitwise_and(mask, roi_mask)

    # 5. Bersihkan noise
    kernel = np.ones((7, 7), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 6. Cari contour
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    valid_contours = []

    for c in contours:
        area = cv2.contourArea(c)

        if area >= MIN_CONTOUR_AREA:
            valid_contours.append(c)

    if not valid_contours:
        return None, mask

    contour = max(valid_contours, key=cv2.contourArea)

    return contour, mask


def get_object_signature(contour):
    rect = cv2.minAreaRect(contour)
    (cx, cy), (w, h), angle = rect

    long_side = max(w, h)
    short_side = min(w, h)

    return {
        "cx": cx,
        "cy": cy,
        "long": long_side,
        "short": short_side,
        "rect": rect
    }


def is_stable(prev_sig, curr_sig):
    if prev_sig is None or curr_sig is None:
        return False

    dcx = abs(curr_sig["cx"] - prev_sig["cx"])
    dcy = abs(curr_sig["cy"] - prev_sig["cy"])
    dlong = abs(curr_sig["long"] - prev_sig["long"])
    dshort = abs(curr_sig["short"] - prev_sig["short"])

    return (
        dcx <= CENTER_TOLERANCE_PX and
        dcy <= CENTER_TOLERANCE_PX and
        dlong <= SIZE_TOLERANCE_PX and
        dshort <= SIZE_TOLERANCE_PX
    )


# =====================================================
# FUNGSI PENGUKURAN
# =====================================================

def measure_object(contour, height_cm):
    rect = cv2.minAreaRect(contour)
    (cx, cy), (w_px, h_px), angle = rect

    if w_px <= 0 or h_px <= 0:
        return None

    panjang_px = max(w_px, h_px)
    lebar_px = min(w_px, h_px)

    panjang_raw_cm = panjang_px / PX_PER_CM_X
    lebar_raw_cm = lebar_px / PX_PER_CM_Y

    # Koreksi skala karena objek tinggi lebih dekat ke kamera
    if height_cm is not None and CAMERA_TO_AREA_CM > height_cm:
        height_correction = (CAMERA_TO_AREA_CM - height_cm) / CAMERA_TO_AREA_CM
    else:
        height_correction = 1.0

    panjang_cm = panjang_raw_cm * height_correction
    lebar_cm = lebar_raw_cm * height_correction

    volume_cm3 = panjang_cm * lebar_cm * height_cm
    berat_volumetrik_iata_kg = volume_cm3 / 6000

    box = cv2.boxPoints(rect)
    box = np.int32(box)

    return {
        "panjang_px": round(float(panjang_px), 2),
        "lebar_px": round(float(lebar_px), 2),
        "panjang_cm": round(float(panjang_cm), 2),
        "lebar_cm": round(float(lebar_cm), 2),
        "tinggi_cm": round(float(height_cm), 2),
        "volume_cm3": round(float(volume_cm3), 2),
        "berat_volumetrik_iata_kg": round(float(berat_volumetrik_iata_kg), 3),
        "height_correction": round(float(height_correction), 4),
        "rumus_iata": "P x L x T / 6000",
        "box": box
    }


def draw_overlay(warped, contour, status, result=None):
    output = warped.copy()

    cv2.putText(
        output,
        f"Status: {status}",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2
    )

    if contour is not None:
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.int32(box)
        cv2.drawContours(output, [box], 0, (0, 255, 0), 2)

    if result is not None:
        cv2.putText(output, f"P = {result['panjang_cm']} cm", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        cv2.putText(output, f"L = {result['lebar_cm']} cm", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        cv2.putText(output, f"T = {result['tinggi_cm']} cm", (20, 135),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        cv2.putText(output, f"IATA = {result['berat_volumetrik_iata_kg']} kg", (20, 170),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

    return output


def save_measurement(result, warped, mask, contour):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    annotated = draw_overlay(warped, contour, "HASIL PENGUKURAN", result)

    annotated_path = os.path.join(OUTPUT_DIR, "latest_annotated.jpg")
    mask_path = os.path.join(OUTPUT_DIR, "latest_mask.jpg")
    json_path = os.path.join(OUTPUT_DIR, "measurement_results.json")

    cv2.imwrite(annotated_path, annotated)
    cv2.imwrite(mask_path, mask)

    history_json_path = os.path.join(OUTPUT_DIR, f"measurement_{timestamp}.json")
    history_img_path = os.path.join(OUTPUT_DIR, f"annotated_{timestamp}.jpg")

    cv2.imwrite(history_img_path, annotated)

    result_for_json = result.copy()
    result_for_json.pop("box", None)
    result_for_json["timestamp"] = timestamp

    with open(json_path, "w") as f:
        json.dump(result_for_json, f, indent=4)

    with open(history_json_path, "w") as f:
        json.dump(result_for_json, f, indent=4)

    print("")
    print("========== HASIL PENGUKURAN OTOMATIS ==========")
    print(f"Panjang              : {result['panjang_cm']} cm")
    print(f"Lebar                : {result['lebar_cm']} cm")
    print(f"Tinggi               : {result['tinggi_cm']} cm")
    print(f"Volume aktual        : {result['volume_cm3']} cm3")
    print(f"Berat volumetrik IATA: {result['berat_volumetrik_iata_kg']} kg")
    print(f"Rumus                : P x L x T / 6000")
    print(f"Koreksi tinggi PxL   : {result['height_correction']}")
    print(f"File JSON            : {json_path}")
    print(f"File gambar          : {annotated_path}")
    print("================================================")
    print("")


# =====================================================
# MAIN PROGRAM
# =====================================================

def main():
    setup_gpio()

    cap, device, frame_w, frame_h = open_camera()

    if cap is None:
        print("ERROR: Kamera tidak berhasil dibuka.")
        GPIO.cleanup()
        return

    src_points = load_points(frame_w, frame_h)

    if src_points is None:
        cap.release()
        GPIO.cleanup()
        return

    warp_matrix = get_warp_matrix(src_points)

    print("")
    print("Tahap 5 otomatis dimulai.")
    print("Letakkan objek kardus di area kerja.")
    print("Sistem akan mengukur otomatis jika objek stabil.")
    print("Tekan Q untuk keluar.")
    print("")

    stable_count = 0
    removed_count = 0
    prev_signature = None
    already_measured = False
    last_result = None

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("WARNING: Frame kamera tidak terbaca.")
                continue

            warped = warp_workspace(frame, warp_matrix)
            contour, mask = detect_cardboard(warped)

            # Simpan mask terbaru untuk debugging
            cv2.imwrite(os.path.join(OUTPUT_DIR, "latest_mask.jpg"), mask)

            status = "MENUNGGU OBJEK"

            if contour is None:
                stable_count = 0
                prev_signature = None

                if already_measured:
                    removed_count += 1
                    status = f"OBJEK SUDAH DIUKUR - AMBIL OBJEK ({removed_count}/{REMOVE_REQUIRED_FRAMES})"

                    if removed_count >= REMOVE_REQUIRED_FRAMES:
                        already_measured = False
                        last_result = None
                        removed_count = 0
                        print("Objek sudah keluar. Sistem siap mengukur objek berikutnya.")
                else:
                    status = "MENUNGGU OBJEK"

            else:
                removed_count = 0
                curr_signature = get_object_signature(contour)

                if already_measured:
                    status = "OBJEK SUDAH DIUKUR - SILAKAN AMBIL OBJEK"

                else:
                    if is_stable(prev_signature, curr_signature):
                        stable_count += 1
                    else:
                        stable_count = 0

                    prev_signature = curr_signature

                    status = f"MENUNGGU STABIL {stable_count}/{STABLE_REQUIRED_FRAMES}"

                    if stable_count >= STABLE_REQUIRED_FRAMES:
                        status = "MENGUKUR OTOMATIS"

                        height_cm, distance_cm = read_height_cm(samples=15)

                        if height_cm is None:
                            print("ERROR: Tinggi gagal dibaca dari ultrasonik.")
                            height_cm = 0

                        result = measure_object(contour, height_cm)

                        if result is not None:
                            result["jarak_sensor_ke_objek_cm"] = distance_cm
                            result["jarak_sensor_ke_area_cm"] = ULTRASONIC_TO_AREA_CM

                            save_measurement(result, warped, mask, contour)

                            last_result = result
                            already_measured = True

                        stable_count = 0

            display = draw_overlay(warped, contour, status, last_result)

            cv2.imshow("Tahap 5 - Otomatis PxL + T + IATA", display)
            cv2.imshow("Mask Deteksi Objek", mask)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("Program dihentikan.")
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        GPIO.cleanup()


if __name__ == "__main__":
    main()