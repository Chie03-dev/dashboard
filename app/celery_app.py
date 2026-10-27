from celery import Celery
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_ready,
    worker_shutdown,
)
from prometheus_client import Counter, Gauge, Histogram

from app.config import (
    CELERY_ACCEPT_CONTENT,
    CELERY_BEAT_SCHEDULE,
    CELERY_BROKER_URL,
    CELERY_ENABLE_UTC,
    CELERY_RESULT_BACKEND,
    CELERY_RESULT_SERIALIZER,
    CELERY_TASK_SERIALIZER,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TIMEZONE,
    CELERY_WORKER_MAX_TASKS_PER_CHILD,
    CELERY_WORKER_PREFETCH_MULTIPLIER,
)

# Prometheus metrics for Celery
CELERY_TASKS_TOTAL = Counter(
    "celery_tasks_total", "Total Celery tasks", ["task", "status"]
)
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds", "Celery task duration", ["task"]
)
CELERY_WORKER_COUNT = Gauge(
    "celery_workers", "Number of Celery workers"
)
CELERY_QUEUE_LENGTH = Gauge(
    "celery_queue_length", "Celery queue length", ["queue"]
)

celery_app = Celery("dashboard")

celery_app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    task_serializer=CELERY_TASK_SERIALIZER,
    result_serializer=CELERY_RESULT_SERIALIZER,
    accept_content=CELERY_ACCEPT_CONTENT,
    timezone=CELERY_TIMEZONE,
    enable_utc=CELERY_ENABLE_UTC,
    task_track_started=CELERY_TASK_TRACK_STARTED,
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
    worker_prefetch_multiplier=CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
    beat_schedule=CELERY_BEAT_SCHEDULE,
    task_routes={
        "app.tasks.sync_games_task": {"queue": "sync"},
        "app.tasks.sync_dev_task": {"queue": "sync"},
        "app.tasks.build_digest_task": {"queue": "sync"},
        "app.tasks.send_notification_task": {"queue": "notifications"},
    },
    task_default_queue="default",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])


# Signal handlers for metrics
@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    CELERY_WORKER_COUNT.inc()
    print(f"Worker {sender.hostname} ready")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    CELERY_WORKER_COUNT.dec()
    print(f"Worker {sender.hostname} shutting down")


_task_start_times = {}


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    import time
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kw):
    import time
    if task_id in _task_start_times:
        duration = time.perf_counter() - _task_start_times.pop(task_id)
        CELERY_TASK_DURATION.labels(task=task.name).observe(duration)
        CELERY_TASKS_TOTAL.labels(task=task.name, status=state).inc()


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kw):
    task = sender
    CELERY_TASKS_TOTAL.labels(task=task.name, status="FAILURE").inc()


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, einfo=None, **kw):
    task = sender
    CELERY_TASKS_TOTAL.labels(task=task.name, status="RETRY").inc()


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")