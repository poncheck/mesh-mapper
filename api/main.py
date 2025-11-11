from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel
import asyncpg
import os
from contextlib import asynccontextmanager

# Pydantic models for API responses
class Event(BaseModel):
    id: int
    timestamp: datetime
    node_id: str
    hex_id: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[int]
    packet_type: Optional[str]
    rssi: Optional[int]
    snr: Optional[float]
    hop_limit: Optional[int]
    topic: Optional[str]
    raw_payload: Optional[str]

class Device(BaseModel):
    node_id: str
    last_seen: datetime
    last_hex_id: Optional[str]
    last_latitude: Optional[float]
    last_longitude: Optional[float]
    last_altitude: Optional[int]
    first_seen: datetime
    packet_count: int

class HexActivity(BaseModel):
    hex_id: str
    hour: datetime
    unique_nodes: int
    packet_count: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]

class Traceroute(BaseModel):
    id: int
    timestamp: datetime
    source_hex: str
    target_hex: str
    node_id: str
    rssi: Optional[int]
    snr: Optional[float]
    hop_count: Optional[int]

class Stats(BaseModel):
    total_events: int
    total_devices: int
    total_hexes: int
    active_devices_24h: int
    events_24h: int

# Database connection pool
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=os.getenv('POSTGRES_HOST', 'timescaledb'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        database=os.getenv('POSTGRES_DB', 'meshmap'),
        user=os.getenv('POSTGRES_USER', 'meshuser'),
        password=os.getenv('POSTGRES_PASSWORD', 'meshpass'),
        min_size=5,
        max_size=20
    )
    yield
    # Shutdown
    await db_pool.close()

# FastAPI app
app = FastAPI(
    title="Mesh Mapper API",
    description="REST API for Meshtastic mesh network monitoring and analysis",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Check API and database health"""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval('SELECT 1')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")

# Statistics endpoint
@app.get("/api/stats", response_model=Stats)
async def get_stats():
    """Get overall network statistics"""
    async with db_pool.acquire() as conn:
        total_events = await conn.fetchval('SELECT COUNT(*) FROM events')
        total_devices = await conn.fetchval('SELECT COUNT(*) FROM devices')
        total_hexes = await conn.fetchval('SELECT COUNT(DISTINCT hex_id) FROM events')
        
        last_24h = datetime.utcnow() - timedelta(hours=24)
        active_devices_24h = await conn.fetchval(
            'SELECT COUNT(DISTINCT node_id) FROM events WHERE timestamp > $1',
            last_24h
        )
        events_24h = await conn.fetchval(
            'SELECT COUNT(*) FROM events WHERE timestamp > $1',
            last_24h
        )
        
        return Stats(
            total_events=total_events or 0,
            total_devices=total_devices or 0,
            total_hexes=total_hexes or 0,
            active_devices_24h=active_devices_24h or 0,
            events_24h=events_24h or 0
        )

# Events endpoints
@app.get("/api/events", response_model=List[Event])
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    node_id: Optional[str] = None,
    hex_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get events with optional filters"""
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    param_count = 0
    
    if node_id:
        param_count += 1
        query += f" AND node_id = ${param_count}"
        params.append(node_id)
    
    if hex_id:
        param_count += 1
        query += f" AND hex_id = ${param_count}"
        params.append(hex_id)
    
    if start_time:
        param_count += 1
        query += f" AND timestamp >= ${param_count}"
        params.append(start_time)
    
    if end_time:
        param_count += 1
        query += f" AND timestamp <= ${param_count}"
        params.append(end_time)
    
    query += " ORDER BY timestamp DESC"
    query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, offset])
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [Event(**dict(row)) for row in rows]

@app.get("/api/events/{event_id}", response_model=Event)
async def get_event(event_id: int):
    """Get a specific event by ID"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM events WHERE id = $1', event_id)
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        return Event(**dict(row))

# Devices endpoints
@app.get("/api/devices", response_model=List[Device])
async def get_devices(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    active_since: Optional[datetime] = None
):
    """Get all devices with optional activity filter"""
    query = "SELECT * FROM devices WHERE 1=1"
    params = []
    
    if active_since:
        query += " AND last_seen >= $1"
        params.append(active_since)
    
    query += " ORDER BY last_seen DESC"
    query += f" LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
    params.extend([limit, offset])
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [Device(**dict(row)) for row in rows]

@app.get("/api/devices/{node_id}", response_model=Device)
async def get_device(node_id: str):
    """Get a specific device by node_id"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM devices WHERE node_id = $1', node_id)
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        return Device(**dict(row))

