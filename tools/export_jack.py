"""Export reviewed job-source records for Jack's dry-run lead importer.

This module intentionally exports listings only. It never reads or writes Jack's
application or RAV data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, Sequence

EXPORT_FIELDS = (
    "source_id",
    "title",
    "company",
    "location",
    "url",
    "source",
    "description",
    "posted_at",
    "employment_type",
    "match_score",
    "direction",
)
DEFAULT_STATUSES = ("new", "analyzed", "shortlisted")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def job_to_record(job: Any) -> dict[str, Any]:
    """Return the small, version-independent record accepted by Jack."""
    source = str(job.source or "").strip()
    source_job_id = getattr(job, "source_job_id", None) or getattr(job, "id")
    return {
        "source_id": f"{source}:{source_job_id}",
        "title": str(job.title or "").strip(),
        "company": str(job.company or "").strip(),
        "location": str(job.location or "").strip(),
        "url": str(job.url or "").strip(),
        "source": source,
        "description": str(job.description or "").strip(),
        "posted_at": _iso(getattr(job, "posted_at", None)),
        "employment_type": getattr(job, "employment_type", None),
        "match_score": getattr(job, "match_score", None),
        "direction": getattr(job, "direction", None),
    }


def write_records(records: Iterable[dict[str, Any]], output: Path) -> int:
    """Atomically write normalized records and return their count."""
    normalized = [{field: record.get(field) for field in EXPORT_FIELDS} for record in records]
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    return len(normalized)


def load_records(
    statuses: Sequence[str] = DEFAULT_STATUSES,
    min_score: float | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Read exportable listings from Swiss Job Hunter's database."""
    if not 1 <= limit <= 5000:
        raise ValueError("limit must be between 1 and 5000")
    if min_score is not None and not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0 and 1")

    from db.models import Job, JobStatus
    from db.session import get_session, init_db

    valid = {status.value for status in JobStatus}
    unknown = set(statuses) - valid
    if unknown:
        raise ValueError(f"unknown status: {', '.join(sorted(unknown))}")

    init_db()
    with get_session() as session:
        query = session.query(Job).filter(Job.status.in_(list(statuses)))
        if min_score is not None:
            query = query.filter(Job.match_score.isnot(None), Job.match_score >= min_score)
        jobs = query.order_by(Job.scraped_at.desc()).limit(limit).all()
        return [job_to_record(job) for job in jobs]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export normalized listings for Jack")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", action="append", dest="statuses", choices=DEFAULT_STATUSES)
    parser.add_argument("--min-score", type=float)
    parser.add_argument("--limit", type=int, default=500)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = tuple(args.statuses) if args.statuses else DEFAULT_STATUSES
    records = load_records(statuses=statuses, min_score=args.min_score, limit=args.limit)
    count = write_records(records, args.output)
    print(json.dumps({"exported": count, "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
