import RPi.GPIO as GPIO
import time

# ==================================================
# PROGRAM UJI SERVO PENDORONG BERDASARKAN LAYANAN
# Target waktu adalah TOTAL dorong + kembali
#
# Standby = 180 derajat
# Dorong  = 90 derajat
#
# Reguler total = 1.2 detik
# Express total = 1.5 detik
# Kargo   total = 1.8 detik
# ==================================================

# ------------------------------
# Konfigurasi GPIO
# ------------------------------
SERVO_PIN = 18  # GPIO18 / pin fisik 12

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

servo = GPIO.PWM(SERVO_PIN, 50)
servo.start(0)

# ------------------------------
# Posisi servo
# ------------------------------
SUDUT_STANDBY = 180
SUDUT_DORONG = 90

# Step gerakan servo
STEP_SERVO = 5


# ==================================================
# Fungsi konversi sudut ke duty cycle
# ==================================================
def sudut_ke_duty_cycle(sudut):
    return 2 + (sudut / 18)


# ==================================================
# Fungsi menentukan layanan
# ==================================================
def tentukan_layanan(chargeable_weight):
    """
    Menentukan layanan berdasarkan chargeable weight dalam gram.
    Target waktu adalah total dorong + kembali.
    """

    if chargeable_weight <= 0:
        return None

    if chargeable_weight <= 700:
        return {
            "nama": "REGULER",
            "total_waktu": 1.2
        }

    elif chargeable_weight <= 1300:
        return {
            "nama": "EXPRESS",
            "total_waktu": 1.5
        }

    elif chargeable_weight <= 2000:
        return {
            "nama": "KARGO",
            "total_waktu": 1.8
        }

    else:
        return {
            "nama": "MELEBIHI BATAS",
            "total_waktu": None
        }


# ==================================================
# Fungsi hitung delay
# ==================================================
def hitung_delay(sudut_awal, sudut_akhir, step, target_waktu_gerak):
    """
    Menghitung delay per step.
    """

    selisih_sudut = abs(sudut_awal - sudut_akhir)
    jumlah_langkah = selisih_sudut / step

    if jumlah_langkah == 0:
        return 0

    delay = target_waktu_gerak / jumlah_langkah
    return delay


# ==================================================
# Fungsi gerak servo bertahap
# ==================================================
def gerak_servo_bertahap(sudut_awal, sudut_akhir, step, delay):
    """
    Menggerakkan servo dari sudut_awal ke sudut_akhir
    tanpa print per step agar waktu lebih mendekati target.
    """

    waktu_mulai = time.monotonic()

    if sudut_awal > sudut_akhir:
        sudut = sudut_awal
        while sudut >= sudut_akhir:
            servo.ChangeDutyCycle(sudut_ke_duty_cycle(sudut))
            time.sleep(delay)
            sudut -= step

    elif sudut_awal < sudut_akhir:
        sudut = sudut_awal
        while sudut <= sudut_akhir:
            servo.ChangeDutyCycle(sudut_ke_duty_cycle(sudut))
            time.sleep(delay)
            sudut += step

    else:
        servo.ChangeDutyCycle(sudut_ke_duty_cycle(sudut_awal))
        time.sleep(delay)

    # Pastikan servo sampai sudut akhir
    servo.ChangeDutyCycle(sudut_ke_duty_cycle(sudut_akhir))

    # Delay kecil agar servo sempat menerima posisi akhir
    time.sleep(0.03)

    # Matikan duty cycle agar servo tidak getar
    servo.ChangeDutyCycle(0)

    waktu_selesai = time.monotonic()
    durasi_aktual = waktu_selesai - waktu_mulai

    return durasi_aktual


# ==================================================
# Fungsi standby awal
# ==================================================
def servo_ke_standby_awal():
    print("Mengatur servo ke posisi standby 180°...")
    servo.ChangeDutyCycle(sudut_ke_duty_cycle(SUDUT_STANDBY))
    time.sleep(0.5)
    servo.ChangeDutyCycle(0)
    print("Servo siap di posisi standby.")


