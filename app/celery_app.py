from celery import Celery
from celery.schedules import crontab

from app.config import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_TASK_SERIALIZER,
    CELERY_RESULT_SERIALIZER,
    CELERY_ACCEPT_CONTENT,
    CELERY_TIMEZONE,
    CELERY_ENABLE_UTC,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_WORKER_PREFETCH_MULTIPLIER,
    CELERY_WORKER_MAX_TASKS_PER_CHILD,
    CELERY_BEAT_SCHEDULE,
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
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")