import asyncio
import websockets
import json
import random
import time
import io
import threading
import socketserver
from http import server as http_server

# ════════════════════════════════════════════════════════════════════
#  CONFIG — change all hardware assignments here, nowhere else
# ════════════════════════════════════════════════════════════════════
CONFIG = {

    # ── Network ──────────────────────────────────────────────────────
    "WEBSOCKET_HOST":   "0.0.0.0",
    "WEBSOCKET_PORT":   8765,           # sensor data + commands
    "VIDEO_HOST":       "0.0.0.0",
    "VIDEO_PORT":       8080,           # MJPEG stream

    # ── Camera ───────────────────────────────────────────────────────
    "CAMERA_INDEX":         0,          # 0 = /dev/video0 (CSI port 0, your OV5647)
    "CAMERA_WIDTH":         640,
    "CAMERA_HEIGHT":        480,
    "CAMERA_FRAMERATE":     30,
    "CAMERA_JPEG_QUALITY":  80,         # 0-100, lower = less bandwidth

    # ── Teensy serial (motion control) ───────────────────────────────
    "TEENSY_PORT":      "/dev/ttyUSB0",
    "TEENSY_BAUDRATE":  115200,

    # ── Gas sensors (MQ series) via ADS1115 ADC over I2C ─────────────
    # ADS1115 has 4 channels: A0, A1, A2, A3
    # Wire each MQ sensor's AOUT pin to one channel
    "GAS_ADC_I2C_ADDRESS":  0x48,       # default ADS1115 address (ADDR pin to GND)
    "GAS_MQ2_CHANNEL":      0,          # A0 — smoke, LPG
    "GAS_MQ4_CHANNEL":      1,          # A1 — methane (primary mine gas)
    "GAS_MQ5_CHANNEL":      2,          # A2 — natural gas
    "GAS_MQ6_CHANNEL":      3,          # A3 — butane/LPG
    # MQ7 (CO) and MQ8 (H2) need a second ADS1115 (address 0x49, ADDR to VCC)
    "GAS_ADC2_I2C_ADDRESS": 0x49,
    "GAS_MQ7_CHANNEL":      0,          # second ADS1115 A0 — carbon monoxide
    "GAS_MQ8_CHANNEL":      1,          # second ADS1115 A1 — hydrogen

    # ── DHT11 (temperature + humidity) ───────────────────────────────
    "DHT_GPIO_PIN":         4,          # BCM GPIO 4 (physical pin 7)
    "DHT_TYPE":             "DHT11",    # "DHT11" or "DHT22"

    # ── Ultrasonic sensors (HC-SR04) ─────────────────────────────────
    "ULTRASONIC_FRONT_TRIG": 17,        # BCM GPIO 17 (physical pin 11)
    "ULTRASONIC_FRONT_ECHO": 27,        # BCM GPIO 27 (physical pin 13)
    "ULTRASONIC_FLOOR_TRIG": 22,        # BCM GPIO 22 (physical pin 15)
    "ULTRASONIC_FLOOR_ECHO": 23,        # BCM GPIO 23 (physical pin 16)

    # ── IMU (MPU6050 gyro + accelerometer) ───────────────────────────
    "IMU_I2C_ADDRESS":      0x68,       # default MPU6050 (AD0 pin LOW)
                                        # use 0x69 if AD0 pin is HIGH

    # ── Magnetometer (HMC5883L or QMC5883L) ─────────────────────────
    "MAG_I2C_ADDRESS":      0x1E,       # HMC5883L default

    # ── Moisture sensor ──────────────────────────────────────────────
    "MOISTURE_GPIO_PIN":    24,         # BCM GPIO 24 — digital out of sensor

    # ── Microwave motion sensor (RCWL-0516) ──────────────────────────
    "MOTION_GPIO_PIN":      25,         # BCM GPIO 25

    # ── Particulate matter (PMS5003 or SDS011 via UART) ──────────────
    "PM_SERIAL_PORT":       "/dev/ttyS0",
    "PM_BAUDRATE":          9600,

    # ── Heat/IR sensor (MLX90614 via I2C) ────────────────────────────
    "HEAT_I2C_ADDRESS":     0x5A,       # MLX90614 default

    # ── Update rates (seconds) ───────────────────────────────────────
    "RATE_GAS":             0.5,        # gas sensors every 500ms
    "RATE_ENV":             1.0,        # temp, humidity, PM every 1s
    "RATE_IMU":             0.1,        # IMU every 100ms
    "RATE_PROX":            0.2,        # ultrasonic every 200ms
    "RATE_MAIN_LOOP":       0.1,        # super loop tick = 100ms
}
# ════════════════════════════════════════════════════════════════════
#  END CONFIG
# ════════════════════════════════════════════════════════════════════