@app.get("/api/devices/{node_id}/events", response_model=List[Event])
async def get_device_events(
    node_id: str,
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get all events for a specific device"""
    query = "SELECT * FROM events WHERE node_id = $1"
    params = [node_id]
    
    if start_time:
        query += " AND timestamp >= $2"
        params.append(start_time)
        if end_time:
            query += " AND timestamp <= $3"
            params.append(end_time)
    elif end_time:
        query += " AND timestamp <= $2"
        params.append(end_time)
    
    query += " ORDER BY timestamp DESC"
    query += f" LIMIT ${len(params) + 1}"
    params.append(limit)
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [Event(**dict(row)) for row in rows]

# Hex activity endpoints
@app.get("/api/hexes", response_model=List[str])
async def get_active_hexes(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get list of active hexes in time range"""
    query = "SELECT DISTINCT hex_id FROM events WHERE 1=1"
    params = []
    
    if start_time:
        query += " AND timestamp >= $1"
        params.append(start_time)
        if end_time:
            query += " AND timestamp <= $2"
            params.append(end_time)
    elif end_time:
        query += " AND timestamp <= $1"
        params.append(end_time)
    
    query += " ORDER BY hex_id"
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [row['hex_id'] for row in rows]

@app.get("/api/hexes/{hex_id}/activity", response_model=List[HexActivity])
async def get_hex_activity(
    hex_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    resolution: str = Query("hourly", regex="^(hourly|daily)$")
):
    """Get activity statistics for a specific hex"""
    view = "hex_activity_hourly" if resolution == "hourly" else "hex_activity_daily"
    time_col = "hour" if resolution == "hourly" else "day"
    
    query = f"SELECT hex_id, {time_col} as hour, unique_nodes, packet_count, first_seen, last_seen FROM {view} WHERE hex_id = $1"
    params = [hex_id]
    
    if start_time:
        query += f" AND {time_col} >= $2"
        params.append(start_time)
        if end_time:
            query += f" AND {time_col} <= $3"
            params.append(end_time)
    elif end_time:
        query += f" AND {time_col} <= $2"
        params.append(end_time)
    
    query += f" ORDER BY {time_col} DESC"
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [HexActivity(**dict(row)) for row in rows]

@app.get("/api/hexes/{hex_id}/events", response_model=List[Event])
async def get_hex_events(
    hex_id: str,
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get all events for a specific hex"""
    query = "SELECT * FROM events WHERE hex_id = $1"
    params = [hex_id]
    
    if start_time:
        query += " AND timestamp >= $2"
        params.append(start_time)
        if end_time:
            query += " AND timestamp <= $3"
            params.append(end_time)
    elif end_time:
        query += " AND timestamp <= $2"
        params.append(end_time)
    
    query += " ORDER BY timestamp DESC"
    query += f" LIMIT ${len(params) + 1}"
    params.append(limit)
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [Event(**dict(row)) for row in rows]

# Traceroute endpoints
@app.get("/api/traceroutes", response_model=List[Traceroute])
async def get_traceroutes(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    source_hex: Optional[str] = None,
    target_hex: Optional[str] = None,
    node_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get traceroutes with optional filters"""
    query = "SELECT * FROM traceroutes WHERE 1=1"
    params = []
    param_count = 0
    
    if source_hex:
        param_count += 1
        query += f" AND source_hex = ${param_count}"
        params.append(source_hex)
    
    if target_hex:
        param_count += 1
        query += f" AND target_hex = ${param_count}"
        params.append(target_hex)
    
    if node_id:
        param_count += 1
        query += f" AND node_id = ${param_count}"
        params.append(node_id)
    
    if start_time:
        param_count += 1
        query += f" AND timestamp >= ${param_count}"
        params.append(start_time)
    
    if end_time:
        param_count += 1
        query += f" AND timestamp <= ${param_count}"
        params.append(end_time)
    
    query += " ORDER BY timestamp DESC"
    query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, offset])
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [Traceroute(**dict(row)) for row in rows]

# Geospatial query endpoints
@app.get("/api/map/recent")
async def get_recent_map_data(
    hours: int = Query(24, ge=1, le=168)
):
    """Get recent device positions for map visualization"""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    async with db_pool.acquire() as conn:
        query = """
            SELECT DISTINCT ON (node_id)
                node_id,
                hex_id,
                latitude,
                longitude,
                altitude,
                timestamp,
                packet_type
            FROM events
            WHERE timestamp > $1
                AND latitude IS NOT NULL
                AND longitude IS NOT NULL
            ORDER BY node_id, timestamp DESC
        """
        rows = await conn.fetch(query, since)
        
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [row['longitude'], row['latitude']]
                    },
                    "properties": {
                        "node_id": row['node_id'],
                        "hex_id": row['hex_id'],
                        "altitude": row['altitude'],
                        "timestamp": row['timestamp'].isoformat(),
                        "packet_type": row['packet_type']
                    }
                }
                for row in rows
            ]
        }

@app.get("/api/map/heatmap")
async def get_heatmap_data(
    hours: int = Query(24, ge=1, le=168)
):
    """Get hex activity data for heatmap visualization"""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    async with db_pool.acquire() as conn:
        query = """
            SELECT 
                hex_id,
                COUNT(*) as event_count,
                COUNT(DISTINCT node_id) as unique_nodes
            FROM events
            WHERE timestamp > $1
            GROUP BY hex_id
            ORDER BY event_count DESC
        """
        rows = await conn.fetch(query, since)
        
        return [
            {
                "hex_id": row['hex_id'],
                "event_count": row['event_count'],
                "unique_nodes": row['unique_nodes']
            }
            for row in rows
        ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
