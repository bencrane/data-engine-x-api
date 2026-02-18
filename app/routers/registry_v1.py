from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.registry.loader import get_all_operations
from app.routers._responses import DataEnvelope

router = APIRouter()


class RegistryOperationsRequest(BaseModel):
    entity_type: str | None = None
    produces_field: str | None = None


@router.post("/operations", response_model=DataEnvelope)
async def list_registry_operations(payload: RegistryOperationsRequest) -> DataEnvelope:
    operations = get_all_operations()

    if payload.entity_type:
        operations = [op for op in operations if op.get("entity_type") == payload.entity_type]

    if payload.produces_field:
        operations = [
            op
            for op in operations
            if isinstance(op.get("produces"), list) and payload.produces_field in op["produces"]
        ]

    return DataEnvelope(data={"operations": operations, "count": len(operations)})
