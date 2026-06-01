# Nepal Traffic AI — Vehicle Recognition & Traffic Data Collection System

An AI-powered checkpoint system for Nepal's Department of Transport Management (DoTM) and Traffic Police. Detects vehicles from RTSP camera feeds using YOLOv8, reads license plates with PaddleOCR (including Devanagari bus route text), classifies ownership from Nepal's plate format, cross-references DoTM registry, and presents everything in a real-time dashboard.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         NEPAL TRAFFIC AI                              │
│                                                                        │
│  ┌─────────────┐    ┌──────────────────────────────────────────────┐  │
│  │  RTSP Cam   │───▶│            BACKEND  (FastAPI)                │  │
│  │  (or mock)  │    │                                              │  │
│  └─────────────┘    │  ┌─────────┐  ┌───────┐  ┌──────────────┐   │  │
│                     │  │ YOLOv8  │  │Paddle │  │  Classifier  │   │  │
│  ┌─────────────┐    │  │detector │  │  OCR  │  │(Nepal plates)│   │  │
│  │  Simulator  │───▶│  └────┬────┘  └───┬───┘  └──────┬───────┘   │  │
│  │  (dev mode) │    │       │           │             │            │  │
│  └─────────────┘    │  ┌────▼───────────▼─────────────▼────────┐  │  │
│                     │  │     VehicleDetection (dataclass)       │  │  │
│                     │  └────────────────────┬───────────────────┘  │  │
│                     │                       │                       │  │
│                     │  ┌────────────────────▼───────────────────┐  │  │
│                     │  │    DoTM Registry Lookup  (mock/API)    │  │  │
│                     │  └────────────────────┬───────────────────┘  │  │
│                     │                       │                       │  │
│                     │  ┌────────────────────▼───────────────────┐  │  │
│                     │  │   AlertEngine  (watchlist / rules)     │  │  │
│                     │  └────────────────────┬───────────────────┘  │  │
│                     │                       │                       │  │
│                     │  ┌────────────────────▼───────────────────┐  │  │
│                     │  │  SQLite / PostgreSQL  (async SQLAlchemy)│  │  │
│                     │  └────────────────────┬───────────────────┘  │  │
│                     │                       │                       │  │
│                     │  ┌────────────────────▼───────────────────┐  │  │
│                     │  │  WebSocket  /ws/live  /ws/alerts       │  │  │
│                     │  └────────────────────┬───────────────────┘  │  │
│                     └───────────────────────│───────────────────────┘  │
│                                             │                           │
│  ┌──────────────────────────────────────────▼───────────────────────┐  │
│  │                    FRONTEND  (Vanilla JS)                         │  │
│  │  Dashboard · Vehicle Log · Analytics · Alerts · Registry · Settings│  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisitse

- Python 3.11+
- pip
- Docker & Docker Compose (optional)
- Node.js (optional — only needed for custom build tooling)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/nepal-traffic-ai.git
cd nepal-traffic-ai

# 2. Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Configure environment
cp .env.example .env    # or use the provided .env

# 5. Seed the database with test data
python -m scripts.seed_database

# 6. Start the backend server
uvicorn backend.main:app --reload --port 8000

# 7. In another terminal, start the camera simulator
python -m scripts.simulate_camera --checkpoint cp-thankot --rate 3

