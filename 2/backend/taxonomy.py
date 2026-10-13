from __future__ import annotations

from typing import Literal

Category = Literal[
    "access_accounts",
    "hardware",
    "software_apps",
    "network",
    "security",
    "data_backup",
    "infrastructure",
    "feature_request",
    "other",
]

Urgency = Literal["critical", "high", "medium", "low"]
Status = Literal["new", "in_progress", "waiting", "done"]

CATEGORIES: list[str] = list(Category.__args__)  # type: ignore[attr-defined]
URGENCIES: list[str] = list(Urgency.__args__)  # type: ignore[attr-defined]
STATUSES: list[str] = list(Status.__args__)  # type: ignore[attr-defined]

CATEGORY_LABELS: dict[str, str] = {
    "access_accounts": "Access & accounts",
    "hardware": "Hardware",
    "software_apps": "Software & apps",
    "network": "Network",
    "security": "Security",
    "data_backup": "Data & backup",
    "infrastructure": "Infrastructure",
    "feature_request": "Feature / project",
    "other": "Other",
}

URGENCY_LABELS: dict[str, str] = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "in_progress": "In progress",
    "waiting": "Waiting",
    "done": "Done",
}

URGENCY_RUBRIC = """
critical — production or many people blocked right now; suspected breach; data loss in progress; safety risk. Respond immediately.
high — one person cannot do their job; SLA at risk today; outage with a workaround that is painful. Same business day.
medium — degraded but workable; needs a fix this week; scheduled change. A few days.
low — question, enhancement, documentation, or nice-to-have. Backlog.
"""

CATEGORY_RUBRIC = """
access_accounts — logins, MFA, permissions, SSO, leavers/joiners, shared mailboxes.
hardware — laptops, phones, peripherals, desks, printers, broken screens.
software_apps — install, license, SaaS, crashing apps, browser, email client.
network — wifi, VPN, DNS, can't reach an internal site, slow connection.
security — phishing, malware, lost device, suspicious access, vulnerability.
data_backup — restore, export, lost files, database dump, retention.
infrastructure — servers, cloud, CI, deploy, environments, DNS records, certificates.
feature_request — new capability, integration, or project rather than a break/fix.
other — does not fit the rest; still pick this rather than forcing a mismatch.
"""
