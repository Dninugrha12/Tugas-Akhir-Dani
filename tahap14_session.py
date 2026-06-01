"""
TAHAP 14 SESSION - In-process measurement session (Opsi C)

Membungkus logika tahap14 menjadi objek "kamera hangat":
- INIT sekali (GPIO, loadcell, kamera, kalibrasi) -> kamera tetap terbuka.
- measure_once(): SATU pengukuran, tanpa window OpenCV, tanpa input(),
  tanpa loop tak terbatas. Return dict hasil (key gaya tahap14).
- retare(): re-tare loadcell saat idle (lawan drift HX711).
- close(): lepas kamera + cleanup GPIO.

PENTING: file ini ME-REUSE fungsi dari tahap14_integrated_chargeable.py
(diimport sebagai modul `t14`). TIDAK menyalin logika hitung, supaya tidak
menyimpang dari alat ukur yang sudah divalidasi laporan.

File ini HANYA jalan di Raspberry Pi (butuh cv2 + RPi.GPIO via cvsys/hx711).
"""

import os
import time
import statistics
from datetime import datetime


class NeedCalibration(Exception):
    """File kalibrasi (sensor point / background / loadcell) hilang/invalid."""


class MeasurementTimeout(Exception):
    """Paket tidak terdeteksi/stabil dalam batas waktu."""


# Default lokasi background hasil tahap10 (kalau konstanta cvsys tak ada)
_DEFAULT_BACKGROUND_PATH = os.path.join("hasil_tahap10", "latest_live_background.jpg")

# Jumlah sampel untuk re-tare otomatis (platform kosong)
_RETARE_SAMPLES = 25


