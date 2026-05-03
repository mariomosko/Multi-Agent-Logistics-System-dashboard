from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Shipment
from app.schemas import ShipmentCreate, ShipmentRead

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.post("/", response_model=ShipmentRead, status_code=201)
async def create_shipment(
    payload: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
) -> Shipment:
    existing = await db.scalar(
        select(Shipment).where(Shipment.tracking_number == payload.tracking_number)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tracking number already exists")

    shipment = Shipment(**payload.model_dump())
    db.add(shipment)
    await db.commit()
    await db.refresh(shipment)
    return shipment


@router.get("/", response_model=list[ShipmentRead])
async def list_shipments(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[Shipment]:
    result = await db.execute(select(Shipment).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{shipment_id}", response_model=ShipmentRead)
async def get_shipment(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
) -> Shipment:
    shipment = await db.get(Shipment, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment
