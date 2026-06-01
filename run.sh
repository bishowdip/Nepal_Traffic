#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Nepal Traffic AI — Complete Setup & Run Script
# ═══════════════════════════════════════════════════════════════════════════════
#
# USAGE:
#   chmod +x run.sh          # make executable (first time only)
#
#   ./run.sh                 # full setup + start server + simulator
#   ./run.sh --no-seed       # skip DB seed (use when DB already seeded)
#   ./run.sh --no-sim        # start server only, no simulator
#   ./run.sh --video /path/to/video.mp4   # use a real video instead of simulator
#   ./run.sh --stop          # kill the server (and any simulator running)
#   ./run.sh --reset         # wipe DB + logs, re-seed, restart everything
#   ./run.sh --status        # show what's currently running
#   ./run.sh --test          # run the pytest test suite
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }
info() { echo -e "${CYAN}  →${RESET} $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET} $*"; }
err()  { echo -e "${RED}  ✗${RESET} $*"; }
hdr()  { echo -e "\n${BOLD}${CYAN}$*${RESET}"; echo "  $(printf '─%.0s' {1..60})"; }

# ── Project root (directory containing this script) ───────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PROJECT_ROOT="$SCRIPT_DIR"

# ── Defaults ──────────────────────────────────────────────────────────────────
DO_SEED=true
DO_SIM=true
DO_RESET=false
DO_STOP=false
DO_STATUS=false
DO_TEST=false
VIDEO_SOURCE=""
SERVER_PORT=8000
SIM_RATE=3         # seconds between detections
PID_DIR="$PROJECT_ROOT/.pids"

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --no-seed)   DO_SEED=false; shift ;;
    --no-sim)    DO_SIM=false;  shift ;;
    --video)     VIDEO_SOURCE="$2"; DO_SIM=false; shift 2 ;;
    --reset)     DO_RESET=true; shift ;;
    --stop)      DO_STOP=true;  shift ;;
    --status)    DO_STATUS=true; shift ;;
    --test)      DO_TEST=true;  DO_SIM=false; shift ;;
    --port)      SERVER_PORT="$2"; shift 2 ;;
    --rate)      SIM_RATE="$2"; shift 2 ;;
    -h|--help)
      head -30 "$0" | grep "^#" | sed 's/^# \{0,\}//'
      exit 0 ;;
    *) err "Unknown option: $1"; exit 1 ;;
  esac
done

mkdir -p "$PID_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: check if port is in use
# ═══════════════════════════════════════════════════════════════════════════════
port_in_use() { lsof -ti:"$1" &>/dev/null; }

# ═══════════════════════════════════════════════════════════════════════════════
# --status
# ═══════════════════════════════════════════════════════════════════════════════
if $DO_STATUS; then
  hdr "Status"
  if port_in_use $SERVER_PORT; then
    PID=$(lsof -ti:$SERVER_PORT | head -1)
    ok "Backend server is RUNNING on port $SERVER_PORT (PID $PID)"
    echo "    Dashboard → http://localhost:$SERVER_PORT"
    echo "    API docs  → http://localhost:$SERVER_PORT/docs"
  else
    warn "Backend server is NOT running on port $SERVER_PORT"
  fi
  if [[ -f "$PID_DIR/simulator.pid" ]]; then
    SIM_PID=$(cat "$PID_DIR/simulator.pid" 2>/dev/null || echo "")
    if [[ -n "$SIM_PID" ]] && kill -0 "$SIM_PID" 2>/dev/null; then
      ok "Simulator is RUNNING (PID $SIM_PID)"
    else
      warn "Simulator is NOT running (stale PID file)"
    fi
  else
    info "Simulator is not running"
  fi
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# --stop
# ═══════════════════════════════════════════════════════════════════════════════
if $DO_STOP; then
  hdr "Stopping services"
  if port_in_use $SERVER_PORT; then
    lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null && ok "Backend server stopped"
  else
    info "Server was not running"
  fi
  if [[ -f "$PID_DIR/simulator.pid" ]]; then
    SIM_PID=$(cat "$PID_DIR/simulator.pid" 2>/dev/null || echo "")
    if [[ -n "$SIM_PID" ]] && kill -0 "$SIM_PID" 2>/dev/null; then
      kill "$SIM_PID" 2>/dev/null && ok "Simulator stopped (PID $SIM_PID)"
    fi
    rm -f "$PID_DIR/simulator.pid"
  fi
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════
clear
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ███╗   ██╗███████╗██████╗  █████╗ ██╗     "
echo "  ████╗  ██║██╔════╝██╔══██╗██╔══██╗██║     "
echo "  ██╔██╗ ██║█████╗  ██████╔╝███████║██║     "
echo "  ██║╚██╗██║██╔══╝  ██╔═══╝ ██╔══██║██║     "
echo "  ██║ ╚████║███████╗██║     ██║  ██║███████╗"
echo "  ╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝  ╚═╝╚══════╝"
echo ""
echo "  Traffic AI — Kathmandu Valley Checkpoint System"
echo -e "${RESET}"
echo "  Project: $PROJECT_ROOT"
echo "  Python:  $(python3 --version 2>&1)"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 0: --reset (wipe DB + logs)
# ═══════════════════════════════════════════════════════════════════════════════
if $DO_RESET; then
  hdr "Step 0 · Reset — wiping database and logs"

  # Kill existing server first
  if port_in_use $SERVER_PORT; then
    lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null
    sleep 1
    ok "Stopped existing server"
  fi

  rm -f "$PROJECT_ROOT/nepal_traffic.db"
  rm -f "$PROJECT_ROOT/logs/"*.log
  ok "Database and logs wiped"
  DO_SEED=true
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Update requirements.txt (Python 3.13 compatible, no pinned versions)
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 1 · Requirements — updating to Python 3.13 compatible versions"

