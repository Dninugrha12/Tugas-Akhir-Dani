ALUR FINAL SISTEM PENGUKURAN PAKET

Tahap 2:
- tahap2_test_camera.py
- Fungsi: menguji kamera/webcam.

Tahap 3A:
- tahap3a_capture_chessboard.py
- Fungsi: mengambil gambar chessboard untuk kalibrasi kamera.

Tahap 3B:
- tahap3b_calibrate_camera.py
- Fungsi: menghasilkan file camera_calibration.npz.

Tahap 3C:
- tahap3c_test_undistort.py
- Fungsi: menguji hasil undistort kamera.

Tahap 4A:
- tahap4a_capture_workspace_undistorted.py
- Fungsi: mengambil gambar area kerja versi undistorted.

Tahap 4B:
- tahap4b_select_points_undistorted.py
- Fungsi: memilih 4 titik sudut area kerja pada gambar undistorted.

Tahap 5A:
- tahap5a_perspective_undistorted.py
- Fungsi: membuat perspective transform dengan margin.

Tahap 6:
- tahap6_pixel_to_cm.py
- Fungsi: menghitung skala pixel ke cm.

Tahap 7:
- tahap7_measure_pxl_undistorted.py
- Fungsi: mengukur panjang dan lebar objek dari kamera.

Tahap 9:
- tahap9_ultrasonic_height.py
- Fungsi: membaca tinggi objek dari sensor ultrasonik.

Tahap 10:
- tahap10_measure_pxl_ultrasonic.py
- Fungsi: menggabungkan kamera dan ultrasonik untuk mendapatkan P, L, T, volume, dan berat volumetrik.

Tahap 11:
- tahap11_calibrate_loadcell.py
- Fungsi: kalibrasi loadcell HX711.

Tahap 12:
- tahap12_read_actual_weight.py
- Fungsi: membaca berat aktual dari loadcell.

Tahap 13:
- tahap13_chargeable_weight.py
- Fungsi: membandingkan berat aktual dan berat volumetrik, lalu memilih nilai terbesar sebagai chargeable weight.

Tahap 14:
- tahap14_integrated_chargeable.py
- Fungsi: program integrasi 1x run untuk membaca P, L, T, berat volumetrik, berat aktual, dan chargeable weight.

CATATAN:
File lama tahap3_select_points.py, tahap4_perspective.py, dan tahap5_measure_pxl.py tidak digunakan lagi pada alur final karena sudah digantikan oleh versi undistorted:
- tahap4b_select_points_undistorted.py
- tahap5a_perspective_undistorted.py
- tahap7_measure_pxl_undistorted.py

BATASAN SISTEM:
- Paket dengan berat aktual di bawah 50 gram dianggap tidak terbaca.
- Jika berat aktual di bawah 50 gram, sistem menampilkan T = 0.00 cm dan Berat Aktual = 0.00 g.
- Program utama final dijalankan dari root folder program-python, bukan dari folder FINAL_TAHAPAN/scripts_final.
