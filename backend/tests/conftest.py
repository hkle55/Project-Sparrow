import os

import pytest


@pytest.fixture(autouse=True)
def isolate_sparrow_env(monkeypatch):
    """Tests must not see the developer's or cloud environment's real Sparrow settings
    (e.g. SPARROW_CONFIG_JSON on the project-sparrow environment)."""
    for name in list(os.environ):
        if name.startswith("SPARROW_"):
            monkeypatch.delenv(name)
