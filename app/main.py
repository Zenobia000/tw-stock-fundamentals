from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="tw-stock-fundamentals")
app.include_router(api_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if (WEB_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

if (WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