# ==================================================
# Fungsi proses dorong paket
# ==================================================
def proses_dorong_paket(chargeable_weight):
    layanan = tentukan_layanan(chargeable_weight)

    if layanan is None:
        print("Chargeable weight tidak valid. Nilai harus lebih dari 0 gram.")
        return

    if layanan["nama"] == "MELEBIHI BATAS":
        print("\n====================================")
        print("HASIL KLASIFIKASI PAKET")
        print("====================================")
        print(f"Chargeable Weight : {chargeable_weight:.1f} gram")
        print("Status            : MELEBIHI BATAS")
        print("Keterangan        : Paket melebihi kapasitas maksimum 2000 gram.")
        print("Servo             : Tidak diaktifkan.")
        print("====================================")
        return

    total_waktu = layanan["total_waktu"]

    # Karena total waktu terdiri dari dorong + kembali,
    # maka masing-masing gerakan mendapat setengah waktu.
    waktu_dorong = total_waktu / 2
    waktu_kembali = total_waktu / 2

    delay_dorong = hitung_delay(
        SUDUT_STANDBY,
        SUDUT_DORONG,
        STEP_SERVO,
        waktu_dorong
    )

    delay_kembali = hitung_delay(
        SUDUT_DORONG,
        SUDUT_STANDBY,
        STEP_SERVO,
        waktu_kembali
    )

    jumlah_langkah = abs(SUDUT_STANDBY - SUDUT_DORONG) / STEP_SERVO

    print("\n====================================")
    print("HASIL KLASIFIKASI PAKET")
    print("====================================")
    print(f"Chargeable Weight       : {chargeable_weight:.1f} gram")
    print(f"Layanan                 : {layanan['nama']}")
    print(f"Sudut Standby           : {SUDUT_STANDBY}°")
    print(f"Sudut Dorong            : {SUDUT_DORONG}°")
    print(f"Step Servo              : {STEP_SERVO}°")
    print(f"Jumlah Langkah          : {jumlah_langkah:.0f} langkah")
    print("------------------------------------")
    print(f"Target Total Waktu      : {total_waktu:.2f} detik")
    print(f"Target Waktu Dorong     : {waktu_dorong:.2f} detik")
    print(f"Target Waktu Kembali    : {waktu_kembali:.2f} detik")
    print("------------------------------------")
    print(f"Delay Dorong per Step   : {delay_dorong:.4f} detik")
    print(f"Delay Kembali per Step  : {delay_kembali:.4f} detik")
    print("====================================")

    input("\nTekan ENTER untuk mulai mendorong paket...")

    # Pastikan servo berada di posisi standby
    servo.ChangeDutyCycle(sudut_ke_duty_cycle(SUDUT_STANDBY))
    time.sleep(0.1)
    servo.ChangeDutyCycle(0)

    print("\nServo mulai mendorong paket...")
    waktu_mulai_total = time.monotonic()

    durasi_dorong = gerak_servo_bertahap(
        SUDUT_STANDBY,
        SUDUT_DORONG,
        STEP_SERVO,
        delay_dorong
    )

    print("Servo kembali ke posisi standby...")

    durasi_kembali = gerak_servo_bertahap(
        SUDUT_DORONG,
        SUDUT_STANDBY,
        STEP_SERVO,
        delay_kembali
    )

    waktu_selesai_total = time.monotonic()
    durasi_total_aktual = waktu_selesai_total - waktu_mulai_total

    print("\n====================================")
    print("HASIL WAKTU AKTUAL PROGRAM")
    print("====================================")
    print(f"Target total waktu        : {total_waktu:.2f} detik")
    print(f"Durasi aktual dorong      : {durasi_dorong:.2f} detik")
    print(f"Durasi aktual kembali     : {durasi_kembali:.2f} detik")
    print(f"Durasi aktual total       : {durasi_total_aktual:.2f} detik")
    print("====================================")
    print("Servo sudah kembali standby dan siap untuk paket berikutnya.")


# ==================================================
# Program utama
# ==================================================
try:
    servo_ke_standby_awal()

    while True:
        print("\n====================================")
        print("  UJI SERVO TOTAL WAKTU BERDASARKAN CW")
        print("====================================")
        print("Reguler : w <= 700 g       | total 1.2 detik")
        print("Express : 700 < w <= 1300 g| total 1.5 detik")
        print("Kargo   : 1300 < w <= 2000 g| total 1.8 detik")
        print("------------------------------------")
        print("Posisi standby : 180°")
        print("Posisi dorong  : 90°")
        print("------------------------------------")
        print("Ketik 'q' untuk keluar.")
        print("------------------------------------")

        data_input = input("Masukkan chargeable weight paket dalam gram: ")

        if data_input.lower() == "q":
            print("Program dihentikan oleh pengguna.")
            break

        try:
            chargeable_weight = float(data_input)
            proses_dorong_paket(chargeable_weight)

        except ValueError:
            print("Input salah. Masukkan angka saja.")
            print("Contoh input benar: 650, 1000, 1700")

except KeyboardInterrupt:
    print("\nProgram dihentikan dengan Ctrl+C.")

finally:
    servo.stop()
    GPIO.cleanup()
    print("GPIO sudah dibersihkan.")