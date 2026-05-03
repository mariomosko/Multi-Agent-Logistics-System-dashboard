"""Basic integration tests — require a running SQLite DB and a valid ANTHROPIC_API_KEY."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_logistics.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_shipment(client: AsyncClient):
    payload = {
        "tracking_number": "TEST123",
        "origin": "New York, NY",
        "destination": "Los Angeles, CA",
        "carrier": "FedEx",
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
    }
    resp = await client.post("/api/v1/shipments/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tracking_number"] == "TEST123"


@pytest.mark.asyncio
async def test_duplicate_shipment(client: AsyncClient):
    payload = {
        "tracking_number": "DUP001",
        "origin": "Chicago, IL",
        "destination": "Miami, FL",
        "carrier": "UPS",
        "customer_name": "John Smith",
        "customer_email": "john@example.com",
    }
    await client.post("/api/v1/shipments/", json=payload)
    resp = await client.post("/api/v1/shipments/", json=payload)
    assert resp.status_code == 409
