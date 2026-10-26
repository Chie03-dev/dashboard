import logging

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import SCHEDULER_HOURS
from app.db import init_db
from app.routes import chat, dev, digest, games, settings
from app.services import ai, devfeed, games as games_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Dashboard")

app.include_router(games.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(dev.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")


def run_job():
    try:
        games_service.sync_games()
    except Exception as e:
        logger.error("sync_games job error: %s", e)
    try:
        devfeed.sync_dev()
    except Exception as e:
        logger.error("sync_dev job error: %s", e)
    try:
        ai.get_digest()
    except Exception as e:
        logger.error("digest job error: %s", e)


@app.on_event("startup")
def startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_job, "interval", hours=SCHEDULER_HOURS, next_run_time=__import__("datetime").datetime.now())
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started")


@app.on_event("shutdown")
def shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown(wait=False)