cat > "$PROJECT_ROOT/backend/requirements.txt" << 'REQEOF'
# ── Core API framework ────────────────────────────────────────────────────────
fastapi>=0.115.0
uvicorn[standard]>=0.30.0

# ── Database ──────────────────────────────────────────────────────────────────
sqlalchemy[asyncio]>=2.0.36
aiosqlite>=0.20.0

# ── Validation & config ───────────────────────────────────────────────────────
pydantic>=2.10.0
pydantic-settings>=2.6.0
python-multipart>=0.0.9
python-dotenv>=1.0.1

# ── Image processing ──────────────────────────────────────────────────────────
pillow>=10.0.0
numpy>=1.26.0
opencv-python-headless>=4.8.0

# ── ML / AI ───────────────────────────────────────────────────────────────────
ultralytics>=8.2.0            # YOLOv8 — works on Python 3.13

# ── Data & reporting ─────────────────────────────────────────────────────────
pandas>=2.0.0
reportlab>=4.0.0

# ── HTTP / WebSocket ──────────────────────────────────────────────────────────
httpx>=0.27.0
websockets>=12.0
anyio>=4.0.0

# ── Testing ───────────────────────────────────────────────────────────────────
pytest>=8.0.0
pytest-asyncio>=0.23.0
REQEOF

ok "requirements.txt updated (Python 3.13 compatible)"

# ── Optional ML extras note ───────────────────────────────────────────────────
cat > "$PROJECT_ROOT/backend/requirements-ml.txt" << 'MLEOF'
# ── OPTIONAL: Real OCR — requires Python ≤ 3.11 (use conda env or Docker) ───
# Install ONLY if you have Python 3.10 or 3.11:
#   pip install -r backend/requirements-ml.txt
paddlepaddle>=3.0.0
paddleocr>=2.8.0
MLEOF

ok "requirements-ml.txt written (PaddleOCR, optional)"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Install Python dependencies
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 2 · Installing Python dependencies"

info "Running pip install -r backend/requirements.txt ..."
if pip install -r "$PROJECT_ROOT/backend/requirements.txt" -q --no-warn-script-location 2>&1; then
  ok "All packages installed"
else
  err "pip install failed. Check your internet connection or pip version."
  exit 1
fi

# Verify critical imports
info "Verifying critical imports..."
FAILED_IMPORTS=()
for pkg in fastapi uvicorn sqlalchemy aiosqlite pydantic ultralytics cv2 httpx; do
  python3 -c "import $pkg" 2>/dev/null && ok "$pkg" || { warn "$pkg import failed (non-fatal)"; FAILED_IMPORTS+=("$pkg"); }
done

