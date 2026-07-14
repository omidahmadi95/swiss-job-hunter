from datetime import datetime
from types import SimpleNamespace

from tools.export_jack import EXPORT_FIELDS, job_to_record, write_records


def test_job_to_record_exports_only_normalized_fields(tmp_path):
    job = SimpleNamespace(
        id=42,
        source_job_id="abc-123",
        title="Junior Software Engineer",
        company="Example AG",
        location="Zürich",
        url="https://example.ch/jobs/42",
        source="jobs.ch",
        description="Build and support software.",
        posted_at=datetime(2026, 7, 14, 8, 30),
        employment_type="80-100%",
        match_score=0.74,
        direction="java_fullstack",
        secret_value="must not leak",
    )

    record = job_to_record(job)

    assert set(record) == set(EXPORT_FIELDS)
    assert record["source_id"] == "jobs.ch:abc-123"
    assert record["posted_at"] == "2026-07-14T08:30:00"
    assert record["match_score"] == 0.74
    assert "secret_value" not in record


def test_job_to_record_falls_back_to_database_id():
    job = SimpleNamespace(
        id=7,
        source_job_id=None,
        title="QA Engineer",
        company="Example AG",
        location="Bern",
        url="https://example.ch/jobs/7",
        source="jobup.ch",
        description="Test systems.",
        posted_at=None,
        employment_type=None,
        match_score=None,
        direction=None,
    )

    record = job_to_record(job)

    assert record["source_id"] == "jobup.ch:7"
    assert record["posted_at"] is None
    assert record["match_score"] is None


def test_write_records_creates_valid_json_atomically(tmp_path):
    output = tmp_path / "jack-export.json"
    records = [{field: None for field in EXPORT_FIELDS}]
    records[0].update(
        source_id="jobs.ch:1",
        title="Support Engineer",
        company="Example AG",
        url="https://example.ch/jobs/1",
        source="jobs.ch",
    )

    count = write_records(records, output)

    assert count == 1
    assert output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    text = output.read_text(encoding="utf-8")
    assert '"source_id": "jobs.ch:1"' in text
