from fastapi import APIRouter, Request, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional

from app.auth import get_current_tenant
from app.db import get_conn
from app.logging_conf import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class GitHubWebhookPayload(BaseModel):
    action: Optional[str] = None
    repository: Optional[dict] = None
    sender: Optional[dict] = None
    # Notification webhook
    notification: Optional[dict] = None


class EpicWebhookPayload(BaseModel):
    eventType: Optional[str] = None
    catalogNs: Optional[dict] = None
    offerId: Optional[str] = None
    # Free game promotion events
    promotion: Optional[dict] = None


@router.post("/github")
async def github_webhook(
    request: Request,
    payload: GitHubWebhookPayload,
    x_github_event: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    tenant_id: str = Depends(get_current_tenant),
):
    """
    GitHub webhook endpoint.
    Events: push, pull_request, issues, release, repository, notification
    """
    logger.info(
        "GitHub webhook received",
        event=x_github_event,
        delivery=x_github_delivery,
        tenant_id=tenant_id,
    )

    # Verify signature if configured
    # TODO: Implement HMAC verification with GITHUB_WEBHOOK_SECRET

    event_type = x_github_event or "unknown"

    if event_type == "push":
        # Handle push events - could trigger sync
        repo = payload.repository
        if repo:
            logger.info("Push to repo", repo=repo.get("full_name"), tenant_id=tenant_id)

    elif event_type == "release":
        # New release - could be relevant for dev feed
        repo = payload.repository
        if repo:
            logger.info("New release", repo=repo.get("full_name"), tenant_id=tenant_id)

    elif event_type == "notification":
        # GitHub notification - could sync dev feed immediately
        logger.info("Notification event", tenant_id=tenant_id)

    # Could trigger immediate sync_dev_task here
    # from app.tasks import sync_dev_task
    # sync_dev_task.delay()

    return {"status": "received", "event": event_type}


@router.post("/epic")
async def epic_webhook(
    request: Request,
    payload: EpicWebhookPayload,
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Epic Games webhook endpoint.
    Events: free_game_promotion, offer_changed, catalog_updated
    """
    logger.info(
        "Epic webhook received",
        event_type=payload.eventType,
        offer_id=payload.offerId,
        tenant_id=tenant_id,
    )

    event_type = payload.eventType or "unknown"

    if event_type in ("free_game_promotion", "offer_changed"):
        # Free game promotion started/ended - trigger games sync
        logger.info("Free game promotion event", offer_id=payload.offerId, tenant_id=tenant_id)
        # Could trigger immediate sync_games_task here
        # from app.tasks import sync_games_task
        # sync_games_task.delay()

    return {"status": "received", "event": event_type}


@router.post("/generic")
async def generic_webhook(
    request: Request,
    source: str,
    payload: dict,
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Generic webhook endpoint for custom integrations.
    """
    logger.info("Generic webhook received", source=source, tenant_id=tenant_id)
    return {"status": "received", "source": source}