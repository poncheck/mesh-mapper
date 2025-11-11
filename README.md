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

### Kolejne etapy
- [ ] Etap 2: Dekodowanie pakietów Meshtastic (protobuf/JSON)
- [ ] Etap 3: Ekstrakcja danych (node-ID, lat/lon, typ pakietu) i mapowanie na H3
- [ ] Etap 4: Przygotowanie bazy danych (Postgres + TimescaleDB)
- [ ] Etap 5: Zapis zdekodowanych danych do bazy
- [ ] Etap 6: Backend API (FastAPI)
- [ ] Etap 7: Frontend (React + mapa interaktywna)

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

## Struktura projektu

```
mesh-mapper/
├── mqtt_worker/          # Worker MQTT
│   ├── Dockerfile
│   ├── requirements.txt
│   └── mqtt_worker.py
├── logs/                 # Logi (gitignore)
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Licencja

MIT

## Autor

poncheck
