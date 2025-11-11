import os
import time
import json
import paho.mqtt.client as mqtt
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.88.30")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "msh/#")
LOG_PATH = os.getenv("LOG_PATH", "/logs/mqtt_raw.log")
DECODED_LOG_PATH = os.getenv("DECODED_LOG_PATH", "/logs/mqtt_decoded.log")

def decode_protobuf_packet(payload):
    """Dekoduje pakiet protobuf Meshtastic"""
    try:
        service_envelope = mqtt_pb2.ServiceEnvelope()
        service_envelope.ParseFromString(payload)
        
        packet = service_envelope.packet
        decoded = {
            "id": packet.id,
            "from": hex(packet.from_node) if packet.from_node else None,
            "to": hex(packet.to_node) if packet.to_node else None,
            "channel": packet.channel,
            "rx_time": packet.rx_time,
            "rx_snr": packet.rx_snr if packet.HasField("rx_snr") else None,
            "rx_rssi": packet.rx_rssi if packet.HasField("rx_rssi") else None,
            "hop_limit": packet.hop_limit,
            "want_ack": packet.want_ack,
        }
        
        # Dekodowanie payload w zależności od port_num
        if packet.HasField("decoded"):
            decoded["port_num"] = packet.decoded.portnum
            
            # Position data
            if packet.decoded.portnum == portnums_pb2.POSITION_APP:
                pos = mesh_pb2.Position()
                pos.ParseFromString(packet.decoded.payload)
                decoded["position"] = {
                    "latitude": pos.latitude_i * 1e-7 if pos.latitude_i else None,
                    "longitude": pos.longitude_i * 1e-7 if pos.longitude_i else None,
                    "altitude": pos.altitude if pos.altitude else None,
                    "time": pos.time if pos.time else None,
                }
            
            # Telemetry data
            elif packet.decoded.portnum == portnums_pb2.TELEMETRY_APP:
                telemetry = telemetry_pb2.Telemetry()
                telemetry.ParseFromString(packet.decoded.payload)
                decoded["telemetry"] = {
                    "time": telemetry.time if telemetry.time else None,
                }
                if telemetry.HasField("device_metrics"):
                    decoded["telemetry"]["device_metrics"] = {
                        "battery_level": telemetry.device_metrics.battery_level,
                        "voltage": telemetry.device_metrics.voltage,
                        "channel_utilization": telemetry.device_metrics.channel_utilization,
                        "air_util_tx": telemetry.device_metrics.air_util_tx,
                    }
            
            # Text message
            elif packet.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
                decoded["text"] = packet.decoded.payload.decode('utf-8', errors='ignore')
        
        return decoded
    except Exception as e:
        return {"error": str(e)}

def decode_json_packet(payload):
    """Dekoduje pakiet JSON Meshtastic"""
    try:
        data = json.loads(payload)
        decoded = {
            "id": data.get("id"),
            "from": data.get("from"),
            "to": data.get("to"),
            "channel": data.get("channel"),
            "type": data.get("type"),
            "sender": data.get("sender"),
            "timestamp": data.get("timestamp"),
            "rssi": data.get("rssi"),
            "snr": data.get("snr"),
            "hop_limit": data.get("hop_limit"),
            "hop_start": data.get("hop_start"),
            "hops_away": data.get("hops_away"),
        }
        
        # Position data w JSON
        if "latitude" in data and "longitude" in data:
            decoded["position"] = {
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "altitude": data.get("altitude"),
            }
        
        return decoded
    except Exception as e:
        return {"error": str(e)}

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    
    # Logowanie surowego pakietu (hex)
    payload_hex = msg.payload.hex()
    log_line = f"{ts} {msg.topic} {payload_hex}\n"
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(log_line)
    
    # Dekodowanie pakietu
    decoded = None
    if "/json/" in msg.topic:
        decoded = decode_json_packet(msg.payload)
    elif "/e/" in msg.topic or "/c/" in msg.topic:
        decoded = decode_protobuf_packet(msg.payload)
    
    # Logowanie zdekodowanego pakietu
    if decoded:
        decoded_line = f"{ts} {msg.topic} {json.dumps(decoded, ensure_ascii=False)}\n"
        os.makedirs(os.path.dirname(DECODED_LOG_PATH), exist_ok=True)
        with open(DECODED_LOG_PATH, "a") as f:
            f.write(decoded_line)
        
        # Wydruk na konsoli jeśli pakiet zawiera pozycję
        if "position" in decoded and decoded["position"].get("latitude"):
            print(f"📍 Position: {decoded.get('from')} at {decoded['position']['latitude']:.6f}, {decoded['position']['longitude']:.6f}")

if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(DECODED_LOG_PATH), exist_ok=True)
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    print(f"🚀 Starting MQTT worker, subscribing to {MQTT_TOPIC} on {MQTT_HOST}:{MQTT_PORT}")
    client.loop_forever()
