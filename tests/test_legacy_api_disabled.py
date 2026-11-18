"""The retired records-based API must never become reachable again."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend import auth, models as m
from backend.main import app, engine


@pytest.fixture
def authenticated_client():
    username = "legacy" + uuid.uuid4().hex
    password = "StrongTest123"
    with engine.begin() as connection:
        connection.execute(
            m.users.insert().values(
                username=username,
                display_name="旧接口测试",
                password_hash=auth.password_hash(password),
                role="ANNOTATOR",
                active=True,
            )
        )
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
        yield client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/state"),
        ("post", "/api/import"),
        ("get", "/api/dicom/1.2.3"),
        ("put", "/api/assessments"),
        ("delete", "/api/boxes/obsolete"),
        ("get", "/api/export/json"),
        ("post", "/api/project/save"),
        ("delete", "/api/imported/studies/obsolete"),
        ("post", "/api/imported/restore/obsolete"),
        ("delete", "/api/slices/obsolete/boxes"),
        ("get", "/api/browser-project/obsolete"),
        ("put", "/api/browser-project/obsolete"),
    ],
)
def test_retired_routes_are_not_registered(authenticated_client, method, path):
    response = getattr(authenticated_client, method)(path)
    assert response.status_code == 404


def test_public_registration_remains_closed():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "someone", "password": "StrongTest123"},
        )
    assert response.status_code == 403
