import logging
import time
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from app.config import SYNC_MAX_RETRIES, SYNC_RETRY_BASE_DELAY, SYNC_RETRY_MAX_DELAY
from app.db import init_db
from app.http_clients import close_all_clients
from app.logging_conf import get_logger, set_correlation_id, setup_logging

# Setup logging for Celery workers
setup_logging(json_format=True)
logger = get_logger("celery.tasks")


def retry_with_backoff(task, max_retries=3, base_delay=2.0, max_delay=60.0, *args, **kwargs):
    """Execute a function with exponential backoff retry logic."""
    last_exception = None
    for attempt in range(max_retries):
        try:
            return task(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    task.__name__,
                    e,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    max_retries,
                    task.__name__,
                    e,
                )
    raise last_exception


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def sync_games_task(self):
    """Sync free games from all sources."""
    cid = set_correlation_id()
    logger.info("Starting games sync task", task_id=self.request.id, correlation_id=cid)
    start = time.perf_counter()
    
    try:
        # Import here to avoid circular imports
        from app.services import games as games_service
        
        items = retry_with_backoff(
            games_service.sync_games,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        logger.info("Games sync completed", duration=duration, item_count=len(items), correlation_id=cid)
        return {"status": "success", "items_synced": len(items), "duration": duration}
    except Exception as e:
        duration = time.perf_counter() - start
        logger.error("Games sync failed", error=str(e), duration=duration, correlation_id=cid)
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def sync_dev_task(self):
    """Sync dev feed items from HackerNews and GitHub."""
    cid = set_correlation_id()
    logger.info("Starting dev feed sync task", task_id=self.request.id, correlation_id=cid)
    start = time.perf_counter()
    
    try:
        from app.services import devfeed
        
        items = retry_with_backoff(
            devfeed.sync_dev,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        logger.info("Dev feed sync completed", duration=duration, item_count=len(items), correlation_id=cid)
        return {"status": "success", "items_synced": len(items), "duration": duration}
    except Exception as e:
        duration = time.perf_counter() - start
        logger.error("Dev feed sync failed", error=str(e), duration=duration, correlation_id=cid)
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def build_digest_task(self):
    """Build daily LLM digest."""
    cid = set_correlation_id()
    logger.info("Starting digest build task", task_id=self.request.id, correlation_id=cid)
    start = time.perf_counter()
    
    try:
        from app.services import ai
        
        text = retry_with_backoff(
            ai.build_digest,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        logger.info("Digest build completed", duration=duration, text_length=len(text), correlation_id=cid)
        return {"status": "success", "text_length": len(text), "duration": duration}
    except Exception as e:
        duration = time.perf_counter() - start
        logger.error("Digest build failed", error=str(e), duration=duration, correlation_id=cid)
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def send_notification_task(self, notification_type: str, game_data: dict):
    """Send notification (email + ntfy) for game events."""
    cid = set_correlation_id()
    logger.info("Sending notification", notification_type=notification_type, game=game_data.get("title"), correlation_id=cid)
    
    try:
        from app.services import notifier
        
        if notification_type == "new_game":
            notifier.notify_new_game(game_data)
        elif notification_type == "wishlist":
            notifier.notify_wishlist(game_data)
        elif notification_type == "reminder":
            notifier.notify_reminder(game_data)
        else:
            logger.warning("Unknown notification type", notification_type=notification_type, correlation_id=cid)
            return {"status": "skipped", "reason": "unknown_type"}
        
        logger.info("Notification sent", notification_type=notification_type, correlation_id=cid)
        return {"status": "success", "notification_type": notification_type}
    except Exception as e:
        logger.error("Notification failed", notification_type=notification_type, error=str(e), correlation_id=cid)
        raise


@shared_task
def run_full_sync():
    """Run all sync tasks in sequence (for manual trigger)."""
    cid = set_correlation_id()
    logger.info("Starting full sync", correlation_id=cid)
    
    results = {}
    
    # Run games sync
    try:
        result = sync_games_task.apply()
        results["games"] = result.get()
    except Exception as e:
        results["games"] = {"status": "failed", "error": str(e)}
        logger.error("Games sync failed in full sync", error=str(e), correlation_id=cid)
    
    # Run dev sync
    try:
        result = sync_dev_task.apply()
        results["dev"] = result.get()
    except Exception as e:
        results["dev"] = {"status": "failed", "error": str(e)}
        logger.error("Dev sync failed in full sync", error=str(e), correlation_id=cid)
    
    # Run digest build
    try:
        result = build_digest_task.apply()
        results["digest"] = result.get()
    except Exception as e:
        results["digest"] = {"status": "failed", "error": str(e)}
        logger.error("Digest build failed in full sync", error=str(e), correlation_id=cid)
    
    logger.info("Full sync completed", results=results, correlation_id=cid)
    return results


# Initialize DB when module is loaded (for worker startup)
init_db()
logger.info("Celery tasks module loaded, DB initialized")