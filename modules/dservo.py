from gpiozero import AngularServo
from time import sleep

# GPIO18 = pin fisik 12
servo = AngularServo(
    18,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025
)

print("Sistem rack pendorong siap")
print("Masukkan sudut 0 - 180 derajat")
print("Ketik q untuk keluar\n")

# posisi awal
sudut_sekarang = 90
servo.angle = sudut_sekarang
sleep(1)

try:
    while True:
        nilai = input("Masukkan sudut: ")

        if nilai.lower() == "q":
            break

        try:
            sudut_tujuan = float(nilai)

            # batasi input agar tetap 0-180
            if sudut_tujuan < 0:
                sudut_tujuan = 0
            elif sudut_tujuan > 180:
                sudut_tujuan = 180

            # keterangan arah servo
            if sudut_tujuan > sudut_sekarang:
                arah = "servo maju"
            elif sudut_tujuan < sudut_sekarang:
                arah = "servo mundur"
            else:
                arah = "servo diam"

            print(f"{arah} | Sudut servo: {sudut_tujuan}°")

            # langsung ke sudut yang diminta
            servo.angle = sudut_tujuan
            sleep(0.8)

            sudut_sekarang = sudut_tujuan

        except ValueError:
            print("Masukkan angka yang benar!")

except KeyboardInterrupt:
    print("\nProgram dihentikan")

finally:
    servo.angle = 0
    print("Servo kembali ke 0°")