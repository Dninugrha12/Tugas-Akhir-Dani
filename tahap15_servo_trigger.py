import RPi.GPIO as GPIO
import time

# ==================================================
# TAHAP 15: SERVO TRIGGER PENDORONG PAKET
# ==================================================
# File ini TIDAK dijalankan langsung.
# File ini dipanggil oleh tahap14_integrated_chargeable.py
# setelah chargeable_weight_g valid dan data final tersimpan.
#
# Posisi servo:
# Standby = 180 derajat
# Dorong  = 90 derajat
#
# Parameter layanan:
# Reguler : w <= 700 g        total dorong+kembali = 1.2 detik
# Express : 700 < w <= 1300 g total dorong+kembali = 1.5 detik
# Kargo   : 1300 < w <= 2000 g total dorong+kembali = 1.8 detik
# ==================================================


# ==================================================
# KONFIGURASI SERVO
# ==================================================
SERVO_PIN = 18          # GPIO18 / pin fisik 12
SUDUT_STANDBY = 180
SUDUT_DORONG = 90
STEP_SERVO = 5

servo = None
servo_ready = False


# ==================================================
# KONVERSI SUDUT KE DUTY CYCLE
# ==================================================
def sudut_ke_duty_cycle(sudut):
    """
    Mengubah sudut servo 0-180 derajat menjadi duty cycle.
    Rumus umum servo standar:
    0 derajat   sekitar duty cycle 2%
    90 derajat  sekitar duty cycle 7%
    180 derajat sekitar duty cycle 12%
    """
    return 2 + (sudut / 18)


# ==================================================
# SETUP SERVO
# ==================================================
def setup_servo():
    """
    Inisialisasi GPIO dan servo.
    Fungsi ini dipanggil sekali di awal program tahap 14.
    """

    global servo, servo_ready

    if servo_ready:
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SERVO_PIN, GPIO.OUT)

    servo = GPIO.PWM(SERVO_PIN, 50)
    servo.start(0)

    servo_ready = True

    print("Mengatur servo pendorong ke posisi standby 180°...")
    servo_ke_standby_awal()
    print("Servo pendorong siap.")


def servo_ke_standby_awal():
    """
    Mengarahkan servo ke posisi standby.
    """

    global servo

    if servo is None:
        print("Servo belum di-setup.")
        return

    servo.ChangeDutyCycle(sudut_ke_duty_cycle(SUDUT_STANDBY))
    time.sleep(0.5)
    servo.ChangeDutyCycle(0)


# ==================================================
# HITUNG DELAY BERDASARKAN TARGET WAKTU
# ==================================================
def hitung_delay(sudut_awal, sudut_akhir, step, target_waktu_gerak):
    """
    Menghitung delay per step agar total waktu gerak
    mendekati target waktu yang ditentukan.

    Rumus:
    jumlah_langkah = selisih_sudut / step
    delay = target_waktu_gerak / jumlah_langkah
    """

    selisih_sudut = abs(sudut_awal - sudut_akhir)
    jumlah_langkah = selisih_sudut / step

    if jumlah_langkah == 0:
        return 0

    return target_waktu_gerak / jumlah_langkah


# ==================================================
# GERAK SERVO BERTAHAP
# ==================================================
def gerak_servo_bertahap(sudut_awal, sudut_akhir, step, delay):
    """
    Menggerakkan servo dari sudut_awal ke sudut_akhir secara bertahap.
    Fungsi ini dibuat tanpa print per step agar gerakan lebih mendekati target waktu.
    """

    global servo

    if servo is None:
        print("Servo belum di-setup.")
        return 0

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

    # Pastikan servo mencapai sudut akhir
    servo.ChangeDutyCycle(sudut_ke_duty_cycle(sudut_akhir))
    time.sleep(0.03)

    # Duty cycle dimatikan untuk mengurangi getaran servo
    servo.ChangeDutyCycle(0)

    waktu_selesai = time.monotonic()
    return waktu_selesai - waktu_mulai


