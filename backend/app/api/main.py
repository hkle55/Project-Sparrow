"""Sparrow HTTP API. Also serves the web device simulator from /frontend.

Environment:
- SPARROW_CONFIG_TOML (contents) or SPARROW_CONFIG (path): commute profile (app/config.py)
- SPARROW_DB: SQLite path for validation data (default data/sparrow.sqlite)
- SPARROW_COLLECT=1: run the prediction collector in the background
- SPARROW_ACCESS_TOKEN: if set, every route except /health needs the token, given as the
  X-Sparrow-Token header, a ?key= query parameter (which also sets a cookie), or that cookie
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.device import DeviceOut, to_device
from app.api.schemas import CommuteOut
from app.config import REPO_ROOT, SparrowConfig, load_config
from app.service import commute_status
from app.simulation import SCENARIOS, simulate
from app.transit.client import TransitClient
from app.validation import store
from app.validation.analysis import analyze
from app.validation.collector import Collector
from app.validation.report import render

log = logging.getLogger("sparrow")
if not logging.getLogger().handlers:  # show app/collector logs next to uvicorn's
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
DEFAULT_DB = REPO_ROOT / "data" / "sparrow.sqlite"
TOKEN_COOKIE = "sparrow_token"


def now_utc() -> datetime:
    return datetime.now(UTC)


class ObservationIn(BaseModel):
    route: str = Field(max_length=8)
    stop_id: str = Field(max_length=16)
    arrived_at: float | None = None  # epoch seconds; default: now
    vehicle_id: str | None = Field(default=None, max_length=16)
    note: str | None = Field(default=None, max_length=200)


def create_app(
    config: SparrowConfig | None = None,
    client: TransitClient | None = None,
    *,
    db_path: str | Path | None = None,
    collect: bool | None = None,
    access_token: str | None = None,
) -> FastAPI:
    db_path = db_path or os.environ.get("SPARROW_DB") or DEFAULT_DB
    collect = collect if collect is not None else os.environ.get("SPARROW_COLLECT") == "1"
    token = access_token if access_token is not None else os.environ.get("SPARROW_ACCESS_TOKEN")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = config or load_config()
        options = [o for m in cfg.modes.values() for o in m.options]
        app.state.config = cfg
        app.state.options = options
        app.state.client = client or TransitClient(
            {o.route for o in options}, {o.stop_id for o in options}, cfg.settings.tz
        )
        app.state.db = store.connect(db_path)
        task = None
        if collect and options:
            task = asyncio.create_task(
                Collector(app.state.db, app.state.client, options).run()
            )
        log.info("Sparrow loaded %d modes (collector %s)", len(cfg.modes),
                 "on" if task else "off")
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        app.state.db.close()
        await app.state.client.aclose()

    app = FastAPI(title="Sparrow", version="0.1.0", lifespan=lifespan)

    if token:
        @app.middleware("http")
        async def require_token(request: Request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            given = (
                request.headers.get("x-sparrow-token")
                or request.query_params.get("key")
                or request.cookies.get(TOKEN_COOKIE)
                or ""
            )
            if not secrets.compare_digest(given.encode(), token.encode()):
                return JSONResponse({"detail": "access token required"}, status_code=401)
            response = await call_next(request)
            if request.query_params.get("key"):
                response.set_cookie(TOKEN_COOKIE, token, max_age=365 * 86400, httponly=True,
                                    secure=request.url.scheme == "https", samesite="lax")
            return response

    @app.middleware("http")
    async def revalidate_frontend(request: Request, call_next):
        # Pages and their JS/CSS must be re-checked on every load; otherwise a browser can
        # pair new HTML with yesterday's app.js after an update. Unchanged files are a cheap 304.
        response = await call_next(request)
        path = request.url.path
        if path in ("/", "/device", "/observe") or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

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

    @app.get("/api/v1/device", response_model=DeviceOut, response_model_exclude_none=True)
    async def device(
        mode: str = Query(default="work"), sim: str | None = Query(default=None)
    ) -> DeviceOut:
        """Compact payload for the physical Sparrow. V1 shows the work commute only."""
        return to_device(await commute(mode, sim))

    # --- prediction validation ---------------------------------------------------------

    @app.get("/api/v1/observe/options")
    def observe_options() -> list[dict]:
        cfg: SparrowConfig = app.state.config
        return [
            {"mode": m.key, "label": m.label, "route": o.route, "stop_id": o.stop_id,
             "stop_name": o.stop_name}
            for m in cfg.modes.values() for o in m.options
        ]

    @app.post("/api/v1/observations", status_code=201)
    def add_observation(ob: ObservationIn) -> dict:
        known = {(o.route, o.stop_id) for o in app.state.options}
        if (ob.route, ob.stop_id) not in known:
            raise HTTPException(422, "route/stop is not in the commute profile")
        now = now_utc().timestamp()
        arrived = ob.arrived_at if ob.arrived_at is not None else now
        if not (now - 86400 <= arrived <= now + 60):
            raise HTTPException(422, "arrived_at must be within the last 24 hours")
        oid = store.add_observation(
            app.state.db, recorded_at=now, arrived_at=arrived, route=ob.route,
            stop_id=ob.stop_id, vehicle_id=(ob.vehicle_id or "").strip() or None,
            note=(ob.note or "").strip() or None,
        )
        return {"id": oid, "arrived_at": arrived}

    @app.get("/api/v1/observations")
    def list_observations(limit: int = Query(default=20, ge=1, le=200)) -> list[dict]:
        rows = app.state.db.execute(
            "SELECT id, arrived_at, route, stop_id, vehicle_id, note FROM observations"
            " ORDER BY arrived_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    @app.delete("/api/v1/observations/{oid}", status_code=204)
    def delete_observation(oid: int) -> None:
        cur = app.state.db.execute("DELETE FROM observations WHERE id=?", (oid,))
        app.state.db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "no such observation")

    @app.get("/api/v1/validation/report", response_class=PlainTextResponse)
    def validation_report() -> str:
        cfg: SparrowConfig = app.state.config
        s = cfg.settings
        a = analyze(app.state.db, s.safety_buffer_min * 60, s.stale_after_s)
        return render(a, s.tz, now_utc())

    if FRONTEND.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND / "index.html")

        @app.get("/device", include_in_schema=False)
        def device_preview() -> FileResponse:
            return FileResponse(FRONTEND / "device.html")

        @app.get("/observe", include_in_schema=False)
        def observe_page() -> FileResponse:
            return FileResponse(FRONTEND / "observe.html")

        app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    return app


app = create_app()
