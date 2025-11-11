-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table: events
-- Przechowuje wszystkie zdarzenia z pakietów Meshtastic
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    node_id TEXT NOT NULL,
    hex_id TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude INTEGER,
    packet_type TEXT,
    rssi INTEGER,
    snr REAL,
    hop_limit INTEGER,
    topic TEXT,
    raw_payload TEXT
);

-- Konwersja na hypertable (partycjonowanie po czasie)
SELECT create_hypertable('events', 'timestamp', chunk_time_interval => INTERVAL '1 day');

-- Indeksy dla szybkich zapytań
CREATE INDEX idx_events_hex_id ON events (hex_id, timestamp DESC);
CREATE INDEX idx_events_node_id ON events (node_id, timestamp DESC);
CREATE INDEX idx_events_timestamp ON events (timestamp DESC);

-- Table: devices
-- Ostatni znany stan urządzeń
CREATE TABLE devices (
    node_id TEXT PRIMARY KEY,
    last_seen TIMESTAMPTZ NOT NULL,
    last_hex_id TEXT,
    last_latitude DOUBLE PRECISION,
    last_longitude DOUBLE PRECISION,
    last_altitude INTEGER,
    first_seen TIMESTAMPTZ NOT NULL,
    packet_count INTEGER DEFAULT 0
);

CREATE INDEX idx_devices_last_seen ON devices (last_seen DESC);
CREATE INDEX idx_devices_hex_id ON devices (last_hex_id);

-- Table: hex_activity
-- Agregaty aktywności per hex
CREATE TABLE hex_activity (
    hex_id TEXT NOT NULL,
    hour TIMESTAMPTZ NOT NULL,
    unique_nodes INTEGER DEFAULT 0,
    packet_count INTEGER DEFAULT 0,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    PRIMARY KEY (hex_id, hour)
);

-- Konwersja na hypertable
SELECT create_hypertable('hex_activity', 'hour', chunk_time_interval => INTERVAL '7 days');

CREATE INDEX idx_hex_activity_hex_id ON hex_activity (hex_id, hour DESC);

-- Table: traceroutes
-- Krawędzie między hexami (dla visualizacji traceroute)
CREATE TABLE traceroutes (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    source_hex TEXT NOT NULL,
    target_hex TEXT NOT NULL,
    node_id TEXT NOT NULL,
    rssi INTEGER,
    snr REAL,
    hop_count INTEGER
);

-- Konwersja na hypertable
SELECT create_hypertable('traceroutes', 'timestamp', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX idx_traceroutes_source ON traceroutes (source_hex, timestamp DESC);
CREATE INDEX idx_traceroutes_target ON traceroutes (target_hex, timestamp DESC);

-- Retention policy: usuń dane starsze niż 365 dni
SELECT add_retention_policy('events', INTERVAL '365 days');
SELECT add_retention_policy('hex_activity', INTERVAL '365 days');
SELECT add_retention_policy('traceroutes', INTERVAL '365 days');

-- Continuous aggregates dla szybkich zapytań agregacyjnych
-- Agregaty godzinowe
CREATE MATERIALIZED VIEW hex_activity_hourly
WITH (timescaledb.continuous) AS
SELECT
    hex_id,
    time_bucket('1 hour', timestamp) AS hour,
    COUNT(DISTINCT node_id) AS unique_nodes,
    COUNT(*) AS packet_count,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM events
GROUP BY hex_id, hour
WITH NO DATA;

-- Agregaty dzienne
CREATE MATERIALIZED VIEW hex_activity_daily
WITH (timescaledb.continuous) AS
SELECT
    hex_id,
    time_bucket('1 day', timestamp) AS day,
    COUNT(DISTINCT node_id) AS unique_nodes,
    COUNT(*) AS packet_count,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM events
GROUP BY hex_id, day
WITH NO DATA;

-- Refresh policy dla continuous aggregates
SELECT add_continuous_aggregate_policy('hex_activity_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('hex_activity_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO meshuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO meshuser;