# ==================================================
# TENTUKAN LAYANAN
# ==================================================
def tentukan_layanan(chargeable_weight_g):
    """
    Menentukan layanan berdasarkan chargeable weight dalam gram.
    """

    if chargeable_weight_g <= 0:
        return {
            "nama": "TIDAK VALID",
            "total_waktu": None
        }

    if chargeable_weight_g <= 700:
        return {
            "nama": "REGULER",
            "total_waktu": 1.2
        }

    elif chargeable_weight_g <= 1300:
        return {
            "nama": "EXPRESS",
            "total_waktu": 1.5
        }

    elif chargeable_weight_g <= 2000:
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
# PROSES DORONG PAKET
# ==================================================
def proses_dorong_paket(chargeable_weight_g):
    """
    Fungsi utama tahap 15.
    Fungsi ini dipanggil dari tahap 14 setelah chargeable_weight_g valid.

    Alur:
    1. Terima chargeable_weight_g
    2. Tentukan layanan
    3. Hitung waktu dorong dan waktu kembali
    4. Servo bergerak 180° ke 90°
    5. Servo kembali 90° ke 180°
    """

    if not servo_ready:
        setup_servo()

    layanan = tentukan_layanan(chargeable_weight_g)

    if layanan["nama"] == "TIDAK VALID":
        print("Chargeable weight tidak valid. Servo tidak diaktifkan.")
        return {
            "status": False,
            "layanan": layanan["nama"],
            "pesan": "Chargeable weight tidak valid"
        }

    if layanan["nama"] == "MELEBIHI BATAS":
        print("Paket melebihi batas 2000 gram. Servo tidak diaktifkan.")
        return {
            "status": False,
            "layanan": layanan["nama"],
            "pesan": "Paket melebihi batas maksimum"
        }

    total_waktu = layanan["total_waktu"]

    # Total waktu dibagi dua:
    # 50% untuk dorong, 50% untuk kembali standby
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

    print("\n====================================")
    print("TAHAP 15 - SERVO PENDORONG")
    print("====================================")
    print(f"Chargeable Weight : {chargeable_weight_g:.1f} gram")
    print(f"Layanan           : {layanan['nama']}")
    print(f"Target Total      : {total_waktu:.2f} detik")
    print(f"Waktu Dorong      : {waktu_dorong:.2f} detik")
    print(f"Waktu Kembali     : {waktu_kembali:.2f} detik")
    print(f"Sudut Standby     : {SUDUT_STANDBY}°")
    print(f"Sudut Dorong      : {SUDUT_DORONG}°")
    print(f"Step Servo        : {STEP_SERVO}°")
    print("====================================")

    waktu_mulai_total = time.monotonic()

    print("Servo mulai mendorong paket...")
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
    durasi_total = waktu_selesai_total - waktu_mulai_total

    print("\n====================================")
    print("HASIL GERAK SERVO")
    print("====================================")
    print(f"Durasi dorong aktual  : {durasi_dorong:.2f} detik")
    print(f"Durasi kembali aktual : {durasi_kembali:.2f} detik")
    print(f"Durasi total aktual   : {durasi_total:.2f} detik")
    print("Servo sudah kembali standby.")
    print("====================================")

    return {
        "status": True,
        "layanan": layanan["nama"],
        "chargeable_weight_g": chargeable_weight_g,
        "target_total": total_waktu,
        "durasi_dorong": durasi_dorong,
        "durasi_kembali": durasi_kembali,
        "durasi_total": durasi_total
    }


# ==================================================
# CLEANUP SERVO
# ==================================================
def cleanup_servo():
    """
    Membersihkan GPIO servo.
    Fungsi ini dipanggil di bagian finally pada tahap 14.
    """

    global servo, servo_ready

    if servo is not None:
        servo.stop()

    GPIO.cleanup()

    servo = None
    servo_ready = False

    print("GPIO servo tahap 15 sudah dibersihkan.")