"""
Five sample webhook payloads for testing the /api/v1/webhook/tracking-update endpoint.

Each payload simulates a real carrier event for a different exception scenario.
The tracking numbers match the seeds inserted by `python -m scripts.init_db --seed`.

Usage (requires the server to be running):

    import httpx, asyncio
    from tests.sample_payloads import PAYLOADS

    async def send(payload):
        async with httpx.AsyncClient(base_url="http://localhost:8000") as c:
            r = await c.post("/api/v1/webhook/tracking-update", json=payload)
            print(r.status_code, r.json())

    asyncio.run(send(PAYLOADS["weather_delay"]))
"""

# ── 1. Severe weather delay ───────────────────────────────────────────────────
WEATHER_DELAY = {
    "carrier": "FedEx",
    "tracking_number": "FX100000001",
    "event_type": "delay",
    "event_timestamp": "2026-05-03T14:30:00Z",
    "location": "Memphis, TN — FedEx World Hub",
    "description": (
        "Package delayed due to severe thunderstorms and tornado warnings across "
        "the Memphis hub. All outbound flights grounded. Estimated delay: 2-3 days."
    ),
    "status_code": "DE",
    "metadata": {
        "weather_event": "tornado_warning",
        "hub_closure_duration_hours": 18,
        "affected_flights": 47,
    },
}

# ── 2. Package damaged in transit ─────────────────────────────────────────────
DAMAGED_PACKAGE = {
    "carrier": "UPS",
    "tracking_number": "UPS200000002",
    "event_type": "damaged",
    "event_timestamp": "2026-05-03T09:15:00Z",
    "location": "Louisville, KY — UPS Worldport",
    "description": (
        "Package sustained visible damage during unloading at Worldport. "
        "Outer carton crushed; contents may be compromised. Package held pending "
        "damage assessment. Customer notification required."
    ),
    "status_code": "DM",
    "metadata": {
        "damage_type": "crush",
        "assessment_required": True,
        "insurance_claim_eligible": True,
        "reported_by": "sort_facility_scan",
    },
}

# ── 3. Failed delivery — address issue ────────────────────────────────────────
FAILED_DELIVERY_ADDRESS = {
    "carrier": "USPS",
    "tracking_number": "USPS300000003",
    "event_type": "address_issue",
    "event_timestamp": "2026-05-03T11:45:00Z",
    "location": "Austin, TX 78701",
    "description": (
        "Delivery attempted but address could not be located. Apartment number "
        "missing from label. Carrier left notice; package returned to post office. "
        "Redelivery requires address correction."
    ),
    "status_code": "AG",
    "metadata": {
        "attempt_number": 1,
        "notice_left": True,
        "hold_until": "2026-05-10",
        "missing_field": "apartment_number",
    },
}

# ── 4. Customs hold ───────────────────────────────────────────────────────────
CUSTOMS_HOLD = {
    "carrier": "DHL",
    "tracking_number": "DHL400000004",
    "event_type": "customs_hold",
    "event_timestamp": "2026-05-03T07:00:00Z",
    "location": "JFK International Airport, NY — CBP Customs",
    "description": (
        "Shipment held by U.S. Customs and Border Protection for additional "
        "documentation review. Commercial invoice and HS tariff codes require "
        "verification. Estimated hold: 3-7 business days. Importer of record "
        "must provide supplemental documentation."
    ),
    "status_code": "CH",
    "metadata": {
        "customs_authority": "CBP",
        "hold_reason": "documentation_review",
        "documents_required": ["commercial_invoice", "hs_tariff_declaration"],
        "estimated_hold_days": 5,
        "bond_required": False,
    },
}

# ── 5. Lost package — no scans for 6 days ─────────────────────────────────────
LOST_PACKAGE = {
    "carrier": "FedEx",
    "tracking_number": "FX500000005",
    "event_type": "lost",
    "event_timestamp": "2026-05-03T16:00:00Z",
    "location": "Last scan: Dallas, TX — FedEx Ground facility",
    "description": (
        "Package has not received any scan activity for 6 days following "
        "departure from Dallas Ground facility. Expected delivery date was "
        "2026-04-29. System-generated alert triggered after 144 hours without "
        "a location update. Investigation initiated."
    ),
    "status_code": "LS",
    "metadata": {
        "last_scan_timestamp": "2026-04-27T10:22:00Z",
        "last_scan_location": "Dallas, TX",
        "days_without_scan": 6,
        "expected_delivery": "2026-04-29",
        "days_overdue": 4,
        "investigation_ticket": "INV-2026-88234",
    },
}

# ── Convenience dict ──────────────────────────────────────────────────────────
PAYLOADS: dict[str, dict] = {
    "weather_delay":         WEATHER_DELAY,
    "damaged_package":       DAMAGED_PACKAGE,
    "failed_delivery":       FAILED_DELIVERY_ADDRESS,
    "customs_hold":          CUSTOMS_HOLD,
    "lost_package":          LOST_PACKAGE,
}


# ── Quick send helper ─────────────────────────────────────────────────────────

async def send_all(base_url: str = "http://localhost:8000") -> None:
    """Fire all 5 payloads at the running server and print the results."""
    import asyncio
    import httpx

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        for name, payload in PAYLOADS.items():
            try:
                r = await client.post("/api/v1/webhook/tracking-update", json=payload)
                print(f"[{r.status_code}] {name}: {r.json()}")
            except Exception as exc:
                print(f"[ERR] {name}: {exc}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(send_all())
