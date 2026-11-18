"""Keep application-import tests isolated from the developer's MySQL instance."""

import os
import tempfile
from pathlib import Path

import pytest


if "ANNOTATION_DATABASE_URL" not in os.environ:
    test_root = Path(tempfile.mkdtemp(prefix="annotation-tests-"))
    os.environ["ANNOTATION_DATABASE_URL"] = "sqlite:///" + (test_root / "suite.db").as_posix()


@pytest.fixture(autouse=True)
def isolate_auth_rate_limits():
    """Login attempts from one test must not throttle an unrelated test."""
    from backend import auth

    with auth._attempt_lock:
        auth._attempts.clear()
    yield