# 8. Open the dashboard
open http://localhost:8000        # served as static files
# or open frontend/index.html directly in your browser
```

---

## Nepal License Plate Format

Nepal uses a structured plate format: `[District Code] [Series] [Letter] [Number]`

| Example                | Meaning                                |
|------------------------|----------------------------------------|
| `Ba 2 Kha 4521`        | Kathmandu, series 2, private vehicle   |
| `Ko 1 Ja 0033`         | Kathmandu (old), private               |
| `La 3 Ga 1122`         | Lalitpur                               |
| `Ka 4 Cha 8899`        | Kaski (Pokhara)                        |
| `Na Pra 2 Ga 0011`     | Nepal Police                           |
| `Na Se 1 Ka 0055`      | Nepal Army                             |
| `Sa Pra 3 Ba 0099`     | Armed Police Force                     |
| `Na Ra Sa 4 Ka 0001`   | Government of Nepal (civil service)    |
| `CD 82 1234`           | Diplomatic Corps                       |
| `UN 12 5678`           | United Nations                         |
| `NGO Ba 1 Ka 0001`     | NGO vehicle                            |

**Yellow background** → public/commercial vehicle
**Green background**  → electric vehicle
**White background**  → private vehicle

District codes (partial list):

| Code | City/District       |
|------|---------------------|
| Ba   | Kathmandu           |
| Ko   | Kathmandu (old)     |
| Me   | Kathmandu Metro     |
| La   | Lalitpur            |
| Bha  | Bhaktapur           |
| Ka   | Pokhara (Kaski)     |
| Chi  | Bharatpur (Chitwan) |
| Mo   | Biratnagar (Morang) |
| Pa   | Birgunj (Parsa)     |
| Ra   | Rupandehi/Butwal    |
| Su   | Dharan (Sunsari)    |
| Dha  | Janakpur (Dhanusa)  |

---

## Running with Real Cameras

Add RTSP URLs to your `.env`:

```env
CAMERA_SOURCES=rtsp://admin:pass@192.168.1.10:554/stream1,rtsp://admin:pass@192.168.1.11:554/stream1
MOCK_MODE=false
CONFIDENCE_THRESHOLD=0.70
```

For each camera, the detector will:
1. Capture frames continuously
2. Run YOLOv8 inference on each frame
3. Crop vehicle bounding boxes
4. Run real OCR on the plate region (EasyOCR by default — see below)
5. Run Devanagari OCR on bus fronts
6. Classify ownership from plate text
7. Cross-reference DoTM registry
8. Run alert engine
9. Stream results over WebSocket to dashboard

---

## License Plate OCR

Plate and Devanagari route reading is handled by `backend/services/ocr.py`,
which supports three engines selected via the `OCR_ENGINE` setting:

| `OCR_ENGINE` | Behaviour |
|--------------|-----------|
| `easyocr`    | **Real OCR (default for real mode).** Uses EasyOCR on PyTorch (Apple MPS / CUDA / CPU). Reuses the torch install ultralytics already needs; works on Python 3.13. |
| `paddle`     | Real OCR via PaddleOCR (optional, heavier — see `requirements-ml.txt`). |
| `mock`       | Synthetic plate/route text — no models required (default when `MOCK_MODE=true`). |
| *(empty)*    | Auto: `mock` when `MOCK_MODE=true`, otherwise `easyocr`. |

```bash
# Install the real OCR engine
pip install -r backend/requirements-ml.txt   # EasyOCR

# Run the video processor with real plate reading on a recorded file
python -m scripts.process_video --source "Road traffic video for object recognition.mp4" \
    --skip-frames 5 --save-output annotated.mp4

# Force mock OCR (fast, no models) regardless of mode
python -m scripts.process_video --source traffic.mp4 --mock-ocr
```

Relevant `.env` knobs:

```env
OCR_ENGINE=easyocr        # easyocr | paddle | mock | (empty for auto)
OCR_GPU=true              # use Apple MPS / CUDA when available
OCR_PLATE_LANGS=en        # EasyOCR languages for plates
OCR_ROUTE_LANGS=ne,en     # EasyOCR languages for Devanagari bus routes
OCR_MIN_CONF=0.30         # drop OCR tokens below this confidence
```

> **Note on the bundled demo clip:** `Road traffic video for object recognition.mp4`
> is 640×360 footage where vehicles are only ~20–30 px wide, so plates are not
> physically legible to *any* OCR engine. Plate reading is verified instead by
> `tests/test_ocr_real.py`, which runs the real EasyOCR engine on rendered
> plate images. For real plate reads, use higher-resolution checkpoint cameras
> where the plate occupies a meaningful pixel area.

---

## API Reference

### Vehicle Endpoints

```bash
# Ingest a new vehicle detection (from camera or simulator)
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"plate_text":"Ba 2 Kha 4521","vehicle_type":"car","ownership_category":"private","direction":"inbound","checkpoint_id":"cp-thankot","plate_confidence":0.92}'

# List vehicles (with filters)
curl "http://localhost:8000/api/vehicles?checkpoint_id=cp-thankot&type=bus&limit=50"

# Search by plate text
curl "http://localhost:8000/api/vehicles/search?plate=Ba%202%20Kha"

# Get single vehicle
curl http://localhost:8000/api/vehicles/{id}

# DoTM registry lookup
curl "http://localhost:8000/api/dotm/Ba%202%20Kha%204521"
```

### Stats Endpoints

```bash
# Today's summary
curl "http://localhost:8000/api/stats/summary?checkpoint_id=cp-thankot"

# Hourly counts (last 24 hours)
curl "http://localhost:8000/api/stats/hourly?hours=24"

