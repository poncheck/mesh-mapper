# Mesh Mapper

Aplikacja webowa do monitorowania i wizualizacji sieci Meshtastic w czasie rzeczywistym. System subskrybuje broker MQTT, dekoduje pakiety Meshtastic, mapuje pozycje urządzeń na heksy H3 i przechowuje historię aktywności.

## Architektura

- **MQTT Worker**: Serwis subskrybujący brokera MQTT, dekodujący pakiety Meshtastic (protobuf/JSON), wyciągający pozycję, node-ID, typ pakietu, mapujący na H3 (rez.8), zapisujący zdarzenia do bazy.
- **Storage/API Backend**: REST API (FastAPI), obsługa zapytań agregacyjnych (per hex, per node, per czas).
- **Frontend**: Interaktywna mapa (React + MapLibre/Leaflet), heatmapa, klastrowanie heksów, lista urządzeń, widok traceroute.
- **Baza danych**: Postgres + TimescaleDB (partycjonowanie po czasie i hex_id, szybkie agregacje).

## Stack technologiczny

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, paho-mqtt, h3-py, protobuf
- **Baza danych**: Postgres + TimescaleDB
- **Frontend**: React + TypeScript, MapLibre GL JS, Material UI
- **Docker Compose**: Orkiestracja wszystkich serwisów

## Aktualny stan projektu

### Etap 1 (MVP) - ✅ Zakończony
- ✅ Worker MQTT odbierający i logujący pakiety z brokera
- ✅ Zapis surowych logów do pliku `logs/mqtt_raw.log`
- ✅ Docker Compose z serwisem mqtt-worker

### Etap 2-5 - ✅ Zakończone
- ✅ Dekodowanie pakietów Meshtastic (protobuf/JSON)
- ✅ Ekstrakcja danych (node-ID, lat/lon, typ pakietu) i mapowanie na H3
- ✅ Baza danych (Postgres + TimescaleDB) z tabelami events, devices, hex_activity, traceroutes
- ✅ Zapis zdekodowanych danych do bazy
- ✅ Continuous aggregates dla szybkich zapytań agregacyjnych

### Etap 6 - ✅ Zakończony
- ✅ Backend API (FastAPI) z pełnym zestawem endpointów REST
- ✅ Wsparcie dla zapytań geospatialnych (GeoJSON)
- ✅ Automatyczna dokumentacja API (Swagger/OpenAPI)
- ✅ Connection pooling i optymalizacje wydajności

### Kolejne etapy
- [ ] Etap 7: Frontend (React + mapa interaktywna)
- [ ] Etap 8: Websockets dla real-time updates
- [ ] Etap 9: Zaawansowane analityki i raporty

## Uruchomienie

### Wymagania
- Docker i Docker Compose
- Dostęp do brokera MQTT z pakietami Meshtastic

### Konfiguracja
Edytuj `docker-compose.yml` i ustaw:
- `MQTT_HOST`: adres IP/hostname brokera MQTT
- `MQTT_PORT`: port brokera (domyślnie 1883)
- `MQTT_TOPIC`: topic do subskrypcji (domyślnie `msh/#`)

### Uruchomienie
```bash
docker compose up --build
```

### Sprawdzenie logów
```bash
tail -f logs/mqtt_raw.log
```

## API Documentation

REST API dostępne na `http://localhost:8000` (po uruchomieniu docker-compose).

### Dokumentacja interaktywna
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Główne endpointy

#### Health & Statistics
- `GET /health` - Health check API i bazy danych
- `GET /api/stats` - Ogólne statystyki sieci (liczba zdarzeń, urządzeń, aktywność 24h)

#### Events (Zdarzenia)
- `GET /api/events` - Lista zdarzeń z filtrami (node_id, hex_id, przedział czasu)
- `GET /api/events/{event_id}` - Szczegóły konkretnego zdarzenia

#### Devices (Urządzenia)
- `GET /api/devices` - Lista wszystkich urządzeń
- `GET /api/devices/{node_id}` - Szczegóły konkretnego urządzenia
- `GET /api/devices/{node_id}/events` - Historia zdarzeń dla urządzenia

#### Hex Activity (Aktywność w heksach H3)
- `GET /api/hexes` - Lista aktywnych heksów
- `GET /api/hexes/{hex_id}/activity` - Statystyki aktywności dla heksa (godzinowe/dzienne)
- `GET /api/hexes/{hex_id}/events` - Zdarzenia w konkretnym heksie

#### Traceroutes
- `GET /api/traceroutes` - Lista traceroute z filtrami

#### Map Visualization (Wizualizacja mapy)
- `GET /api/map/recent` - Ostatnie pozycje urządzeń (GeoJSON FeatureCollection)
- `GET /api/map/heatmap` - Dane do heatmapy aktywności heksów

### Przykłady użycia

#### Pobranie statystyk
```bash
curl http://localhost:8000/api/stats
```

#### Pobranie ostatnich 10 zdarzeń
```bash
curl "http://localhost:8000/api/events?limit=10"
```

#### Pobranie zdarzeń dla konkretnego urządzenia
```bash
curl "http://localhost:8000/api/devices/!abcd1234/events?limit=50"
```

#### Pobranie danych do mapy (ostatnie 24h)
```bash
curl "http://localhost:8000/api/map/recent?hours=24"
```

#### Pobranie aktywności dla heksa (rozdzielczość godzinowa)
```bash
curl "http://localhost:8000/api/hexes/881f1d44c7fffff/activity?resolution=hourly"
```

## Struktura projektu

```
mesh-mapper/
├── api/                  # FastAPI REST API
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── mqtt_worker/          # Worker MQTT
│   ├── Dockerfile
│   ├── requirements.txt
│   └── mqtt_worker.py
├── logs/                 # Logi (gitignore)
├── init.sql              # Schema bazy danych
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Licencja

MIT

## Autor

poncheck
