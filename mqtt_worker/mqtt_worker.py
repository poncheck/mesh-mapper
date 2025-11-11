import os
import time
import json
import h3
import asyncio
import asyncpg
import paho.mqtt.client as mqtt
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2
from datetime import datetime

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.88.30")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "msh/#")
LOG_PATH = os.getenv("LOG_PATH", "/logs/mqtt_raw.log")
DECODED_LOG_PATH = os.getenv("DECODED_LOG_PATH", "/logs/mqtt_decoded.log")
HEX_EVENTS_PATH = os.getenv("HEX_EVENTS_PATH", "/logs/hex_events.jsonl")
H3_RESOLUTION = int(os.getenv("H3_RESOLUTION", "8"))

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meshuser:meshpass@db:5432/meshmapper")
db_pool = None

def format_node_id(node_id_int):
    """Convert node ID integer to !xxxxxxxx format"""
    if not node_id_int:
        return None
    # Remove leading 0x and add ! prefix
    return f"!{node_id_int:08x}"

def decode_protobuf_packet(payload):
    """Dekoduje pakiet protobuf Meshtastic"""
    try:
        service_envelope = mqtt_pb2.ServiceEnvelope()
        service_envelope.ParseFromString(payload)
        
        packet = service_envelope.packet
        
        # Get node_id from packet.from_node or from ServiceEnvelope fields
        node_id = None
        
        # First try packet.from_node
        if packet.from_node and packet.from_node != 0:
            node_id = format_node_id(packet.from_node)
        else:
            # Get gateway_id from ServiceEnvelope fields
            fields = service_envelope.ListFields()
            print(f"🔍 Fields count: {len(fields)}")
            for idx, (field_desc, value) in enumerate(fields):
                print(f"  [{idx}] {field_desc.name} = {value if not isinstance(value, bytes) else '<bytes>'}")
                
            if len(fields) >= 3:
                # Field 2 should be gateway_id
                gateway_id = fields[2][1]
                print(f"  ✅ Field[2] value: {gateway_id}, type: {type(gateway_id)}")
                if gateway_id and isinstance(gateway_id, str) and gateway_id.startswith('!'):
                    node_id = gateway_id
                    print(f"  ✅ Using gateway_id: {node_id}")
        
        if not node_id:
            print(f"❌ No node_id found!")
            return {"error": "from_node"}
        
        decoded = {
            "id": packet.id if packet.id else None,
            "from": node_id,
            "to": format_node_id(packet.to_node) if packet.to_node else None,
            "channel": packet.channel,
            "rx_time": packet.rx_time if packet.rx_time else None,
            "rx_snr": packet.rx_snr if packet.HasField("rx_snr") else None,
            "rx_rssi": packet.rx_rssi if packet.HasField("rx_rssi") else None,
            "hop_limit": packet.hop_limit if packet.hop_limit else None,
            "hop_start": packet.hop_start if packet.hop_start else None,
            "want_ack": packet.want_ack if packet.want_ack else False,
        }
        
        # Dekodowanie payload w zależności od port_num
        if packet.HasField("decoded"):
            decoded["port_num"] = packet.decoded.portnum
            
            # Position data
            if packet.decoded.portnum == portnums_pb2.POSITION_APP:
                try:
                    pos = mesh_pb2.Position()
                    pos.ParseFromString(packet.decoded.payload)
                    lat = pos.latitude_i * 1e-7 if pos.latitude_i else None
                    lon = pos.longitude_i * 1e-7 if pos.longitude_i else None
                    
                    if lat and lon and lat != 0 and lon != 0:
                        decoded["position"] = {
                            "latitude": lat,
                            "longitude": lon,
                            "altitude": pos.altitude if pos.altitude else None,
                            "time": pos.time if pos.time else None,
                        }
                except Exception as e:
                    print(f"⚠️ Position decode error: {e}")
            
            # Telemetry data
            elif packet.decoded.portnum == portnums_pb2.TELEMETRY_APP:
                try:
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
                except Exception as e:
                    print(f"⚠️ Telemetry decode error: {e}")
            
            # Text message
            elif packet.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
                try:
                    decoded["text"] = packet.decoded.payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"⚠️ Text decode error: {e}")
        
        return decoded
    except Exception as e:
        return {"error": f"Error parsing message: {str(e)}"}

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

