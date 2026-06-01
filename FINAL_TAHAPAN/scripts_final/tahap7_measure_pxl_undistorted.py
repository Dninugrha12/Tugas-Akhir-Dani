import cv2
import numpy as np
import json
import os
import glob
import re
import time
import csv
from datetime import datetime

# =====================================================
# TAHAP 7 - DETEKSI OBJEK DAN UKUR P x L
# VERSI MARGIN
# =====================================================
# Input:
#   camera_calibration.npz
#   hasil_tahap4/points_4_corners_undistorted.json
#   hasil_tahap6/pixel_scale.json
#
# Output:
#   hasil_tahap7/latest_detection.jpg
#   hasil_tahap7/latest_mask.jpg
#   hasil_tahap7/latest_measurement.json
#   hasil_tahap7/measurements_log.csv
#   hasil_tahap7/measurements_log.jsonl
#   hasil_tahap7/archive/
# =====================================================

CALIB_FILE = "camera_calibration.npz"
POINTS_FILE = "hasil_tahap4/points_4_corners_undistorted.json"
SCALE_FILE = "hasil_tahap6/pixel_scale.json"

OUTPUT_DIR = "hasil_tahap7"
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

LOG_CSV = os.path.join(OUTPUT_DIR, "measurements_log.csv")
LOG_JSONL = os.path.join(OUTPUT_DIR, "measurements_log.jsonl")

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30

# Ukuran asli benda uji
ACTUAL_P_CM = 10.2
ACTUAL_L_CM = 10.2
ACTUAL_T_CM = 5.0

# Sementara masih manual. Nanti diganti ultrasonic.
OBJECT_HEIGHT_CM = 5.0

# Jarak kamera ke alas kerja
CAMERA_TO_AREA_CM = 31.5

# HSV kardus cokelat
LOWER_BROWN = np.array([5, 30, 35])
UPPER_BROWN = np.array([35, 255, 255])

MIN_CONTOUR_AREA = 800

# Deteksi stabil
STABLE_FRAME_TARGET = 10
STABILITY_TOLERANCE_CM = 0.35
REMOVE_CONFIRM_FRAMES = 12


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


