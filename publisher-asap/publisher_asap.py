import os
import time

import paho.mqtt.client as mqtt


BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
INTERVAL_SECONDS = float(os.getenv("INTERVAL_SECONDS", "5"))
PUBLISH_TIMEOUT_SECONDS = float(os.getenv("PUBLISH_TIMEOUT_SECONDS", "5"))
ASAP_STATUS = os.getenv("ASAP_STATUS", "aman").strip().lower()
if ASAP_STATUS not in {"aman", "terdeteksi"}:
    raise ValueError("ASAP_STATUS harus 'aman' atau 'terdeteksi'")

TOPIC = "security/asap"
STATUS_TOPIC = f"{TOPIC}/status"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Publisher asap terhubung ke broker", flush=True)
        client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
        print(f"[STATUS] {STATUS_TOPIC} -> online", flush=True)
    else:
        print(f"[MQTT] Koneksi gagal. rc={rc}", flush=True)


client = mqtt.Client(client_id="publisher-asap")
client.on_connect = on_connect

# Will dikirim broker jika koneksi terputus tanpa DISCONNECT yang normal.
client.will_set(STATUS_TOPIC, payload="offline", qos=1, retain=True)

print(f"[MQTT] Menghubungkan ke {BROKER_HOST}:{BROKER_PORT}", flush=True)
client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
client.loop_start()

try:
    while True:
        try:
            info = client.publish(TOPIC, ASAP_STATUS, qos=2, retain=False)
            info.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
            print(f"[PUBLISH] {TOPIC} -> {ASAP_STATUS} (QoS 2)", flush=True)
        except (RuntimeError, ValueError) as exc:
            # Koneksi putus di tengah publish; loop paho akan menyambung ulang.
            print(f"[WARN] Gagal publish {TOPIC} -> {ASAP_STATUS}: {exc}", flush=True)
        time.sleep(INTERVAL_SECONDS)
except KeyboardInterrupt:
    print("[MQTT] Publisher asap dihentikan", flush=True)
finally:
    client.loop_stop()
    client.disconnect()
