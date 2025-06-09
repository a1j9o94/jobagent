# app/tools/reporting.py
from datetime import datetime, timedelta
from sqlmodel import select

from app.models import Application, ApplicationStatus, Role
from app.db import get_session_context


def generate_daily_report(profile_id: int) -> str:
    """Queries the DB for activity and returns a formatted string."""
    with get_session_context() as session:
        # Get yesterday's date range
        yesterday = datetime.now() - timedelta(days=1)
        start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = yesterday.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Query for applications submitted yesterday
        submitted_apps = session.exec(
            select(Application)
            .where(Application.profile_id == profile_id)
            .where(Application.submitted_at >= start_of_day)
            .where(Application.submitted_at <= end_of_day)
        ).all()

        # Query for new roles sourced yesterday
        new_roles = session.exec(
            select(Role)
            .where(Role.created_at >= start_of_day)
            .where(Role.created_at <= end_of_day)
        ).all()

        # Query for applications needing user input
        pending_apps = session.exec(
            select(Application)
            .where(Application.profile_id == profile_id)
            .where(Application.status == ApplicationStatus.NEEDS_USER_INFO)
        ).all()

        # Generate report
        report_lines = [
            "📈 Daily Job Application Report",
            f"📅 {yesterday.strftime('%Y-%m-%d')}",
            "",
            f"✅ Applications Submitted: {len(submitted_apps)}",
            f"🔍 New Roles Found: {len(new_roles)}",
            f"⏳ Pending Your Input: {len(pending_apps)}",
        ]

        if submitted_apps:
            report_lines.append("\n📋 Submitted Applications:")
            for app in submitted_apps:
                report_lines.append(f"  • {app.role.title} at {app.role.company.name}")

        if pending_apps:
            report_lines.append("\n❓ Applications Needing Your Input:")
            for app in pending_apps:
                report_lines.append(f"  • {app.role.title} at {app.role.company.name}")

        return "\n".join(report_lines) 