if [[ ${#FAILED_IMPORTS[@]} -gt 0 ]]; then
  warn "Some imports failed: ${FAILED_IMPORTS[*]}"
  warn "The system will still run in MOCK_MODE=true"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Create / verify .env file
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 3 · Environment — creating .env configuration"

ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" << 'ENVEOF'
# Nepal Traffic AI — Environment Configuration
DATABASE_URL=sqlite+aiosqlite:///./nepal_traffic.db
MOCK_MODE=true
CAMERA_SOURCES=
# Set DOTM_API_KEY to your real DoTM registry key (leave blank for mock mode).
DOTM_API_KEY=
CONFIDENCE_THRESHOLD=0.65
CHECKPOINT_NAME=Thankot Checkpoint
CHECKPOINT_LOCATION=Thankot, Chandragiri Municipality, Kathmandu
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080
ENVEOF
  ok ".env file created"
else
  ok ".env already exists — keeping current settings"
fi

# Show current config
echo ""
echo "  Current configuration:"
grep -v "^#" "$ENV_FILE" | grep -v "^$" | while IFS= read -r line; do
  echo "    $line"
done
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Create required directories
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 4 · Directories"

for dir in logs data models reports; do
  mkdir -p "$PROJECT_ROOT/$dir"
  ok "  $dir/"
done

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Seed the database
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 5 · Database — seeding"

DB_FILE="$PROJECT_ROOT/nepal_traffic.db"

if $DO_SEED; then
  info "Running seed script (3 checkpoints, 500 DoTM records, 2000 sightings)..."
  if PYTHONPATH="$PROJECT_ROOT" python3 -m scripts.seed_database 2>&1; then
    ok "Database seeded successfully"
    if [[ -f "$DB_FILE" ]]; then
      DB_SIZE=$(du -sh "$DB_FILE" | cut -f1)
      ok "Database file: $DB_FILE ($DB_SIZE)"
    fi
  else
    err "Seed script failed. Check the error above."
    exit 1
  fi
else
  if [[ -f "$DB_FILE" ]]; then
    DB_SIZE=$(du -sh "$DB_FILE" | cut -f1)
    ok "Using existing database: $DB_FILE ($DB_SIZE)"
  else
    warn "No database found. Forcing seed..."
    PYTHONPATH="$PROJECT_ROOT" python3 -m scripts.seed_database 2>&1 && ok "Database seeded"
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Kill any existing server on the port
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 6 · Port check — clearing port $SERVER_PORT"

if port_in_use $SERVER_PORT; then
  warn "Port $SERVER_PORT is in use. Killing existing process..."
  lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null
  sleep 1
  if port_in_use $SERVER_PORT; then
    err "Could not free port $SERVER_PORT. Try: sudo lsof -ti:$SERVER_PORT | xargs kill -9"
    exit 1
  fi
  ok "Port $SERVER_PORT freed"
else
  ok "Port $SERVER_PORT is available"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Run tests (if --test flag)
# ═══════════════════════════════════════════════════════════════════════════════
if $DO_TEST; then
  hdr "Step 7 · Tests"
  info "Running pytest..."
  PYTHONPATH="$PROJECT_ROOT" python3 -m pytest tests/ -v --tb=short 2>&1
  exit $?
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Start backend server
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 7 · Backend server — starting on port $SERVER_PORT"

SERVER_LOG="$PROJECT_ROOT/logs/server.log"
info "Launching uvicorn (logs → $SERVER_LOG) ..."

PYTHONPATH="$PROJECT_ROOT" nohup python3 -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "$SERVER_PORT" \
  --reload \
  --log-level info \
  > "$SERVER_LOG" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_DIR/server.pid"
info "Server PID: $SERVER_PID"

# Wait for server to be ready (up to 15 seconds)
info "Waiting for server to be ready..."
READY=false
for i in $(seq 1 15); do
  sleep 1
  if curl -s "http://localhost:$SERVER_PORT/health" &>/dev/null; then
    READY=true
    break
  fi
  printf "."
done
echo ""

if $READY; then
  ok "Server is UP and healthy"
  # Show health response
  HEALTH=$(curl -s "http://localhost:$SERVER_PORT/health" 2>/dev/null)
  echo "  Health: $HEALTH"
else
  err "Server did not respond within 15s. Check logs:"
  echo ""
  tail -20 "$SERVER_LOG"
  exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: Start simulator OR video processor
# ═══════════════════════════════════════════════════════════════════════════════
hdr "Step 8 · Data source"

if [[ -n "$VIDEO_SOURCE" ]]; then
  # ── Real video mode ─────────────────────────────────────────────────────────
  if [[ ! -f "$VIDEO_SOURCE" ]] && [[ ! "$VIDEO_SOURCE" =~ ^rtsp:// ]] && [[ "$VIDEO_SOURCE" != "0" ]]; then
    err "Video source not found: $VIDEO_SOURCE"
    err "Provide a valid file path, device index (0), or rtsp:// URL"
    exit 1
  fi

  info "Starting real video processor..."
  info "Source: $VIDEO_SOURCE"

  VIDEO_LOG="$PROJECT_ROOT/logs/video_processor.log"

  PYTHONPATH="$PROJECT_ROOT" nohup python3 -m scripts.process_video \
    --source "$VIDEO_SOURCE" \
    --checkpoint "cp-thankot" \
    --camera-id "cam-video-01" \
    --confidence 0.45 \
    --skip-frames 3 \
    --mock-ocr \
    --api "http://localhost:$SERVER_PORT/api" \
    > "$VIDEO_LOG" 2>&1 &

  VIDEO_PID=$!
  echo "$VIDEO_PID" > "$PID_DIR/simulator.pid"
  sleep 2

  if kill -0 "$VIDEO_PID" 2>/dev/null; then
    ok "Video processor started (PID $VIDEO_PID)"
    ok "Logs → $VIDEO_LOG"
    ok "Watch live: tail -f $VIDEO_LOG"
  else
    err "Video processor crashed. Check:"
    tail -10 "$VIDEO_LOG"
  fi

elif $DO_SIM; then
  # ── Synthetic simulator mode ─────────────────────────────────────────────────
  info "Starting synthetic camera simulator (rate: ~${SIM_RATE}s/detection)..."

  SIM_LOG="$PROJECT_ROOT/logs/simulator.log"

  PYTHONPATH="$PROJECT_ROOT" nohup python3 -m scripts.simulate_camera \
    --checkpoint "cp-thankot" \
    --rate "$SIM_RATE" \
    > "$SIM_LOG" 2>&1 &

  SIM_PID=$!
  echo "$SIM_PID" > "$PID_DIR/simulator.pid"
  sleep 2

  if kill -0 "$SIM_PID" 2>/dev/null; then
    ok "Simulator started (PID $SIM_PID)"
    ok "Logs → $SIM_LOG"
  else
    err "Simulator crashed. Check:"
    tail -10 "$SIM_LOG"
  fi
else
  info "No data source started (--no-sim was set)"
  info "You can start the simulator manually in another terminal:"
  echo "    PYTHONPATH=. python -m scripts.simulate_camera --rate 3"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DONE — Print summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  ✓  Nepal Traffic AI is running!${RESET}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Dashboard${RESET}   →  http://localhost:$SERVER_PORT"
echo -e "  ${BOLD}API docs${RESET}    →  http://localhost:$SERVER_PORT/docs"
echo -e "  ${BOLD}Health${RESET}      →  http://localhost:$SERVER_PORT/health"
echo ""
echo -e "  ${BOLD}Logs${RESET}"
echo -e "    Server    →  tail -f $PROJECT_ROOT/logs/server.log"
if [[ -n "$VIDEO_SOURCE" ]]; then
  echo -e "    Video     →  tail -f $PROJECT_ROOT/logs/video_processor.log"
elif $DO_SIM; then
  echo -e "    Simulator →  tail -f $PROJECT_ROOT/logs/simulator.log"
fi
echo -e "    Detections→  tail -f $PROJECT_ROOT/logs/detections.log"
echo -e "    Alerts    →  tail -f $PROJECT_ROOT/logs/alerts.log"
echo ""
echo -e "  ${BOLD}Useful commands${RESET}"
echo -e "    Stop everything  →  ./run.sh --stop"
echo -e "    Reset & restart  →  ./run.sh --reset"
echo -e "    Status           →  ./run.sh --status"
echo -e "    Run tests        →  ./run.sh --test"
if [[ -z "$VIDEO_SOURCE" ]]; then
  echo -e "    Use a video file →  ./run.sh --video /path/to/traffic.mp4"
fi
echo ""
echo -e "  ${YELLOW}Press Ctrl+C to exit this script (server keeps running)${RESET}"
echo ""

# ── Optionally tail the simulator log so user sees detections rolling in ──────
if $DO_SIM && [[ -f "$PROJECT_ROOT/logs/simulator.log" ]]; then
  echo -e "  ${CYAN}─── Live simulator output (Ctrl+C to detach) ───${RESET}"
  echo ""
  sleep 1
  tail -f "$PROJECT_ROOT/logs/simulator.log" &
  TAIL_PID=$!
  trap "kill $TAIL_PID 2>/dev/null; echo ''; echo '  Server is still running in background.'; echo '  Stop it with: ./run.sh --stop'; exit 0" INT
  wait $TAIL_PID
elif [[ -n "$VIDEO_SOURCE" ]] && [[ -f "$PROJECT_ROOT/logs/video_processor.log" ]]; then
  echo -e "  ${CYAN}─── Live video processor output (Ctrl+C to detach) ───${RESET}"
  echo ""
  sleep 1
  tail -f "$PROJECT_ROOT/logs/video_processor.log" &
  TAIL_PID=$!
  trap "kill $TAIL_PID 2>/dev/null; echo ''; echo '  Server is still running in background.'; echo '  Stop it with: ./run.sh --stop'; exit 0" INT
  wait $TAIL_PID
fi
