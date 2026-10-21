import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from payload_cache.schemas import PayloadCreated, PayloadRequest, PayloadResponse
from payload_cache.service.cache import PayloadService
from payload_cache.service.db import session_scope

router = APIRouter()


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.engine)


def get_payload_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> PayloadService:
    return PayloadService(session, request.app.state.transformer, ttl=request.app.state.cache_ttl)


ServiceDep = Annotated[PayloadService, Depends(get_payload_service)]


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/payload",
    status_code=status.HTTP_201_CREATED,
    tags=["payload"],
    responses={status.HTTP_200_OK: {"model": PayloadCreated, "description": "Payload reused"}},
)
def create_payload(body: PayloadRequest, response: Response, service: ServiceDep) -> PayloadCreated:
    """Generate a payload, or return the identifier of an identical earlier one."""
    payload, created = service.create_payload(body.list_1, body.list_2)
    # 200 vs 201 tells clients whether anything new was generated, while the
    # body stays the same shape either way.
    if not created:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = f"/payload/{payload.id}"
    message = "Payload created" if created else "Payload already exists"
    return PayloadCreated(id=payload.id, message=message)


@router.get("/payload/{payload_id}", tags=["payload"])
def read_payload(payload_id: uuid.UUID, service: ServiceDep) -> PayloadResponse:
    payload = service.get_payload(payload_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payload not found")
    return PayloadResponse(output=payload.output)