class MeasurementSession:
    """Sesi pengukuran in-process dengan kamera tetap hangat."""

    def __init__(self, headless=True):
        self.headless = headless

        # Lazy import modul hardware/tahap14 (hanya tersedia di Pi)
        import tahap14_integrated_chargeable as t14
        self._t14 = t14
        self._cvsys = t14.cvsys

        cvsys = self._cvsys

        # --- GPIO + ultrasonik ---
        cvsys.setup_gpio()
        self.ultrasonic_base_cm = cvsys.load_ultrasonic_base_distance()

        # --- Loadcell ---
        self.loadcell_calibration = t14.load_loadcell_calibration()
        self.hx = t14.init_loadcell(self.loadcell_calibration)
        self.calibration_factor = float(self.loadcell_calibration["calibration_factor"])
        self.offset_calibration = float(self.loadcell_calibration["offset_final"])
        # Offset awal: pakai nilai kalibrasi tersimpan. retare() bisa memperbaruinya.
        self.offset = self.offset_calibration

        # --- Kamera (dibuka SEKALI, tetap hangat) ---
        cap, device, frame_w, frame_h = t14.open_fixed_camera(t14.FIXED_CAMERA_DEVICE)
        if cap is None:
            raise RuntimeError("Kamera gagal dibuka pada inisialisasi sesi.")
        self.cap = cap
        self.device = device
        self.frame_w = frame_w
        self.frame_h = frame_h

        # --- Kalibrasi kamera + warp + skala ---
        (self.camera_matrix,
         self.dist_coeffs,
         self.new_camera_matrix) = cvsys.load_calibration(frame_w, frame_h)
        self.points = cvsys.load_points()
        self.scale = cvsys.load_scale()
        self.px_per_cm_x = float(self.scale["px_per_cm_x"])
        self.px_per_cm_y = float(self.scale["px_per_cm_y"])

        # --- Sensor point: load dari file (TANPA klik mouse) ---
        self.sensor_point = self._load_sensor_point()

        # --- Background: load dari file (TANPA capture live) ---
        self.background = self._load_background()

    # -----------------------------------------------------------------
    # Loaders (fail-loud kalau kalibrasi belum ada)
    # -----------------------------------------------------------------
    def _load_sensor_point(self):
        cvsys = self._cvsys
        point = None
        if hasattr(cvsys, "load_sensor_point"):
            try:
                point = cvsys.load_sensor_point()
            except Exception:
                point = None
        if not point:
            raise NeedCalibration(
                "Titik sensor belum dikalibrasi (hasil_tahap10/sensor_point.json "
                "tidak ada). Jalankan kalibrasi attended dulu."
            )
        return point

    def _load_background(self):
        import cv2
        cvsys = self._cvsys
        path = getattr(cvsys, "LIVE_BACKGROUND_PATH", _DEFAULT_BACKGROUND_PATH)
        if not os.path.isfile(path):
            raise NeedCalibration(
                "Background workspace belum tersedia (" + path + "). "
                "Jalankan kalibrasi attended (capture background kosong) dulu."
            )
        background = cv2.imread(path)
        if background is None:
            raise NeedCalibration(
                "Background workspace gagal dibaca: " + path
            )
        return background

    # -----------------------------------------------------------------
    # Re-tare (lawan drift HX711) - dipanggil saat idle / platform kosong
    # -----------------------------------------------------------------
    def retare(self, sample_count=_RETARE_SAMPLES):
        """Hitung ulang offset loadcell dari platform kosong (tanpa input())."""
        t14 = self._t14
        readings = []
        while len(readings) < sample_count:
            value = t14.safe_get_weight(self.hx)
            if value is not None:
                readings.append(value)
            time.sleep(0.05)
        if not readings:
            raise RuntimeError("Gagal membaca loadcell saat retare.")
        filtered = t14.remove_outliers(readings)
        self.offset = float(statistics.median(filtered))
        return self.offset

    def read_weight(self):
        """Baca berat aktual loadcell sekali (gram). Untuk polling autopilot.

        Lock dikelola pemanggil (web engine). Reuse read_actual_weight_once
        agar konsisten dengan jalur pengukuran.
        """
        data = self._t14.read_actual_weight_once(self.hx, self.offset)
        return data["actual_weight_g"]


    def _compute_frame(self):
        """Hitung satu frame -> current_data dict, atau None bila belum valid.

        Reuse penuh fungsi tahap14/cvsys. Mengembalikan tuple
        (current_data, annotated, mask) atau (None, reason, None).
        """
        import cv2
        t14 = self._t14
        cvsys = self._cvsys

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None, "frame_read_failed", None

        undistorted = cvsys.undistort_frame(
            frame, self.camera_matrix, self.dist_coeffs, self.new_camera_matrix
        )
        warped = cvsys.warp_workspace_margin(undistorted, self.points, self.scale)
        annotated = warped.copy()

        actual_data = t14.read_actual_weight_once(self.hx, self.offset)
        actual_weight_g = actual_data["actual_weight_g"]

        if actual_weight_g < t14.MIN_VALID_ACTUAL_WEIGHT_G:
            return None, "weight_below_min", None

        height_data = cvsys.read_height_ultrasonic(self.ultrasonic_base_cm)
        if height_data is None:
            return None, "ultrasonic_failed", None

        tinggi_raw_cm = float(height_data.get("height_raw_cm", height_data["height_cm"]))
        tinggi_cm = float(height_data["height_cm"])

        contour, mask, detection_mode = t14.detect_object_tahap14(
            warped, self.background, self.scale, self.sensor_point
        )
        if contour is None:
            return None, "object_not_valid", None

        measurement = cvsys.measure_contour(
            contour, self.px_per_cm_x, self.px_per_cm_y
        )
        panjang_raw_cm = float(measurement["panjang_raw_cm"])
        lebar_raw_cm = float(measurement["lebar_raw_cm"])

        panjang_cm, lebar_cm, height_factor = cvsys.apply_height_correction(
            panjang_raw_cm, lebar_raw_cm, tinggi_cm, self.ultrasonic_base_cm
        )

        volume_cm3, berat_volumetrik_kg, berat_volumetrik_g = \
            cvsys.calculate_volume_and_volumetric_weight(panjang_cm, lebar_cm, tinggi_cm)

        decision = t14.decide_chargeable_weight(berat_volumetrik_g, actual_weight_g)

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
            "detection_mode": detection_mode,
        }

        cv2.drawContours(annotated, [measurement["box"]], 0, (0, 255, 0), 2)
        return current_data, annotated, mask

    def measure_once(self, timeout=30):
        """Jalankan satu siklus pengukuran sampai stabil, lalu simpan & return.

        Tidak ada window/keyboard. Berhenti saat STABLE_FRAME_TARGET frame stabil
        terkumpul, atau raise MeasurementTimeout bila melewati `timeout` detik.
        """
        t14 = self._t14

        stable_buffer = []
        deadline = time.time() + timeout
        last_annotated = None
        last_mask = None

        while time.time() < deadline:
            current_data, annotated, mask = self._compute_frame()

            if current_data is None:
                stable_buffer = []
                time.sleep(0.02)
                continue

            last_annotated = annotated
            last_mask = mask

            stable_buffer.append(current_data)
            if len(stable_buffer) > t14.STABLE_FRAME_TARGET:
                stable_buffer.pop(0)

            if t14.is_integrated_stable(stable_buffer):
                return self._finalize(stable_buffer, last_annotated, last_mask)

        raise MeasurementTimeout(
            "Paket tidak terdeteksi/stabil dalam {} detik.".format(timeout)
        )

    def _finalize(self, stable_buffer, annotated, mask):
        """Bangun final_result (assembly, reuse average_integrated) + simpan."""
        t14 = self._t14
        avg_data = t14.average_integrated(stable_buffer)

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
            "ultrasonic_base_cm": round(self.ultrasonic_base_cm, 3),
            "loadcell_calibration_factor": self.calibration_factor,
            "loadcell_offset_calibration": self.offset_calibration,
            "loadcell_offset_live": self.offset,
            "min_valid_actual_weight_g": t14.MIN_VALID_ACTUAL_WEIGHT_G,
            "loadcell_zero_threshold_g": t14.LOADCELL_ZERO_THRESHOLD_G,
            "sensor_point_x": int(self.sensor_point[0]),
            "sensor_point_y": int(self.sensor_point[1]),
            "source_loadcell_calibration_file": t14.LOADCELL_CALIBRATION_FILE,
            "formula_volumetric": "berat_volumetrik_g = P x L x T / 6",
            "formula_chargeable": "chargeable_weight_g = max(berat_volumetrik_g, berat_aktual_g)",
        }

        # save_integrated_result menambahkan measurement_id, json_file,
        # detection_image, mask_image, lalu tulis JSON/CSV/jpg.
        t14.save_integrated_result(annotated, mask, final_result)
        return final_result

    # -----------------------------------------------------------------
    def close(self):
        """Lepas kamera + cleanup GPIO."""
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        self.cap = None
        try:
            self._cvsys.cleanup_gpio()
        except Exception:
            pass
