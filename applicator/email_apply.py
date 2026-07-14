"""
Email application module.
Sends cover letter + CV PDF to a target email address.
Requires explicit user confirmation before sending.
"""
from __future__ import annotations

import asyncio
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import aiosmtplib

from config.settings import settings
from db.models import Application, ApplicationStatus, Job
from db.session import get_session


async def send_application(
    job: Job,
    cover_letter: str,
    recipient_email: str,
    cv_pdf_path: Optional[Path] = None,
    dry_run: bool = True,
) -> bool:
    """
    Send a job application email.

    Args:
        dry_run: If True, print the email but don't actually send it.
                 Always True by default — pass False explicitly to send.
    """
    if settings.source_only_mode and not dry_run:
        raise PermissionError("Real email sending is disabled in source-only mode")

    cv_path = cv_pdf_path or settings.cv_pdf_path

    # Build email
    msg = MIMEMultipart()
    msg["From"] = f"{settings.apply_from_name} <{settings.apply_from_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = f"Application: {job.title} — {settings.apply_from_name}"

    msg.attach(MIMEText(cover_letter, "plain", "utf-8"))

    # Attach CV if it exists
    if cv_path.exists():
        with open(cv_path, "rb") as f:
            cv_data = f.read()
        attachment = MIMEApplication(cv_data, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"CV_{settings.apply_from_name.replace(' ', '_')}.pdf",
        )
        msg.attach(attachment)
    else:
        print(f"[warning] CV PDF not found at {cv_path} — sending without attachment")

    if dry_run:
        print("=" * 60)
        print("[DRY RUN] Email would be sent:")
        print(f"  To: {recipient_email}")
        print(f"  Subject: {msg['Subject']}")
        print(f"  CV attached: {cv_path.exists()}")
        print("-" * 60)
        print(cover_letter[:500] + "...")
        print("=" * 60)
        return True

    # Actually send
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=True,
            username=settings.smtp_user,
            password=settings.smtp_password,
        )
        _record_application(job, cover_letter, "email", ApplicationStatus.SENT)
        print(f"✓ Application sent to {recipient_email}")
        return True

    except Exception as exc:
        _record_application(job, cover_letter, "email", ApplicationStatus.FAILED)
        print(f"✗ Failed to send to {recipient_email}: {exc}")
        return False


def _record_application(
    job: Job, cover_letter: str, method: str, status: ApplicationStatus
) -> None:
    from datetime import datetime
    with get_session() as session:
        app = session.query(Application).filter(Application.job_id == job.id).first()
        if not app:
            app = Application(job_id=job.id)
            session.add(app)
        app.cover_letter = cover_letter
        app.apply_method = method
        app.status = status
        if status == ApplicationStatus.SENT:
            app.applied_at = datetime.utcnow()
