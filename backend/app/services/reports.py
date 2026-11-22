"""Export provider investigation reports as Markdown or CSV."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from app.models import INVESTIGATION_SECTIONS, Provider, ProviderInvestigation


def completion(inv: ProviderInvestigation) -> float:
    filled = sum(1 for key, _ in INVESTIGATION_SECTIONS if (getattr(inv, key) or "").strip())
    return round(100 * filled / len(INVESTIGATION_SECTIONS), 1)


def to_markdown(inv: ProviderInvestigation, provider: Provider, facts=None) -> str:
    lines = [
        f"# Provider onboarding report: {provider.name}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Country | {provider.country_code} |",
        f"| Status | {provider.status.replace('_', ' ')} |",
        f"| Website | {provider.website or '-'} |",
        f"| Documentation | {provider.documentation_url or '-'} |",
        f"| Authentication | {provider.authentication_type or '-'} |",
        f"| Licence | {provider.licence or '-'} |",
        f"| Owner | {provider.owner or '-'} |",
        f"| Report author | {inv.author or '-'} |",
        f"| Last updated | {inv.updated_at:%Y-%m-%d %H:%M} UTC |",
        f"| Template completion | {completion(inv)}% |",
        "",
    ]
    if inv.findings:
        lines += ["## Summary of findings", "", inv.findings.strip(), ""]
    for i, (key, title) in enumerate(INVESTIGATION_SECTIONS, start=1):
        body = (getattr(inv, key) or "").strip() or "_Not yet documented._"
        lines += [f"## {i}. {title}", "", body, ""]
    if facts:
        lines += ["## Evidence register", "", "| Evidence | Category | Statement | Source |", "|---|---|---|---|"]
        for f in facts:
            stmt = f.statement.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {f.evidence_level} | {f.category} | {stmt} | {f.source_url or '-'} |")
        lines += ["", "_verified_ = tested by GridLink; _researched_ = from provider documentation; "
                  "_assumption_ = not yet confirmed.", ""]
    lines.append(f"_Exported from GridLink on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC._")
    return "\n".join(lines)


def to_csv(rows: list[tuple[ProviderInvestigation, Provider]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["provider", "country", "status", "completion_pct", "author", "updated_at", "findings"]
               + [k for k, _ in INVESTIGATION_SECTIONS])
    for inv, p in rows:
        w.writerow([p.name, p.country_code, p.status, completion(inv), inv.author or "", inv.updated_at.isoformat(),
                    inv.findings or ""] + [getattr(inv, k) or "" for k, _ in INVESTIGATION_SECTIONS])
    return buf.getvalue()
