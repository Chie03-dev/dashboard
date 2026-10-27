#!/usr/bin/env python3
"""
Standalone sync script for the dashboard.
Run via cron/systemd timer: */180 * * * * /path/to/venv/bin/python /path/to/sync.py

This script performs all sync operations:
- sync_games: Fetch free games from GamerPower and Epic Games
- sync_dev: Fetch dev items from HackerNews and GitHub
- build_digest: Generate daily LLM digest

Can also trigger Celery tasks:
  python sync.py --celery --only games    # Queue task via Celery
  python sync.py --celery --full-sync     # Queue full sync via Celery
"""

import argparse
import sys
import time
import uuid

from app.config import SYNC_MAX_RETRIES, SYNC_RETRY_BASE_DELAY, SYNC_RETRY_MAX_DELAY
from app.db import init_db
from app.http_clients import close_all_clients
from app.logging_conf import get_logger, set_correlation_id, setup_logging
from app.services import ai, devfeed, games as games_service
from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

# Try to import Celery tasks
try:
    from app.tasks import (
        sync_games_task,
        sync_dev_task,
        build_digest_task,
        run_full_sync,
    )
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

setup_logging(json_format=True)
logger = get_logger("sync")

SYNC_DURATION = Histogram("dashboard_sync_duration_seconds", "Sync job duration", ["job"])
SYNC_SUCCESS = Counter("dashboard_sync_success_total", "Sync job success", ["job"])
SYNC_FAILURE = Counter("dashboard_sync_failure_total", "Sync job failure", ["job", "error"])


def retry_with_backoff(func, *args, max_retries=3, base_delay=2.0, max_delay=60.0, **kwargs):
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


def run_sync_games():
    """Sync free games from all sources (standalone mode)."""
    logger.info("Starting games sync (standalone)")
    start = time.perf_counter()
    try:
        items = retry_with_backoff(
            games_service.sync_games,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="games").observe(duration)
        SYNC_SUCCESS.labels(job="games").inc()
        logger.info("Games sync completed", duration=duration, item_count=len(items))
        return True
    except Exception as e:
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="games").observe(duration)
        SYNC_FAILURE.labels(job="games", error=type(e).__name__).inc()
        logger.error("Games sync failed", error=str(e))
        return False


def run_sync_dev():
    """Sync dev feed items from HackerNews and GitHub (standalone mode)."""
    logger.info("Starting dev feed sync (standalone)")
    start = time.perf_counter()
    try:
        items = retry_with_backoff(
            devfeed.sync_dev,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="dev").observe(duration)
        SYNC_SUCCESS.labels(job="dev").inc()
        logger.info("Dev feed sync completed", duration=duration, item_count=len(items))
        return True
    except Exception as e:
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="dev").observe(duration)
        SYNC_FAILURE.labels(job="dev", error=type(e).__name__).inc()
        logger.error("Dev feed sync failed", error=str(e))
        return False


def run_build_digest():
    """Build daily LLM digest (standalone mode)."""
    logger.info("Starting digest build (standalone)")
    start = time.perf_counter()
    try:
        text = retry_with_backoff(
            ai.build_digest,
            max_retries=SYNC_MAX_RETRIES,
            base_delay=SYNC_RETRY_BASE_DELAY,
            max_delay=SYNC_RETRY_MAX_DELAY,
        )
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="digest").observe(duration)
        SYNC_SUCCESS.labels(job="digest").inc()
        logger.info("Digest build completed", duration=duration, text_length=len(text))
        return True
    except Exception as e:
        duration = time.perf_counter() - start
        SYNC_DURATION.labels(job="digest").observe(duration)
        SYNC_FAILURE.labels(job="digest", error=type(e).__name__).inc()
        logger.error("Digest build failed", error=str(e))
        return False


