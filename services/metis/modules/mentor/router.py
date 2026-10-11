from __future__ import annotations

import asyncio
import json
import threading
import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from metis.core.audit import correlation_id
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import User
from metis.modules.mentor import schemas, service

router = APIRouter(tags=["mentor"])


@router.post("/projects/{project_id}/mentor/answers", response_model=schemas.AnswerOut)
def ask(project_id: uuid.UUID, data: schemas.AskIn, user: User = Depends(current_user)) -> schemas.AnswerOut:
    return service.ask(user.id, project_id, data)


@router.post("/projects/{project_id}/mentor/stream")
async def ask_stream(project_id: uuid.UUID, data: schemas.AskIn, user: User = Depends(current_user)) -> StreamingResponse:
    """İlerleme olayları: progress(searching|verifying) → sources → result | error. Doğrulanmamış token gönderilmez."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
    cid = correlation_id.get()

    def emit(event: str, payload: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

    def worker() -> None:
        correlation_id.set(cid)
        try:
            service.ask(user.id, project_id, data, emit)
        except AppError as exc:
            emit("error", exc.envelope(cid)["error"])
        except Exception:  # noqa: BLE001
            emit("error", AppError("INTERNAL", "internal error").envelope(cid)["error"])
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():  # noqa: ANN202
        seq = 0
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if item is None:
                break
            seq += 1
            event, payload = item
            yield f"id: {seq}\nevent: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/projects/{project_id}/answers", response_model=list[schemas.AnswerListItem])
def list_answers(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[schemas.AnswerListItem]:
    return service.list_answers(db, user, project_id)


@router.get("/answers/{answer_id}", response_model=schemas.AnswerOut)
def get_answer(answer_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.AnswerOut:
    return service.answer_out(db, user, service.get_answer(db, user, answer_id))


@router.delete("/answers/{answer_id}", status_code=204)
def delete_answer(answer_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_answer(db, user, answer_id)
    return Response(status_code=204)


@router.post("/answers/{answer_id}/feedback", status_code=204)
def feedback(answer_id: uuid.UUID, data: schemas.FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.feedback(db, user, answer_id, data)
    return Response(status_code=204)


@router.get("/answers/{answer_id}/draft-prefill", response_model=schemas.DraftPrefill)
def draft_prefill(answer_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.DraftPrefill:
    return service.draft_prefill(db, user, answer_id)
