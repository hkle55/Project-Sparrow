#!/usr/bin/env python3
"""Analyze collected predictions and write a Markdown report to data/reports/ (gitignored).

    .venv/bin/python scripts/validation_report.py
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.main import DEFAULT_DB  # noqa: E402
from app.config import REPO_ROOT, load_config  # noqa: E402
from app.validation import store  # noqa: E402
from app.validation.analysis import analyze  # noqa: E402
from app.validation.report import render  # noqa: E402

cfg = load_config()
s = cfg.settings
db = store.connect(os.environ.get("SPARROW_DB") or DEFAULT_DB)
now = datetime.now(UTC)
text = render(analyze(db, s.safety_buffer_min * 60, s.stale_after_s), s.tz, now)
out = REPO_ROOT / "data" / "reports" / f"validation-{now.astimezone(s.tz):%Y%m%d-%H%M}.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text)
print(text)
print(f"\nwritten to {out}")
