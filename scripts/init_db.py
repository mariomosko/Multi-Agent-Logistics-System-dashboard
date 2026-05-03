"""
Database initialisation script.

Usage:
    python -m scripts.init_db                         # create tables only
    python -m scripts.init_db --seed                  # create tables + insert sample data
    python -m scripts.init_db --seed --reset          # drop all data first, then seed
    python -m scripts.init_db --seed --if-empty       # seed only when shipments table is empty
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import randint

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select, text

from app.database import AsyncSessionLocal, engine, init_db
from app.models import (
    AgentAction,
    ExceptionSeverity,
    Resolution,
    Shipment,
    ShipmentException,
    ShipmentStatus,
    WorkflowStatus,
)


async def create_tables() -> None:
    print("Creating tables…")
    await init_db()
    print("Tables created.")


async def drop_and_recreate() -> None:
    """Drop all tables then recreate them — picks up schema changes."""
    print("Dropping all tables…")
    async with engine.begin() as conn:
        from app.database import Base
        await conn.run_sync(Base.metadata.drop_all)
    print("Recreating tables…")
    await init_db()
    print("Schema reset complete.")


async def reset_data() -> None:
    print("Resetting data…")
    async with AsyncSessionLocal() as db:
        for table in ("resolutions", "agent_actions", "shipment_exceptions",
                      "webhook_events", "shipments"):
            await db.execute(text(f"DELETE FROM {table}"))
        await db.commit()
    print("Data cleared.")


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def _make_actions(exception_id_placeholder: str, steps: list[dict]) -> list[AgentAction]:
    """Build AgentAction rows for a pre-resolved exception."""
    rows = []
    for s in steps:
        rows.append(AgentAction(
            agent_name=s["agent_name"],
            action_taken=s["action_taken"],
            reasoning=s["reasoning"],
            status="completed",
            duration_ms=s.get("duration_ms", randint(900, 2400)),
            input_tokens=s.get("input_tokens", randint(320, 780)),
            output_tokens=s.get("output_tokens", randint(90, 360)),
        ))
    return rows


async def is_db_empty() -> bool:
    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(Shipment))
        return (count or 0) == 0


async def seed_sample_data() -> None:
    print("Seeding sample data…")
    async with AsyncSessionLocal() as db:

        # ── 10 Shipments ──────────────────────────────────────────────────────

        shipments = [
            # FedEx
            Shipment(tracking_number="FX100000001", status=ShipmentStatus.IN_TRANSIT,
                     carrier="FedEx", origin="New York, NY", destination="Los Angeles, CA",
                     customer_name="Alice Johnson",  customer_email="alice@example.com"),
            Shipment(tracking_number="FX100000002", status=ShipmentStatus.IN_TRANSIT,
                     carrier="FedEx", origin="Boston, MA",    destination="Seattle, WA",
                     customer_name="Marcus Chen",    customer_email="marcus@example.com"),
            Shipment(tracking_number="FX100000003", status=ShipmentStatus.IN_TRANSIT,
                     carrier="FedEx", origin="Phoenix, AZ",   destination="Nashville, TN",
                     customer_name="Sarah Williams", customer_email="sarah@example.com"),
            # UPS
            Shipment(tracking_number="UPS200000001", status=ShipmentStatus.IN_TRANSIT,
                     carrier="UPS", origin="Chicago, IL",  destination="Miami, FL",
                     customer_name="Bob Smith",      customer_email="bob@example.com"),
            Shipment(tracking_number="UPS200000002", status=ShipmentStatus.IN_TRANSIT,
                     carrier="UPS", origin="Denver, CO",   destination="Atlanta, GA",
                     customer_name="Diana Park",     customer_email="diana@example.com"),
            Shipment(tracking_number="UPS200000003", status=ShipmentStatus.PENDING,
                     carrier="UPS", origin="Detroit, MI",  destination="Portland, OR",
                     customer_name="Kevin Rodriguez",customer_email="kevin@example.com"),
            # USPS
            Shipment(tracking_number="USPS300000001", status=ShipmentStatus.IN_TRANSIT,
                     carrier="USPS", origin="Seattle, WA",     destination="Austin, TX",
                     customer_name="Carol White",    customer_email="carol@example.com"),
            Shipment(tracking_number="USPS300000002", status=ShipmentStatus.PENDING,
                     carrier="USPS", origin="Minneapolis, MN", destination="Houston, TX",
                     customer_name="Tom Anderson",   customer_email="tom@example.com"),
            # DHL
            Shipment(tracking_number="DHL400000001", status=ShipmentStatus.IN_TRANSIT,
                     carrier="DHL", origin="New York, NY",    destination="London, UK (via JFK)",
                     customer_name="Elena Vasquez",  customer_email="elena@example.com"),
            Shipment(tracking_number="DHL400000002", status=ShipmentStatus.IN_TRANSIT,
                     carrier="DHL", origin="Los Angeles, CA", destination="Tokyo, Japan (via LAX)",
                     customer_name="James Wu",        customer_email="james@example.com"),
        ]
        db.add_all(shipments)
        await db.flush()
        print(f"  Inserted {len(shipments)} shipments.")

        # Build a quick lookup by tracking number
        by_tn = {s.tracking_number: s for s in shipments}

        # ── 5 Pre-resolved exceptions ─────────────────────────────────────────
        # These populate the monitoring panels immediately without needing live runs.

        exc_seeds = [
            # 1. FX100000001 — delay, high
            dict(
                shipment=by_tn["FX100000001"],
                exception_type="delay",
                severity=ExceptionSeverity.HIGH,
                description="Package delayed due to severe weather at Memphis hub.",
                detected_at=_ago(hours=6),
                raw_event={
                    "event_type": "delay", "carrier": "FedEx",
                    "tracking_number": "FX100000001",
                    "location": "Memphis, TN — FedEx World Hub",
                    "description": "Tornado warning grounds all outbound flights.",
                    "status_code": "DE",
                },
                resolution_type="contact_carrier",
                root_cause="Category 3 storm forced 18-hour hub closure, grounding 47 flights.",
                customer_message="We're sorry for the delay caused by severe weather at our hub. Your package is now on its way and will arrive within 3 days.",
                actions_taken=[
                    {"action_type": "contact_carrier", "status": "completed", "result": "Priority reroute confirmed via Louisville hub"},
                    {"action_type": "notify_customer", "status": "completed", "result": "Email sent with revised ETA"},
                ],
                agent_steps=[
                    dict(agent_name="detection_agent",     action_taken="Classified as 'delay' exception (94% confidence)",        reasoning="Severe weather event grounded all outbound flights at sorting hub."),
                    dict(agent_name="analysis_agent",      action_taken="Severity assessed as 'high'; estimated delay: 3 day(s)",   reasoning="Category 3 storm forced 18-hour hub closure, grounding 47 flights and delaying 12,000+ packages."),
                    dict(agent_name="decision_agent",      action_taken="Resolution selected: 'contact_carrier' with 2 action(s)", reasoning="Contact hub ops to expedite reroute and set priority flag; update customer with revised ETA."),
                    dict(agent_name="communication_agent", action_taken='Customer notification drafted: "Shipment delay notice — updated delivery estimate"', reasoning="Tone: apologetic"),
                    dict(agent_name="action_agent",        action_taken="Executed 2 action(s) — overall status: resolved",         reasoning="Carrier priority flag set. Reroute via alternate hub confirmed. ETA updated."),
                ],
            ),
            # 2. UPS200000001 — damaged, critical
            dict(
                shipment=by_tn["UPS200000001"],
                exception_type="damaged",
                severity=ExceptionSeverity.CRITICAL,
                description="Package sustained visible crush damage at UPS Worldport.",
                detected_at=_ago(hours=4),
                raw_event={
                    "event_type": "damaged", "carrier": "UPS",
                    "tracking_number": "UPS200000001",
                    "location": "Louisville, KY — UPS Worldport",
                    "description": "Outer carton crushed; contents compromised.",
                    "status_code": "DM",
                },
                resolution_type="reship",
                root_cause="Forklift tine punctured outer carton during unloading. Facility confirmed operator error.",
                customer_message="We sincerely apologize — your package was damaged during transit. A replacement has been dispatched and will arrive within 2 business days.",
                actions_taken=[
                    {"action_type": "file_damage_claim", "status": "completed", "result": "Carrier damage claim #CLM-887432 filed"},
                    {"action_type": "reship",            "status": "completed", "result": "Replacement shipped via 2-day priority with foam inserts"},
                ],
                agent_steps=[
                    dict(agent_name="detection_agent",     action_taken="Classified as 'damaged' exception (98% confidence)",      reasoning="Forklift impact detected at sorting facility — outer carton visibly crushed."),
                    dict(agent_name="analysis_agent",      action_taken="Severity assessed as 'critical'; estimated delay: 2 day(s)", reasoning="Forklift tine punctured outer carton during unloading. Facility confirmed operator error."),
                    dict(agent_name="decision_agent",      action_taken="Resolution selected: 'reship' with 2 action(s)",          reasoning="Damage assessment confirms contents compromised. Reship immediately with enhanced protective packaging."),
                    dict(agent_name="communication_agent", action_taken='Customer notification drafted: "Your shipment was damaged in transit"', reasoning="Tone: apologetic"),
                    dict(agent_name="action_agent",        action_taken="Executed 2 action(s) — overall status: resolved",         reasoning="Carrier damage claim #CLM-887432 filed. Replacement shipped via 2-day priority with foam inserts."),
                ],
            ),
            # 3. USPS300000001 — address_issue, low
            dict(
                shipment=by_tn["USPS300000001"],
                exception_type="address_issue",
                severity=ExceptionSeverity.LOW,
                description="Apartment number missing from label — delivery failed.",
                detected_at=_ago(hours=3),
                raw_event={
                    "event_type": "address_issue", "carrier": "USPS",
                    "tracking_number": "USPS300000001",
                    "location": "Austin, TX 78701",
                    "description": "Apartment number missing. Redelivery requires correction.",
                    "status_code": "AG",
                },
                resolution_type="schedule_redelivery",
                root_cause="Shipper omitted apartment number; USPS database shows 24 units at this street address.",
                customer_message="We were unable to deliver your package due to a missing apartment number. Please reply with your unit number so we can reattempt delivery.",
                actions_taken=[
                    {"action_type": "contact_customer",      "status": "completed", "result": "Customer confirmed Apt 4B"},
                    {"action_type": "schedule_redelivery",   "status": "completed", "result": "Redelivery booked for next business day 10AM–2PM"},
                ],
                agent_steps=[
                    dict(agent_name="detection_agent",     action_taken="Classified as 'address_issue' exception (93% confidence)", reasoning="Delivery failed: apartment number absent from shipping label."),
                    dict(agent_name="analysis_agent",      action_taken="Severity assessed as 'low'; estimated delay: 2 day(s)",     reasoning="Shipper omitted apartment number; USPS database shows 24 units at this street address."),
                    dict(agent_name="decision_agent",      action_taken="Resolution selected: 'schedule_redelivery' with 2 action(s)", reasoning="Contact customer to confirm corrected address, then schedule redelivery within next business day."),
                    dict(agent_name="communication_agent", action_taken='Customer notification drafted: "Action required: delivery address update needed"', reasoning="Tone: informational"),
                    dict(agent_name="action_agent",        action_taken="Executed 2 action(s) — overall status: resolved",           reasoning="Customer confirmed Apt 4B. Corrected label generated. Redelivery booked for next business day 10AM–2PM."),
                ],
            ),
            # 4. DHL400000001 — customs_hold, medium
            dict(
                shipment=by_tn["DHL400000001"],
                exception_type="customs_hold",
                severity=ExceptionSeverity.MEDIUM,
                description="CBP documentation review at JFK — estimated 5-day hold.",
                detected_at=_ago(hours=5),
                raw_event={
                    "event_type": "customs_hold", "carrier": "DHL",
                    "tracking_number": "DHL400000001",
                    "location": "JFK International Airport, NY — CBP Customs",
                    "description": "Commercial invoice and HS tariff codes require verification.",
                    "status_code": "CH",
                },
                resolution_type="contact_carrier",
                root_cause="Commercial invoice value inconsistent with HS code; CBP requires importer clarification before release.",
                customer_message="Your international shipment is currently undergoing customs review at JFK. Our customs broker is working to expedite clearance and will provide an update within 48 hours.",
                actions_taken=[
                    {"action_type": "engage_customs_broker", "status": "completed",         "result": "Customs broker notified and assigned"},
                    {"action_type": "submit_documentation",  "status": "pending_external",  "result": "Supplemental HS declaration submitted to CBP portal"},
                ],
                agent_steps=[
                    dict(agent_name="detection_agent",     action_taken="Classified as 'customs_hold' exception (96% confidence)", reasoning="CBP flagged shipment for supplemental documentation review."),
                    dict(agent_name="analysis_agent",      action_taken="Severity assessed as 'medium'; estimated delay: 5 day(s)", reasoning="Commercial invoice value inconsistent with HS code; CBP requires importer clarification before release."),
                    dict(agent_name="decision_agent",      action_taken="Resolution selected: 'contact_carrier' with 3 action(s)", reasoning="Engage customs broker; submit supplemental HS declaration and invoice to CBP within 48h."),
                    dict(agent_name="communication_agent", action_taken='Customer notification drafted: "Customs processing update for your shipment"', reasoning="Tone: informational"),
                    dict(agent_name="action_agent",        action_taken="Executed 2 action(s) — overall status: partially_resolved", reasoning="Customs broker engaged. Supplemental HS declaration submitted. Awaiting CBP portal confirmation."),
                ],
            ),
            # 5. FX100000002 — lost, high
            dict(
                shipment=by_tn["FX100000002"],
                exception_type="lost",
                severity=ExceptionSeverity.HIGH,
                description="No scans for 6 days — package likely misrouted during sort.",
                detected_at=_ago(hours=2),
                raw_event={
                    "event_type": "lost", "carrier": "FedEx",
                    "tracking_number": "FX100000002",
                    "location": "Last scan: Dallas, TX — FedEx Ground",
                    "description": "No scan activity for 6 days. Investigation initiated.",
                    "status_code": "LS",
                },
                resolution_type="reship",
                root_cause="Package likely misrouted during high-volume surge; barcode may have been damaged mid-sort.",
                customer_message="We're sorry to inform you that we've lost track of your shipment. We've opened an urgent investigation and have dispatched a replacement. You'll receive tracking information within 24 hours.",
                actions_taken=[
                    {"action_type": "open_trace_ticket", "status": "completed", "result": "Carrier trace ticket #TRC-2026-8821 opened"},
                    {"action_type": "reship",            "status": "completed", "result": "Replacement order created and dispatched"},
                    {"action_type": "insurance_claim",   "status": "completed", "result": "Insurance claim #INS-2026-4412 filed"},
                ],
                agent_steps=[
                    dict(agent_name="detection_agent",     action_taken="Classified as 'lost' exception (97% confidence)",          reasoning="No scan activity for 6 days — package likely misrouted during high-volume sort."),
                    dict(agent_name="analysis_agent",      action_taken="Severity assessed as 'high'; estimated delay: 7 day(s)",    reasoning="Package likely misrouted during holiday surge; barcode may have been damaged mid-sort causing misread."),
                    dict(agent_name="decision_agent",      action_taken="Resolution selected: 'reship' with 3 action(s)",           reasoning="Package unrecoverable after 6-day trace window. Authorize replacement shipment and open insurance claim."),
                    dict(agent_name="communication_agent", action_taken='Customer notification drafted: "Important: your shipment is being investigated"', reasoning="Tone: urgent"),
                    dict(agent_name="action_agent",        action_taken="Executed 3 action(s) — overall status: resolved",          reasoning="Carrier trace ticket #TRC-2026-8821 opened. Replacement dispatched. Insurance claim pending."),
                ],
            ),
        ]

        for seed in exc_seeds:
            exc = ShipmentException(
                shipment_id=seed["shipment"].id,
                exception_type=seed["exception_type"],
                severity=seed["severity"],
                description=seed["description"],
                raw_event=seed["raw_event"],
                workflow_status=WorkflowStatus.RESOLVED,
            )
            # Manually set detected_at (bypasses server_default)
            exc.detected_at = seed["detected_at"]
            db.add(exc)
            await db.flush()

            # Agent actions
            for step in seed["agent_steps"]:
                db.add(AgentAction(
                    exception_id=exc.id,
                    agent_name=step["agent_name"],
                    action_taken=step["action_taken"],
                    reasoning=step["reasoning"],
                    status="completed",
                    duration_ms=randint(800, 2800),
                    input_tokens=randint(320, 850),
                    output_tokens=randint(80, 380),
                ))

            # Resolution
            db.add(Resolution(
                exception_id=exc.id,
                resolution_type=seed["resolution_type"],
                root_cause=seed["root_cause"],
                customer_notified=True,
                customer_message=seed["customer_message"],
                actions_taken=seed["actions_taken"],
            ))

        await db.commit()
        print(f"  Inserted {len(exc_seeds)} pre-resolved exceptions with full agent history.")


async def verify_schema() -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = [row[0] for row in result.fetchall()]
    print(f"Tables: {', '.join(tables)}")


async def main(seed: bool, reset: bool, if_empty: bool) -> None:
    if reset:
        await drop_and_recreate()
    else:
        await create_tables()
    if seed:
        if if_empty:
            if await is_db_empty():
                await seed_sample_data()
            else:
                print("  Database already has data — skipping seed.")
        else:
            await seed_sample_data()
    await verify_schema()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialise the logistics database")
    parser.add_argument("--seed",     action="store_true", help="Insert sample data")
    parser.add_argument("--reset",    action="store_true", help="Drop and recreate all tables before seeding")
    parser.add_argument("--if-empty", action="store_true", help="Seed only when the shipments table is empty")
    args = parser.parse_args()
    asyncio.run(main(seed=args.seed, reset=args.reset, if_empty=args.if_empty))
