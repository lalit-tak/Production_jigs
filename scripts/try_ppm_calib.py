import serial
import time
HEADER = b"\x68\x0B\x68"
FRAME_LEN = 14

def parse_frame(f):
    if f[:3] != HEADER or f[12:14] != b"\r\n":
        return None
    if (-sum(f[1:11])) & 0xFF != f[11]:          # checksum check
        return None
    raw = int.from_bytes(f[5:9], "big")
    return {
        "serial":    int.from_bytes(f[3:5], "big"),
        "ticks":     raw,                           # e.g. 1000015
        "freq_hz":   raw / 1_000_000,               # e.g. 1.000015
        "drift_ppm": int.from_bytes(f[9:11], "big", signed=True),
    }

def read_frames(port):
    ser = serial.Serial(port, 9600, bytesize=8, parity="N", stopbits=1, timeout=2)
    ser.dtr = True                    # Docklight shows DTR ON, jig is wired to DTR
    ser.reset_input_buffer()
    buf = bytearray()
    try:
        while True:
            buf += ser.read(ser.in_waiting or 1)   # blocks till at least 1 byte
            while True:
                i = buf.find(HEADER)
                if i < 0:
                    del buf[:-2]                   # keep possible partial header
                    break
                if len(buf) - i < FRAME_LEN:
                    del buf[:i]                    # wait for rest of frame
                    break
                frame = bytes(buf[i:i + FRAME_LEN])
                result = parse_frame(frame)
                if result:
                    del buf[:i + FRAME_LEN]
                    yield frame, result
                else:
                    del buf[:i + 1]                # bad frame, resync
            # break
    finally:
        ser.close()

# if __name__ == "__main__":
#     try:
#         print("Before calib")
#         for frame, r in read_frames("COM5"):
#             print(f"{frame.hex(' ').upper()} | SN={r['serial']} "
#                   f"F={r['freq_hz']:.6f} Hz Drift={r['drift_ppm']:+d} ppm")
#             time.sleep(10)
#     except KeyboardInterrupt:
#         pass


if __name__ == "__main__":
    try:
        print("Before calib after of on - 0")

        last_read_time = 0
        interval = 10  # seconds

        for frame, r in read_frames("COM5"):
            now = time.monotonic()

            if now - last_read_time >= interval:
                print(
                    f"{frame.hex(' ').upper()} | "
                    f"SN={r['serial']} "
                    f"F={r['freq_hz']:.6f} Hz "
                    f"Drift={r['drift_ppm']:+d} ppm"
                )
                last_read_time = now

    except KeyboardInterrupt:
        pass


# # # 68 0B 68 5A B6 00 0F 42 3F FF FF EF 0D 0A | SN=23222 F=0.999999 Hz Drift=-1 ppm
# temp_value = 32
# ppm_value = 999702
# temp_bytes = temp_value.to_bytes(4, "big")
# ppm_bytes = ppm_value.to_bytes(4, "big")

# print(temp_bytes, ppm_bytes)