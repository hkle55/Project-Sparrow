"""Sparrow HTTP API. Also serves the web device simulator from /frontend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.schemas import CommuteOut
from app.config import SparrowConfig, load_config
from app.service import commute_status
from app.simulation import SCENARIOS, simulate
from app.transit.client import TransitClient

log = logging.getLogger("sparrow")
FRONTEND = Path(__file__).resolve().parents[3] / "frontend"


def now_utc() -> datetime:
    return datetime.now(UTC)


def create_app(config: SparrowConfig | None = None, client: TransitClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = config or load_config()
        options = [o for m in cfg.modes.values() for o in m.options]
        app.state.config = cfg
        app.state.client = client or TransitClient(
            {o.route for o in options}, {o.stop_id for o in options}, cfg.settings.tz
        )
        log.info("Sparrow loaded %d modes", len(cfg.modes))
        yield
        await app.state.client.aclose()

    app = FastAPI(title="Sparrow", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/modes")
    def modes() -> list[dict]:
        cfg: SparrowConfig = app.state.config
        return [
            {"mode": m.key, "label": m.label, "configured": m.configured}
            for m in cfg.modes.values()
        ]

    @app.get("/api/v1/scenarios")
    def scenarios() -> list[dict]:
        return [{"id": k, "label": label} for k, (label, _) in SCENARIOS.items()]

    @app.get("/api/v1/commute/{mode}", response_model=CommuteOut, response_model_exclude_none=True)
    async def commute(mode: str, sim: str | None = Query(default=None)) -> CommuteOut:
        cfg: SparrowConfig = app.state.config
        m = cfg.modes.get(mode)
        if m is None:
            raise HTTPException(404, f"unknown mode {mode!r}")
        if sim is not None:
            if sim not in SCENARIOS:
                raise HTTPException(404, f"unknown scenario {sim!r}")
            return simulate(sim, m, cfg.settings, now_utc())
        return await commute_status(app.state.client, m, cfg.settings, lambda: now_utc())

    if FRONTEND.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND / "index.html")

        app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    return app


app = create_app()
