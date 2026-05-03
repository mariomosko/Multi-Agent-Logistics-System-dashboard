from sqlalchemy.ext.asyncio import AsyncSession

from app.core.coordinator import AgentCoordinator
from app.models import ShipmentException
from app.schemas import WorkflowResult

# Module-level singleton — the coordinator itself holds no mutable state
# so it is safe to share across all requests.
_coordinator = AgentCoordinator()


async def run_exception_workflow(
    exception: ShipmentException,
    db: AsyncSession,
) -> WorkflowResult:
    return await _coordinator.run(exception, db)