# Top 15 origin cities
curl "http://localhost:8000/api/stats/origin?days=7"
```

### Alert Endpoints

```bash
# List active alerts
curl "http://localhost:8000/api/alerts?resolved=false"

# Resolve an alert
curl -X PATCH "http://localhost:8000/api/alerts/{id}/resolve"
```

### Report Endpoints

```bash
# Daily report JSON
curl "http://localhost:8000/api/reports/daily?date=2024-01-15"

# Export CSV
curl -O "http://localhost:8000/api/reports/export/csv?checkpoint_id=cp-thankot"

# Export PDF
curl -O "http://localhost:8000/api/reports/export/pdf?date=2024-01-15"
```

### WebSocket

```javascript
// Live vehicle feed
const ws = new WebSocket("ws://localhost:8000/ws/live/cp-thankot");
ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  if (type === "sighting") console.log(data.plate_text);
};

// Live alerts
const wsAlerts = new WebSocket("ws://localhost:8000/ws/alerts/cp-thankot");
```

OpenAPI docs: http://localhost:8000/docs

---

## ML Model Training

### 1. Prepare Dataset

```bash
# Generate synthetic plate images for initial training
python -m ml.dataset_prep --action synthetic --count 500

# Create YOLO dataset structure
python -m ml.dataset_prep --action structure

# Split raw images into train/val
python -m ml.dataset_prep --action split --source ./data/raw_images
```

### 2. Train YOLOv8 Vehicle Detector

```bash
# Fine-tune on Nepal vehicles dataset
python -m ml.train_detector --epochs 100 --imgsz 640 --batch 16 --device 0

# Best model saved to ./models/vehicle_detector.pt
```

### 3. Train PaddleOCR

```bash
# Train plate OCR (English) and route OCR (Devanagari)
python -m ml.train_ocr --task both --epochs 30

# Place training data in:
#   ./data/plates/      (plate images + labels.txt)
#   ./data/route_text/  (bus route images + labels.txt)
```

### 4. Evaluate

```bash
python -m ml.evaluate --mock
# Report saved to ./reports/evaluation_report.txt
```

---

## Docker Deployment

```bash
# Build and start all services
docker-compose up --build -d

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs

# View logs
docker-compose logs -f backend

# Seed the database in container
docker-compose exec backend python -m scripts.seed_database

# Stop
docker-compose down
```

---

## Raspberry Pi 5 / NVIDIA Jetson Nano Deployment

### Raspberry Pi 5 (edge node, no GPU)

```bash
# Install system deps
sudo apt-get install -y libgl1 libglib2.0-0 python3.11 python3.11-venv

# Clone and install
git clone https://github.com/your-org/nepal-traffic-ai.git
cd nepal-traffic-ai
python3.11 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt

# Use MOCK_MODE=false with real camera
# Set CONFIDENCE_THRESHOLD=0.60 for lower-powered hardware
echo "MOCK_MODE=false" >> .env
echo "CONFIDENCE_THRESHOLD=0.60" >> .env

# Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### NVIDIA Jetson Nano (GPU inference)

```bash
# Install JetPack 4.6+ (includes CUDA, cuDNN, TensorRT)
# Then install ultralytics with CUDA support
pip install ultralytics torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Export YOLOv8 to TensorRT for faster inference
python3 -c "
from ultralytics import YOLO
model = YOLO('./models/vehicle_detector.pt')
model.export(format='engine', device=0, half=True)
"

# Update config to use TensorRT model
echo "CONFIDENCE_THRESHOLD=0.65" >> .env
```

For both edge devices:
- Configure RTSP URLs in `.env` from your IP cameras
- Enable systemd service for auto-start on boot
- Mount an external SSD for database and image storage
- Set up SSH tunneling or VPN for remote monitoring

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests: `pytest tests/ -v`
4. Commit: `git commit -m "feat: add my feature"`
5. Push and open a Pull Request

### Code Standards
- Python 3.11+, type hints throughout
- Async SQLAlchemy for all DB operations
- Pydantic v2 schemas for all API I/O
- Tests for all new services and endpoints

### Adding a New Checkpoint
1. Add via the Settings page in the dashboard, or:
2. `POST /api/checkpoints` with name, location, lat, lng, camera_sources
3. Add the RTSP URL to `CAMERA_SOURCES` in `.env`

---

## License

MIT License — Department of Transport Management, Nepal
For official deployment, contact DoTM at https://dotm.gov.np
