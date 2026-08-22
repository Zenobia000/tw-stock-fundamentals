from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.db.connection import get_connection
from app.ingest import refresh_market, refresh_stock

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def _scheduled_refresh() -> None:
    """Refresh all locally tracked stocks after the Taiwan cash market closes."""
    conn = get_connection()
    try:
        codes = [
            row[0] for row in conn.execute("SELECT code FROM stocks ORDER BY code")
        ]
    finally:
        conn.close()
    refresh_market()
    for code in codes:
        refresh_stock(code)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(
        _scheduled_refresh,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone="Asia/Taipei"),
        id="weekday-market-refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    _app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="tw-stock-fundamentals", lifespan=lifespan)
app.include_router(api_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if (WEB_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

if (WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