# ── Camera MJPEG streaming ───────────────────────────────────────────

class StreamingOutput(io.BufferedIOBase):
    """Thread-safe buffer that holds the latest JPEG frame."""
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

# Shared output buffer — written by camera thread, read by HTTP clients
stream_output = StreamingOutput()


class MJPEGHandler(http_server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/video':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=MJPEG_FRAME')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                while True:
                    with stream_output.condition:
                        stream_output.condition.wait()
                        frame = stream_output.frame
                    self.wfile.write(b'--MJPEG_FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception:
                pass  # client disconnected normally
        else:
            self.send_error(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request console noise


class ThreadedMJPEGServer(socketserver.ThreadingMixIn, http_server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_camera():
    """
    Starts the OV5647 via picamera2 and pushes JPEG frames
    into stream_output continuously.
    Comment this entire function and the thread call in main()
    to disable camera (e.g. for sensor-only testing).
    """
    try:
        from picamera2 import Picamera2
        from picamera2.encoders import JpegEncoder
        from picamera2.outputs import FileOutput

        cam = Picamera2(CONFIG["CAMERA_INDEX"])
        cam.configure(cam.create_video_configuration(
            main={
                "size": (CONFIG["CAMERA_WIDTH"], CONFIG["CAMERA_HEIGHT"]),
                "format": "RGB888"
            }
        ))
        cam.start_recording(
            JpegEncoder(q=CONFIG["CAMERA_JPEG_QUALITY"]),
            FileOutput(stream_output)
        )
        print(f"[CAM] OV5647 streaming at "
              f"{CONFIG['CAMERA_WIDTH']}x{CONFIG['CAMERA_HEIGHT']} "
              f"{CONFIG['CAMERA_FRAMERATE']}fps")
    except Exception as e:
        print(f"[CAM] Camera failed to start: {e}")
        print("[CAM] Video stream will be unavailable")


def start_video_server():
    """Starts the MJPEG HTTP server in its own thread."""
    srv = ThreadedMJPEGServer(
        (CONFIG["VIDEO_HOST"], CONFIG["VIDEO_PORT"]),
        MJPEGHandler
    )
    print(f"[CAM] MJPEG server on {CONFIG['VIDEO_HOST']}:{CONFIG['VIDEO_PORT']}/video")
    srv.serve_forever()


# ── Sensor reading (simulated — swap with real GPIO reads) ───────────

def read_all_sensors():
    """
    Returns a full sensor packet dict.
    Replace each random.* call with the actual sensor read for that pin.
    Each sensor's pin/address is in CONFIG above.
    """
    return {
        "type": "sensors",
        "gas": {
            # Replace with: AnalogIn(ads1, ADS.P0).voltage
            "mq2": round(random.uniform(0.1, 2.5), 3),   # CONFIG GAS_MQ2_CHANNEL
            "mq4": round(random.uniform(0.1, 3.0), 3),   # CONFIG GAS_MQ4_CHANNEL
            "mq5": round(random.uniform(0.1, 1.5), 3),   # CONFIG GAS_MQ5_CHANNEL
            "mq6": round(random.uniform(0.1, 1.2), 3),   # CONFIG GAS_MQ6_CHANNEL
            "mq7": round(random.uniform(0.1, 2.0), 3),   # CONFIG GAS_MQ7_CHANNEL
            "mq8": round(random.uniform(0.1, 1.8), 3),   # CONFIG GAS_MQ8_CHANNEL
        },
        "env": {
            # Replace with: dht.temperature, dht.humidity
            "temp":     round(random.uniform(28.0, 45.0), 1),  # CONFIG DHT_GPIO_PIN
            "humidity": round(random.uniform(60.0, 98.0), 1),  # CONFIG DHT_GPIO_PIN
            # Replace with: PMS5003 serial read on CONFIG PM_SERIAL_PORT
            "pm25":     round(random.uniform(10.0, 250.0), 1),
            # Replace with: GPIO.input(CONFIG["MOISTURE_GPIO_PIN"])
            "moisture": random.choice([True, False]),
            # Replace with: GPIO.input(CONFIG["MOTION_GPIO_PIN"])
            "motion":   random.choice([True, False]),
            # Replace with: mlx.object_temperature on CONFIG HEAT_I2C_ADDRESS
            "heat_c":   round(random.uniform(25.0, 80.0), 1),
        },
        "imu": {
            # Replace with MPU6050 reads on CONFIG IMU_I2C_ADDRESS
            "pitch": round(random.uniform(-20.0, 20.0), 2),
            "roll":  round(random.uniform(-15.0, 15.0), 2),
            "yaw":   round(random.uniform(0.0, 360.0), 2),
            "ax":    round(random.uniform(-2.0, 2.0), 3),
            "ay":    round(random.uniform(-2.0, 2.0), 3),
            "az":    round(random.uniform(8.0, 11.0), 3),
        },
        "prox": {
            # Replace with HC-SR04 pulse timing on ULTRASONIC_FRONT_TRIG/ECHO
            "front_cm": random.randint(15, 300),
            "floor_cm": random.randint(5, 40),
            "collision": random.random() < 0.05,
        },
        "ts": round(time.time(), 3)
    }


# ── WebSocket server (sensor data out + commands in) ─────────────────

laptop_client = None


async def handle_laptop(websocket):
    global laptop_client
    laptop_client = websocket
    print(f"[WS]  Laptop connected from {websocket.remote_address}")
    try:
        async for raw in websocket:
            cmd = json.loads(raw)
            print(f"[CMD] Received: {cmd}")
            # TODO: serial.write(cmd) to Teensy on CONFIG["TEENSY_PORT"]
    except websockets.exceptions.ConnectionClosed:
        print("[WS]  Laptop disconnected")
    finally:
        laptop_client = None


async def super_loop():
    """
    Main data loop: reads all sensors, packs into JSON,
    sends to laptop at RATE_MAIN_LOOP interval.
    """
    last_gas  = 0
    last_env  = 0
    last_imu  = 0
    last_prox = 0

    while True:
        now = time.time()
        should_send = False

        # Build packet only for sensors whose rate has elapsed
        packet = {"type": "sensors", "ts": round(now, 3)}

        if now - last_gas >= CONFIG["RATE_GAS"]:
            data = read_all_sensors()
            packet["gas"]  = data["gas"]
            packet["env"]  = data["env"]
            last_gas = now
            last_env = now
            should_send = True

        if now - last_imu >= CONFIG["RATE_IMU"]:
            data = read_all_sensors()
            packet["imu"] = data["imu"]
            last_imu = now
            should_send = True

        if now - last_prox >= CONFIG["RATE_PROX"]:
            data = read_all_sensors()
            packet["prox"] = data["prox"]
            last_prox = now
            should_send = True

        if should_send and laptop_client:
            try:
                await laptop_client.send(json.dumps(packet))
            except Exception as e:
                print(f"[WS]  Send error: {e}")

        await asyncio.sleep(CONFIG["RATE_MAIN_LOOP"])


async def main():
    ws_host = CONFIG["WEBSOCKET_HOST"]
    ws_port = CONFIG["WEBSOCKET_PORT"]
    print(f"[WS]  WebSocket server on {ws_host}:{ws_port}")

    ws_server = await websockets.serve(handle_laptop, ws_host, ws_port)
    await asyncio.gather(ws_server.wait_closed(), super_loop())


if __name__ == "__main__":
    # Start camera capture
    threading.Thread(target=start_camera, daemon=True).start()
    # Start MJPEG HTTP server
    threading.Thread(target=start_video_server, daemon=True).start()
    # Start WebSocket + super loop
    asyncio.run(main())
