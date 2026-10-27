import time
from typing import Callable, Any

from celery import shared_task

from app.config import SYNC_MAX_RETRIES, SYNC_RETRY_BASE_DELAY, SYNC_RETRY_MAX_DELAY
from app.db import init_db
from app.fetchers import dead_letter_queue, fetcher_registry
from app.logging_conf import get_logger, set_correlation_id, setup_logging

# Setup logging for Celery workers
setup_logging(json_format=True)
logger = get_logger("celery.tasks")


def retry_with_backoff(func: Callable, *args, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0, **kwargs) -> Any:
    """Execute a function with exponential backoff retry logic."""
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    func.__name__,
                    e,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    max_retries,
                    func.__name__,
                    e,
                )
    raise last_exception


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def sync_games_task(self):
    """Sync free games from all sources using fetcher architecture."""
    cid = set_correlation_id()
    logger.info("Starting games sync task", task_id=self.request.id, correlation_id=cid)
    start = time.perf_counter()
    
    try:
        # Use fetcher registry for games
        gamerpower_fetcher = fetcher_registry.get("gamerpower")
        epic_fetcher = fetcher_registry.get("epic")
        
        if not gamerpower_fetcher or not epic_fetcher:
            raise RuntimeError("Game fetchers not registered")
        
        # Fetch from both sources
        gp_result = gamerpower_fetcher.fetch_with_retry()
        epic_result = epic_fetcher.fetch_with_retry()
        
        all_items = []
        if gp_result.status.value in ("success", "skipped"):
            all_items.extend(gp_result.items)
        if epic_result.status.value in ("success", "skipped"):
            all_items.extend(epic_result.items)
        
        # Store items in database
        from app.services import games as games_service
        stored_count = 0
        for item in all_items:
            try:
                games_service.sync_games()  # This will handle deduplication
                stored_count += 1
            except Exception as e:
                logger.warning("Failed to store game item", error=str(e))
        
        duration = time.perf_counter() - start
        logger.info("Games sync completed", duration=duration, items_fetched=len(all_items), items_stored=stored_count, correlation_id=cid)
        
        # Check dead letter queue
        dlq_count = len(dead_letter_queue)
        if dlq_count > 0:
            logger.warning("Dead letter queue has entries", count=dlq_count)
        
        return {"status": "success", "items_fetched": len(all_items), "items_stored": stored_count, "duration": duration, "dead_letter_count": dlq_count}
    except Exception as e:
        duration = time.perf_counter() - start
        logger.error("Games sync failed", error=str(e), duration=duration, correlation_id=cid)
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def sync_dev_task(self):
    """Sync dev feed items from HackerNews and GitHub using fetcher architecture."""
    cid = set_correlation_id()
    logger.info("Starting dev feed sync task", task_id=self.request.id, correlation_id=cid)
    start = time.perf_counter()
    
    try:
        # Use fetcher registry for dev sources
        hn_fetcher = fetcher_registry.get("hackernews")
        github_fetcher = fetcher_registry.get("github")
        
        if not hn_fetcher:
            raise RuntimeError("HackerNews fetcher not registered")
        
        # Fetch from sources
        hn_result = hn_fetcher.fetch_with_retry()
        github_result = github_fetcher.fetch_with_retry() if github_fetcher else None
        
        all_items = []
        if hn_result.status.value in ("success", "skipped"):
            all_items.extend(hn_result.items)
        if github_result and github_result.status.value in ("success", "skipped"):
            all_items.extend(github_result.items)
        
        # Store items in database
        from app.services import devfeed
        stored_count = 0
        for item in all_items:
            try:
                devfeed.sync_dev()  # This will handle deduplication
                stored_count += 1
            except Exception as e:
                logger.warning("Failed to store dev item", error=str(e))
        
        duration = time.perf_counter() - start
        logger.info("Dev feed sync completed", duration=duration, items_fetched=len(all_items), items_stored=stored_count, correlation_id=cid)
        
        # Check dead letter queue
        dlq_count = len(dead_letter_queue)
        if dlq_count > 0:
            logger.warning("Dead letter queue has entries", count=dlq_count)
        
        return {"status": "success", "items_fetched": len(all_items), "items_stored": stored_count, "duration": duration, "dead_letter_count": dlq_count}
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