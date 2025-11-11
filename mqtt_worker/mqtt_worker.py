import os
import time
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.88.30")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "msh/#")
LOG_PATH = os.getenv("LOG_PATH", "/logs/mqtt_raw.log")

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    payload_hex = msg.payload.hex()
    log_line = f"{ts} {msg.topic} {payload_hex}\n"
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(log_line)

if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()