def detect_cardboard(warped):
    hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)

    mask = cv2.inRange(hsv, LOWER_BROWN, UPPER_BROWN)

    kernel = np.ones((5, 5), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    valid_contours = []

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if area >= MIN_CONTOUR_AREA:
            valid_contours.append(cnt)

    if len(valid_contours) == 0:
        return None, mask

    largest = max(valid_contours, key=cv2.contourArea)

    return largest, mask


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


def apply_height_correction(panjang_raw_cm, lebar_raw_cm):
    if CAMERA_TO_AREA_CM <= 0:
        factor = 1.0
    else:
        factor = (CAMERA_TO_AREA_CM - OBJECT_HEIGHT_CM) / CAMERA_TO_AREA_CM

    panjang_corr_cm = panjang_raw_cm * factor
    lebar_corr_cm = lebar_raw_cm * factor

    return panjang_corr_cm, lebar_corr_cm, factor


def calc_error(measured, actual):
    if actual == 0:
        return 0.0

    return abs(measured - actual) / actual * 100


def is_measurement_stable(buffer):
    if len(buffer) < STABLE_FRAME_TARGET:
        return False

    p_values = [item["panjang_corr_cm"] for item in buffer]
    l_values = [item["lebar_corr_cm"] for item in buffer]

    p_range = max(p_values) - min(p_values)
    l_range = max(l_values) - min(l_values)

    return p_range <= STABILITY_TOLERANCE_CM and l_range <= STABILITY_TOLERANCE_CM


def average_measurements(buffer):
    keys = [
        "panjang_raw_cm",
        "lebar_raw_cm",
        "panjang_corr_cm",
        "lebar_corr_cm",
        "panjang_px",
        "lebar_px",
        "angle",
        "height_correction_factor",
        "error_raw_persen_panjang",
        "error_raw_persen_lebar",
        "error_corr_persen_panjang",
        "error_corr_persen_lebar"
    ]

    avg = {}

    for key in keys:
        avg[key] = float(np.mean([item[key] for item in buffer]))

    return avg


def append_csv_log(csv_path, result):
    fieldnames = [
        "measurement_id",
        "timestamp",
        "object_detected",

        "actual_panjang_cm",
        "actual_lebar_cm",
        "actual_tinggi_cm",

        "panjang_raw_cm",
        "lebar_raw_cm",

        "panjang_corr_cm",
        "lebar_corr_cm",

        "camera_to_area_cm",
        "object_height_cm",
        "height_correction_factor",

        "px_per_cm_x",
        "px_per_cm_y",

        "panjang_px",
        "lebar_px",
        "angle",

        "error_raw_persen_panjang",
        "error_raw_persen_lebar",
        "error_corr_persen_panjang",
        "error_corr_persen_lebar",

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


def draw_text_panel(annotated, lines):
    y = 30

    for text, color in lines:
        cv2.putText(
            annotated,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2
        )
        y += 30


def draw_status(annotated, status_text, color):
    cv2.putText(
        annotated,
        status_text,
        (20, annotated.shape[0] - 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2
    )


def draw_workspace_box(annotated, scale):
    x0 = int(scale["workspace_x0"])
    y0 = int(scale["workspace_y0"])
    x1 = int(scale["workspace_x1"])
    y1 = int(scale["workspace_y1"])

    cv2.rectangle(
        annotated,
        (x0, y0),
        (x1, y1),
        (255, 255, 0),
        2
    )


def main():
    print("=====================================================")
    print("TAHAP 7 - DETEKSI OBJEK DAN UKUR P x L VERSI MARGIN")
    print("MODE: SIMPAN 1 KALI PER OBJEK")
    print("=====================================================")
    print("")

    cap, device, frame_w, frame_h = open_camera()

    if cap is None:
        print("ERROR: Kamera tidak bisa dibuka.")
        return

    try:
        camera_matrix, dist_coeffs, new_camera_matrix = load_calibration(frame_w, frame_h)
        points = load_points()
        scale = load_scale()
    except Exception as e:
        print("ERROR:", e)
        cap.release()
        return

    output_w = int(scale["output_width_px"])
    output_h = int(scale["output_height_px"])

    px_per_cm_x = float(scale["px_per_cm_x"])
    px_per_cm_y = float(scale["px_per_cm_y"])

    print("Konfigurasi:")
    print(f"Device kamera      : {device}")
    print(f"Warp output        : {output_w} x {output_h} px")
    print(f"Workspace utama    : x={scale['workspace_x0']}..{scale['workspace_x1']}, y={scale['workspace_y0']}..{scale['workspace_y1']}")
    print(f"Margin             : {scale['margin_px']} px")
    print(f"PX_PER_CM_X        : {px_per_cm_x}")
    print(f"PX_PER_CM_Y        : {px_per_cm_y}")
    print(f"CAMERA_TO_AREA_CM  : {CAMERA_TO_AREA_CM}")
    print(f"OBJECT_HEIGHT_CM   : {OBJECT_HEIGHT_CM}")
    print("")
    print("Instruksi:")
    print("1. Letakkan objek.")
    print("2. Tunggu sampai status OBJEK TERSIMPAN.")
    print("3. Ambil objek.")
    print("4. Setelah status SIAP OBJEK BARU, letakkan objek berikutnya.")
    print("5. Tekan Q untuk keluar.")
    print("=====================================================")
    print("")

    cv2.namedWindow("Tahap 7 - Deteksi P x L Margin", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Tahap 7 - Deteksi P x L Margin", 800, 672)

    cv2.namedWindow("Tahap 7 - Mask Kardus", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Tahap 7 - Mask Kardus", 800, 672)

    state = "WAITING_OBJECT"
    measurement_buffer = []
    no_object_counter = 0
    saved_count = 0

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

        contour, mask = detect_cardboard(warped)

        annotated = warped.copy()
        draw_workspace_box(annotated, scale)

        if contour is not None:
            measurement = measure_contour(
                contour,
                px_per_cm_x,
                px_per_cm_y
            )

            panjang_raw_cm = measurement["panjang_raw_cm"]
            lebar_raw_cm = measurement["lebar_raw_cm"]

            panjang_corr_cm, lebar_corr_cm, factor = apply_height_correction(
                panjang_raw_cm,
                lebar_raw_cm
            )

            error_raw_p = calc_error(panjang_raw_cm, ACTUAL_P_CM)
            error_raw_l = calc_error(lebar_raw_cm, ACTUAL_L_CM)
            error_corr_p = calc_error(panjang_corr_cm, ACTUAL_P_CM)
            error_corr_l = calc_error(lebar_corr_cm, ACTUAL_L_CM)

            current_data = {
                "panjang_raw_cm": float(panjang_raw_cm),
                "lebar_raw_cm": float(lebar_raw_cm),
                "panjang_corr_cm": float(panjang_corr_cm),
                "lebar_corr_cm": float(lebar_corr_cm),
                "panjang_px": float(measurement["panjang_px"]),
                "lebar_px": float(measurement["lebar_px"]),
                "angle": float(measurement["angle"]),
                "height_correction_factor": float(factor),
                "error_raw_persen_panjang": float(error_raw_p),
                "error_raw_persen_lebar": float(error_raw_l),
                "error_corr_persen_panjang": float(error_corr_p),
                "error_corr_persen_lebar": float(error_corr_l)
            }

            cv2.drawContours(annotated, [measurement["box"]], 0, (0, 255, 0), 2)

            lines = [
                (f"P raw  = {panjang_raw_cm:.2f} cm", (0, 255, 255)),
                (f"L raw  = {lebar_raw_cm:.2f} cm", (0, 255, 255)),
                (f"P corr = {panjang_corr_cm:.2f} cm", (0, 255, 0)),
                (f"L corr = {lebar_corr_cm:.2f} cm", (0, 255, 0)),
                (f"Err P={error_corr_p:.2f}% L={error_corr_l:.2f}%", (0, 255, 255)),
            ]

            draw_text_panel(annotated, lines)

            no_object_counter = 0

            if state == "WAITING_OBJECT":
                state = "MEASURING"
                measurement_buffer = []
                print("Objek terdeteksi. Mulai stabilisasi...")

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

                        "actual_panjang_cm": ACTUAL_P_CM,
                        "actual_lebar_cm": ACTUAL_L_CM,
                        "actual_tinggi_cm": ACTUAL_T_CM,

                        "camera_to_area_cm": CAMERA_TO_AREA_CM,
                        "object_height_cm": OBJECT_HEIGHT_CM,

                        "px_per_cm_x": px_per_cm_x,
                        "px_per_cm_y": px_per_cm_y,

                        "warp_output_width_px": output_w,
                        "warp_output_height_px": output_h,

                        "workspace_x0": int(scale["workspace_x0"]),
                        "workspace_y0": int(scale["workspace_y0"]),
                        "workspace_x1": int(scale["workspace_x1"]),
                        "workspace_y1": int(scale["workspace_y1"]),
                        "margin_px": int(scale["margin_px"]),

                        "panjang_raw_cm": round(avg["panjang_raw_cm"], 3),
                        "lebar_raw_cm": round(avg["lebar_raw_cm"], 3),

                        "panjang_corr_cm": round(avg["panjang_corr_cm"], 3),
                        "lebar_corr_cm": round(avg["lebar_corr_cm"], 3),

                        "height_correction_factor": round(avg["height_correction_factor"], 6),

                        "panjang_px": round(avg["panjang_px"], 3),
                        "lebar_px": round(avg["lebar_px"], 3),
                        "angle": round(avg["angle"], 3),

                        "error_raw_persen_panjang": round(avg["error_raw_persen_panjang"], 3),
                        "error_raw_persen_lebar": round(avg["error_raw_persen_lebar"], 3),
                        "error_corr_persen_panjang": round(avg["error_corr_persen_panjang"], 3),
                        "error_corr_persen_lebar": round(avg["error_corr_persen_lebar"], 3)
                    }

                    save_measurement_files(annotated, mask, result)

                    saved_count += 1
                    state = "OBJECT_SAVED_WAIT_REMOVAL"

                    print("")
                    print("=====================================================")
                    print(f"OBJEK TERSIMPAN #{saved_count}")
                    print(f"P corr = {avg['panjang_corr_cm']:.2f} cm")
                    print(f"L corr = {avg['lebar_corr_cm']:.2f} cm")
                    print(f"Err P  = {avg['error_corr_persen_panjang']:.2f}%")
                    print(f"Err L  = {avg['error_corr_persen_lebar']:.2f}%")
                    print("Silakan ambil objek dari area kerja.")
                    print("=====================================================")
                    print("")

            elif state == "OBJECT_SAVED_WAIT_REMOVAL":
                draw_status(
                    annotated,
                    "Status: OBJEK SUDAH TERSIMPAN - AMBIL OBJEK",
                    (0, 255, 0)
                )

        else:
            if state == "OBJECT_SAVED_WAIT_REMOVAL":
                no_object_counter += 1

                draw_status(
                    annotated,
                    f"Status: MENUNGGU OBJEK KELUAR... {no_object_counter}/{REMOVE_CONFIRM_FRAMES}",
                    (0, 255, 255)
                )

                if no_object_counter >= REMOVE_CONFIRM_FRAMES:
                    state = "WAITING_OBJECT"
                    measurement_buffer = []
                    no_object_counter = 0
                    print("Objek sudah keluar. Sistem siap objek baru.")

            elif state == "MEASURING":
                measurement_buffer = []
                state = "WAITING_OBJECT"

                draw_status(
                    annotated,
                    "Status: OBJEK HILANG - RESET",
                    (0, 0, 255)
                )

            else:
                draw_status(
                    annotated,
                    "Status: SIAP OBJEK BARU",
                    (0, 255, 255)
                )

            cv2.putText(
                annotated,
                "Objek kardus belum terdeteksi",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )

        cv2.imshow("Tahap 7 - Deteksi P x L Margin", annotated)
        cv2.imshow("Tahap 7 - Mask Kardus", mask)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            print("Keluar dari Tahap 7.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()