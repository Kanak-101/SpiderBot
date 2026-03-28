.PHONY: install

install:
	@echo "--- Installing Dependencies and Script ---"
	sudo apt update && sudo apt upgrade -y
	sudo apt install -y python3-full python3-websockets python3-picamera2 python3-libcamera
	sudo nmcli connection add \ type ethernet \ ifname eth0 \ con-name "laptop-link" \ ipv4.method manual \ ipv4.addresses 192.168.10.1/24 \ ipv4.never-default yes \ connection.autoconnect yes
	sudo nmcli connection up "laptop-link"
	@sudo tee /home/rpi_node.py > /dev/null << 'EOF'
	import asyncio
	import websockets
	import json
	import random
	import time
	import io
	import threading
	import socketserver
	from http import server as http_server

	CONFIG = {
	    "WEBSOCKET_HOST": "0.0.0.0",
	    "WEBSOCKET_PORT": 8765,
	    "VIDEO_HOST": "0.0.0.0",
	    "VIDEO_PORT": 8080,
	    "CAMERA_INDEX": 0,
	    "CAMERA_WIDTH": 640,
	    "CAMERA_HEIGHT": 480,
	    "CAMERA_FRAMERATE": 30,
	    "CAMERA_JPEG_QUALITY": 80,
	    "TEENSY_PORT": "/dev/ttyUSB0",
	    "TEENSY_BAUDRATE": 115200,
	    "GAS_ADC_I2C_ADDRESS": 0x48,
	    "GAS_MQ2_CHANNEL": 0,
	    "GAS_MQ4_CHANNEL": 1,
	    "GAS_MQ5_CHANNEL": 2,
	    "GAS_MQ6_CHANNEL": 3,
	    "GAS_ADC2_I2C_ADDRESS": 0x49,
	    "GAS_MQ7_CHANNEL": 0,
	    "GAS_MQ8_CHANNEL": 1,
	    "DHT_GPIO_PIN": 4,
	    "DHT_TYPE": "DHT11",
	    "ULTRASONIC_FRONT_TRIG": 17,
	    "ULTRASONIC_FRONT_ECHO": 27,
	    "ULTRASONIC_FLOOR_TRIG": 22,
	    "ULTRASONIC_FLOOR_ECHO": 23,
	    "IMU_I2C_ADDRESS": 0x68,
	    "MAG_I2C_ADDRESS": 0x1E,
	    "MOISTURE_GPIO_PIN": 24,
	    "MOTION_GPIO_PIN": 25,
	    "PM_SERIAL_PORT": "/dev/ttyS0",
	    "PM_BAUDRATE": 9600,
	    "HEAT_I2C_ADDRESS": 0x5A,
	    "RATE_GAS": 0.5,
	    "RATE_ENV": 1.0,
	    "RATE_IMU": 0.1,
	    "RATE_PROX": 0.2,
	    "RATE_MAIN_LOOP": 0.1,
	}

	class StreamingOutput(io.BufferedIOBase):
	    def __init__(self):
		self.frame = None
		self.condition = threading.Condition()

	    def write(self, buf):
		with self.condition:
		    self.frame = buf
		    self.condition.notify_all()

	stream_output = StreamingOutput()

	class MJPEGHandler(http_server.BaseHTTPRequestHandler):
	    def do_GET(self):
		if self.path == '/video':
		    self.send_response(200)
		    self.send_header('Age', '0')
		    self.send_header('Cache-Control', 'no-cache, private')
		    self.send_header('Pragma', 'no-cache')
		    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=MJPEG_FRAME')
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
		        pass
		else:
		    self.send_error(404)
		    self.end_headers()

	    def log_message(self, fmt, *args):
		pass

	class ThreadedMJPEGServer(socketserver.ThreadingMixIn, http_server.HTTPServer):
	    allow_reuse_address = True
	    daemon_threads = True

	def start_camera():
	    try:
		from picamera2 import Picamera2
		from picamera2.encoders import JpegEncoder
		from picamera2.outputs import FileOutput
		cam = Picamera2(CONFIG["CAMERA_INDEX"])
		cam.configure(cam.create_video_configuration(
		    main={"size": (CONFIG["CAMERA_WIDTH"], CONFIG["CAMERA_HEIGHT"]), "format": "RGB888"}
		))
		cam.start_recording(JpegEncoder(q=CONFIG["CAMERA_JPEG_QUALITY"]), FileOutput(stream_output))
	    except Exception as e:
		print(f"Camera error: {e}")

	def start_video_server():
	    srv = ThreadedMJPEGServer((CONFIG["VIDEO_HOST"], CONFIG["VIDEO_PORT"]), MJPEGHandler)
	    srv.serve_forever()

	def read_sensors():
	    return {
		"gas": {k: round(random.uniform(0.1, 1.5), 2) for k in ["mq2", "mq4", "mq5", "mq6", "mq7", "mq8"]},
		"env": {"temp": 25.0, "humidity": 50.0, "pm25": 10.0, "moisture": False, "motion": False, "heat_c": 30.0},
		"imu": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0, "ax": 0.0, "ay": 0.0, "az": 9.8},
		"prox": {"front_cm": 100, "floor_cm": 10, "collision": False}
	    }

	laptop_client = None

	async def handle_laptop(websocket):
	    global laptop_client
	    laptop_client = websocket
	    try:
		async for message in websocket:
		    pass
	    finally:
		laptop_client = None

	async def super_loop():
	    while True:
		if laptop_client:
		    data = read_sensors()
		    data["type"] = "sensors"
		    data["ts"] = time.time()
		    try:
		        await laptop_client.send(json.dumps(data))
		    except:
		        pass
		await asyncio.sleep(CONFIG["RATE_MAIN_LOOP"])

	async def main():
	    server = await websockets.serve(handle_laptop, CONFIG["WEBSOCKET_HOST"], CONFIG["WEBSOCKET_PORT"])
	    await asyncio.gather(server.wait_closed(), super_loop())

	if __name__ == "__main__":
	    threading.Thread(target=start_camera, daemon=True).start()
	    threading.Thread(target=start_video_server, daemon=True).start()
	    asyncio.run(main())
	EOF
	sudo chmod +x /home/rpi_node.py
	@echo "Done. The Environment has been setup."
	python3 /home/rpi_node.py
	@echo "Scipt is running"
