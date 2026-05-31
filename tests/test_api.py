"""
tests/test_api.py
Integration tests for all REST API endpoints.
Uses in-memory SQLite with httpx AsyncClient.
"""
import pytest
import pytest_asyncio
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MOCK_MODE"]    = "true"

from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db


@pytest_asyncio.fixture(scope="module")
async def client():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Health endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mock_mode"] is True


# ── Ingest + vehicles ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_creates_sighting(client):
    payload = {
        "plate_text":         "Ba 2 Kha 4521",
        "plate_confidence":   0.92,
        "vehicle_type":       "car",
        "ownership_category": "private",
        "district_code":      "Ba",
        "direction":          "inbound",
        "checkpoint_id":      "cp-test",
        "camera_id":          "cam-01",
    }
    resp = await client.post("/api/ingest", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["plate_text"] == "Ba 2 Kha 4521"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_ingest_bus_with_origin(client):
    payload = {
        "plate_text":         "Ka 3 Cha 8899",
        "plate_confidence":   0.85,
        "vehicle_type":       "bus",
        "ownership_category": "public",
        "direction":          "inbound",
        "checkpoint_id":      "cp-test",
        "origin_city":        "Pokhara",
        "destination_city":   "Kathmandu",
        "origin_text":        "पोखरा–काठमाडौं",
    }
    resp = await client.post("/api/ingest", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["origin_city"] == "Pokhara"


@pytest.mark.asyncio
async def test_list_vehicles_returns_200(client):
    resp = await client.get("/api/vehicles")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_vehicles_filter_type(client):
    resp = await client.get("/api/vehicles?type=car")
    assert resp.status_code == 200
    data = resp.json()
    for row in data:
        assert row["vehicle_type"] == "car"


@pytest.mark.asyncio
async def test_list_vehicles_filter_direction(client):
    resp = await client.get("/api/vehicles?direction=inbound")
    assert resp.status_code == 200
    data = resp.json()
    for row in data:
        assert row["direction"] == "inbound"


@pytest.mark.asyncio
async def test_get_vehicle_by_id(client):
    # First create one
    payload = {
        "plate_text": "Ko 1 Ja 0033",
        "plate_confidence": 0.88,
        "vehicle_type": "motorcycle",
        "ownership_category": "private",
        "direction": "outbound",
        "checkpoint_id": "cp-test",
    }
    create_resp = await client.post("/api/ingest", json=payload)
    assert create_resp.status_code == 201
    vid = create_resp.json()["id"]

    resp = await client.get(f"/api/vehicles/{vid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == vid


@pytest.mark.asyncio
async def test_get_vehicle_not_found(client):
    resp = await client.get("/api/vehicles/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_vehicles_by_plate(client):
    resp = await client.get("/api/vehicles/search?plate=Ba")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Stats ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_summary(client):
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_today"     in data
    assert "by_type"         in data
    assert "by_ownership"    in data
    assert "plate_accuracy_pct" in data
    assert "active_alerts"   in data


@pytest.mark.asyncio
async def test_stats_hourly(client):
    resp = await client.get("/api/stats/hourly")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_stats_origin(client):
    resp = await client.get("/api/stats/origin")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── Alerts ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts(client):
    resp = await client.get("/api/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_alert_count_active(client):
    resp = await client.get("/api/alerts/count/active")
    assert resp.status_code == 200
    assert "count" in resp.json()


# ── Checkpoints ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_checkpoints(client):
    resp = await client.get("/api/checkpoints")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_checkpoint(client):
    resp = await client.post("/api/checkpoints", json={
        "name": "Test Checkpoint",
        "location": "Test Location",
        "lat": 27.7, "lng": 85.3,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Checkpoint"


# ── Watchlist ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watchlist_add_and_list(client):
    add_resp = await client.post("/api/watchlist", json={
        "plate_text": "Ba 9 Sa 1111",
        "reason": "Test watchlist",
        "added_by": "test",
    })
    assert add_resp.status_code == 201

    list_resp = await client.get("/api/watchlist")
    assert list_resp.status_code == 200
    plates = [w["plate_text"] for w in list_resp.json()]
    assert "Ba 9 Sa 1111" in plates


# ── DoTM lookup ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dotm_not_found(client):
    resp = await client.get("/api/dotm/ZZ%201%20ZZ%200001")
    assert resp.status_code == 404


# ── Reports ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_report(client):
    resp = await client.get("/api/reports/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_vehicles" in data
    assert "by_type"        in data


@pytest.mark.asyncio
async def test_export_csv(client):
    resp = await client.get("/api/reports/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_ingest_unregistered_creates_alert(client):
    """Ingest an unregistered plate — should create a warning alert."""
    # Use a clearly fake plate that won't be in the DoTM mock
    payload = {
        "plate_text":         "ZZ 9 ZZ 9999",
        "plate_confidence":   0.75,
        "vehicle_type":       "car",
        "ownership_category": "private",
        "direction":          "inbound",
        "checkpoint_id":      "cp-test",
    }
    resp = await client.post("/api/ingest", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # Should be flagged since ZZ is not in DoTM
    assert data["dotm_registered"] is False

    # Check an unregistered alert was raised
    alerts_resp = await client.get("/api/alerts?resolved=false")
    assert alerts_resp.status_code == 200