async def init_db():
    """Initialize database connection pool with retry logic"""
    global db_pool
    max_retries = 5
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, timeout=10)
            print("✅ Database connection pool initialized")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                print(f"   Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print(f"❌ Failed to connect to database after {max_retries} attempts")
                print(f"   Worker will continue without database support (file logging only)")
                db_pool = None

async def save_event_to_db(event):
    """Save event to database"""
    try:
        async with db_pool.acquire() as conn:
            # Insert event
            await conn.execute('''
                INSERT INTO events (
                    timestamp, node_id, hex_id, latitude, longitude, 
                    altitude, packet_type, rssi, snr, hop_limit, topic, raw_payload
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ''', 
                datetime.fromtimestamp(event['timestamp']),
                event['node_id'],
                event['hex_id'],
                event.get('latitude'),
                event.get('longitude'),
                event.get('altitude'),
                str(event.get('packet_type')),
                event.get('rssi'),
                event.get('snr'),
                event.get('hop_limit'),
                event.get('topic'),
                event.get('raw_payload')
            )
            
            # Update or insert device
            await conn.execute('''
                INSERT INTO devices (
                    node_id, last_seen, last_hex_id, last_latitude, 
                    last_longitude, last_altitude, first_seen, packet_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $2, 1)
                ON CONFLICT (node_id) DO UPDATE SET
                    last_seen = EXCLUDED.last_seen,
                    last_hex_id = EXCLUDED.last_hex_id,
                    last_latitude = EXCLUDED.last_latitude,
                    last_longitude = EXCLUDED.last_longitude,
                    last_altitude = EXCLUDED.last_altitude,
                    packet_count = devices.packet_count + 1
            ''',
                event['node_id'],
                datetime.fromtimestamp(event['timestamp']),
                event['hex_id'],
                event.get('latitude'),
                event.get('longitude'),
                event.get('altitude')
            )
            
    except Exception as e:
        print(f"⚠️ Database save error: {e}")

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    timestamp_unix = int(time.time())
    
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
        
        # Mapowanie na H3 i zapis zdarzenia per hex
        if "position" in decoded and decoded["position"].get("latitude") and decoded["position"].get("longitude"):
            lat = decoded["position"]["latitude"]
            lon = decoded["position"]["longitude"]
            
            # Konwersja lat/lon na hex H3
            try:
                hex_id = h3.geo_to_h3(lat, lon, H3_RESOLUTION)
                
                # Utworzenie strukturalnego zdarzenia
                event = {
                    "timestamp": timestamp_unix,
                    "timestamp_iso": ts,
                    "node_id": decoded.get("from"),
                    "hex_id": hex_id,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": decoded["position"].get("altitude"),
                    "packet_type": decoded.get("port_num", "unknown"),
                    "rssi": decoded.get("rx_rssi"),
                    "snr": decoded.get("rx_snr"),
                    "hop_limit": decoded.get("hop_limit"),
                    "topic": msg.topic,
                    "raw_payload": payload_hex,
                }
                
                # Zapis do pliku hex_events.jsonl (JSON Lines - każda linia to osobny JSON)
                os.makedirs(os.path.dirname(HEX_EVENTS_PATH), exist_ok=True)
                with open(HEX_EVENTS_PATH, "a") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
                
                # Zapis do bazy danych (async)
                if db_pool:
                    asyncio.create_task(save_event_to_db(event))
                
                # Wydruk na konsoli
                print(f"📍 {decoded.get('from')} @ {lat:.6f},{lon:.6f} → H3: {hex_id}")
                
            except Exception as e:
                print(f"⚠️  H3 mapping error: {e}")

async def mqtt_loop():
    """Main MQTT loop with async support"""
    # Initialize database first
    await init_db()
    
    # Setup MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    print(f"🚀 Starting MQTT worker, subscribing to {MQTT_TOPIC} on {MQTT_HOST}:{MQTT_PORT}")
    
    # Run MQTT loop in background
    client.loop_start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        client.loop_stop()
        if db_pool:
            await db_pool.close()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(DECODED_LOG_PATH), exist_ok=True)
    asyncio.run(mqtt_loop())
