"""Focused invariants for the local, source-only API mode."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# The application requires one configured LLM provider at import time. Tests never
# call it, but setting a harmless placeholder keeps application import deterministic.
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite://"

import server
from config.settings import Settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(server.settings, "source_only_mode", True)
    return TestClient(server.app)


def test_source_only_is_safe_by_default() -> None:
    config = Settings(anthropic_api_key="test-key", _env_file=None)
    assert config.source_only_mode is True
    assert config.api_host == "127.0.0.1"
    assert config.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert "*" not in config.cors_origins


def test_source_only_scraping_requires_no_llm_api_key() -> None:
    config = Settings(
        source_only_mode=True,
        anthropic_api_key="",
        deepseek_api_key="",
        openrouter_api_key="",
        ollama_base_url="",
        _env_file=None,
    )
    assert config.source_only_mode is True


def test_full_mode_still_requires_an_llm_provider() -> None:
    with pytest.raises(ValidationError, match="At least one LLM provider"):
        Settings(
            source_only_mode=False,
            anthropic_api_key="",
            deepseek_api_key="",
            openrouter_api_key="",
            ollama_base_url="",
            _env_file=None,
        )


def test_cors_defaults_allow_local_frontend_not_arbitrary_origins(client: TestClient) -> None:
    local = client.options(
        "/config",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"

    remote = client.options(
        "/config",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert remote.status_code == 400
    assert "access-control-allow-origin" not in remote.headers


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("delete", "/jobs/1", None),
        ("patch", "/jobs/1/stars", {"stars": 5}),
        ("patch", "/jobs/1/status", {"status": "shortlisted"}),
        ("post", "/run/purge-archived", {"max_score": 0.1, "dry_run": False}),
        (
            "post",
            "/run/apply/email",
            {
                "job_id": 1,
                "cover_letter": "hello",
                "recipient_email": "jobs@example.test",
                "dry_run": False,
            },
        ),
        ("post", "/run/apply/email", {"job_id": 1, "cover_letter": "preview", "dry_run": True}),
        ("post", "/run/analyze", {"llm": True}),
        ("post", "/run/enrich", {"rescore_llm": True}),
        ("post", "/companies/lookup", {"company": "Example AG"}),
        ("post", "/jobs/1/view", None),
        ("post", "/jobs/1/apply", {"method": "manual"}),
        ("post", "/jobs/1/events", {"event_type": "note", "note": "x"}),
    ],
)
def test_source_only_rejects_external_or_destructive_mutations(
    client: TestClient, method: str, path: str, json_body: dict | None
) -> None:
    response = client.request(method.upper(), path, json=json_body)
    assert response.status_code == 403
    assert response.json()["detail"] == "Operation disabled in source-only mode"


def test_source_only_still_allows_purge_preview(client: TestClient) -> None:
    # A purge dry-run is allowed through and returns an SSE response. Avoid consuming
    # its DB-backed generator: calling the route directly verifies the guard boundary.
    import asyncio

    response = asyncio.run(server.run_purge_archived(server.PurgeRequest(dry_run=True)))
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (server.SearchRequest, {"pages": 0}),
        (server.SearchRequest, {"pages": 11}),
        (server.SearchRequest, {"keywords": ["x"] * 21}),
        (server.EnrichRequest, {"limit": 501}),
        (server.EnrichRequest, {"concurrency": 21}),
        (server.AnalyzeRequest, {"limit": 1001}),
        (server.AnalyzeRequest, {"concurrency": 21}),
        (server.AnalyzeRequest, {"min_score": 1.01}),
        (server.CheckLinksRequest, {"concurrency": 21}),
        (server.CheckLinksRequest, {"timeout": 61}),
    ],
)
def test_request_resource_bounds_reject_excessive_values(model, kwargs) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_llm_shortlist_threshold_never_lowers_requested_score() -> None:
    request = server.AnalyzeRequest(llm=True, min_score=0.8)
    assert server.shortlist_threshold(request) == 0.8


def test_container_exposure_is_loopback_only() -> None:
    root = Path(__file__).resolve().parent.parent
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8765:8765"' in compose
    assert '"8765:8765"' not in compose

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "${API_HOST:-127.0.0.1}" in dockerfile