def queue_celery_task(task_name: str, *args, **kwargs):
    """Queue a Celery task and wait for result."""
    if not CELERY_AVAILABLE:
        raise RuntimeError("Celery not available. Install celery or run in standalone mode.")
    
    task_map = {
        "games": sync_games_task,
        "dev": sync_dev_task,
        "digest": build_digest_task,
        "full": run_full_sync,
    }
    
    if task_name not in task_map:
        raise ValueError(f"Unknown task: {task_name}")
    
    task = task_map[task_name]
    logger.info("Queueing Celery task", task=task_name)
    
    # Apply async and wait for result
    result = task.apply_async(args=args, kwargs=kwargs)
    logger.info("Task queued", task_id=result.id, task=task_name)
    
    # Wait for result with timeout
    try:
        return result.get(timeout=300)  # 5 minute timeout
    except Exception as e:
        logger.error("Celery task failed", task=task_name, error=str(e))
        raise


def main():
    parser = argparse.ArgumentParser(description="Dashboard sync script")
    parser.add_argument(
        "--only",
        choices=["games", "dev", "digest"],
        help="Run only a specific sync task",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        choices=["games", "dev", "digest"],
        default=[],
        help="Skip specific sync tasks",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize database before syncing",
    )
    parser.add_argument(
        "--pushgateway",
        help="Pushgateway URL for metrics (e.g., http://localhost:9091)",
    )
    parser.add_argument(
        "--correlation-id",
        help="Correlation ID for this sync run",
    )
    parser.add_argument(
        "--celery",
        action="store_true",
        help="Queue tasks via Celery instead of running standalone",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Run full sync (all tasks) via Celery",
    )
    args = parser.parse_args()

    cid = args.correlation_id or str(uuid.uuid4())[:8]
    set_correlation_id(cid)

    if args.init_db:
        logger.info("Initializing database")
        init_db()

    # Celery mode
    if args.celery or args.full_sync:
        if not CELERY_AVAILABLE:
            logger.error("Celery not available. Install celery or run without --celery flag.")
            return 1
        
        if args.full_sync:
            logger.info("Queueing full sync via Celery")
            try:
                result = queue_celery_task("full")
                logger.info("Full sync completed via Celery", result=result)
                return 0
            except Exception as e:
                logger.error("Full sync via Celery failed", error=str(e))
                return 1
        
        if args.only:
            logger.info("Queueing task via Celery", task=args.only)
            try:
                result = queue_celery_task(args.only)
                logger.info("Task completed via Celery", result=result)
                return 0
            except Exception as e:
                logger.error("Celery task failed", error=str(e))
                return 1
        
        # Default: queue all tasks
        logger.info("Queueing all tasks via Celery")
        try:
            result = queue_celery_task("full")
            logger.info("All tasks completed via Celery", result=result)
            return 0
        except Exception as e:
            logger.error("Celery tasks failed", error=str(e))
            return 1

    # Standalone mode (original behavior)
    tasks = []
    if args.only:
        if args.only == "games":
            tasks.append(("games", run_sync_games))
        elif args.only == "dev":
            tasks.append(("dev", run_sync_dev))
        elif args.only == "digest":
            tasks.append(("digest", run_build_digest))
    else:
        if "games" not in args.skip:
            tasks.append(("games", run_sync_games))
        if "dev" not in args.skip:
            tasks.append(("dev", run_sync_dev))
        if "digest" not in args.skip:
            tasks.append(("digest", run_build_digest))

    results = {}
    overall_start = time.perf_counter()

    for name, func in tasks:
        results[name] = func()

    total_duration = time.perf_counter() - overall_start

    logger.info("Sync summary", total_duration=total_duration)
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        logger.info("Task result", task=name, status=status)

    # Push metrics to Pushgateway if configured
    if args.pushgateway:
        try:
            registry = CollectorRegistry()
            SYNC_DURATION.labels(job="games").observe(0)  # ensure metric exists
            SYNC_DURATION.labels(job="dev").observe(0)
            SYNC_DURATION.labels(job="digest").observe(0)
            push_to_gateway(args.pushgateway, job="dashboard_sync", registry=registry)
            logger.info("Metrics pushed", pushgateway=args.pushgateway)
        except Exception as e:
            logger.warning("Failed to push metrics", error=str(e))

    close_all_clients()

    if all(results.values()):
        logger.info("All sync tasks completed successfully")
        return 0
    else:
        logger.error("Some sync tasks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())