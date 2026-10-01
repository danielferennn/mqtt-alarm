import os

import paho.mqtt.client as mqtt


BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
TOPIC = "security/#"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Unit alarm terhubung ke broker", flush=True)
        client.subscribe(TOPIC, qos=2)
        print(f"[SUBSCRIBE] {TOPIC}", flush=True)
    else:
        print(f"[MQTT] Koneksi gagal. rc={rc}", flush=True)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    normalized = payload.casefold()
    print(
        f"[MESSAGE] topic={msg.topic} | qos={msg.qos} | "
        f"retain={msg.retain} | payload={payload}",
        flush=True,
    )

    if msg.topic == "security/asap" and normalized in {
        "terdeteksi",
        "detected",
        "asap terdeteksi",
        "smoke detected",
    }:
        print(f"ALERT: asap terdeteksi ({msg.topic})", flush=True)
    elif msg.topic in {"security/pintu/status", "security/asap/status"} and normalized == "offline":
        sensor = "pintu" if msg.topic == "security/pintu/status" else "asap"
        print(f"ALERT: sensor {sensor} offline ({msg.topic})", flush=True)


client = mqtt.Client(client_id="mqtt-alarm", clean_session=True)
client.on_connect = on_connect
client.on_message = on_message

print(f"[MQTT] Menghubungkan unit alarm ke {BROKER_HOST}:{BROKER_PORT}", flush=True)
client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
client.loop_forever()
