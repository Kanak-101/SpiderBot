import asyncio
import threading
import json
import websockets
from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── Change these if RPi IP ever changes ──────────────────────────────
RPI_WS_URL    = "ws://192.168.10.1:8765"   # sensor data + commands
RPI_VIDEO_URL = "http://192.168.10.1:8080/video"  # MJPEG stream
# ─────────────────────────────────────────────────────────────────────

rpi_ws_ref = {"ws": None}
event_loop = None


@app.route('/')
def index():
    # Pass video URL to template so it's in one place
    return render_template('index.html', video_url=RPI_VIDEO_URL)


@socketio.on('command')
def on_command(data):
    ws = rpi_ws_ref["ws"]
    if ws and event_loop:
        asyncio.run_coroutine_threadsafe(
            ws.send(json.dumps(data)), event_loop
        )
        print(f"[CMD] Sent to RPi: {data}")
    else:
        print("[!]  Command dropped — RPi not connected")


async def connect_to_rpi():
    while True:
        try:
            print(f"[*]  Connecting to RPi at {RPI_WS_URL}...")
            async with websockets.connect(RPI_WS_URL) as ws:
                rpi_ws_ref["ws"] = ws
                print("[+]  Connected to RPi")
                socketio.emit('rpi_status', {'connected': True})
                async for raw in ws:
                    data = json.loads(raw)
                    socketio.emit('sensor_data', data)
        except Exception as e:
            print(f"[-]  RPi disconnected: {e}. Retrying in 3s...")
            rpi_ws_ref["ws"] = None
            socketio.emit('rpi_status', {'connected': False})
            await asyncio.sleep(3)


def start_rpi_thread():
    global event_loop
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_until_complete(connect_to_rpi())


if __name__ == '__main__':
    threading.Thread(target=start_rpi_thread, daemon=True).start()
    print("[*]  Dashboard at http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)