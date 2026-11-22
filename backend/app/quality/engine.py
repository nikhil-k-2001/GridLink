"""Data quality engine: completeness, consistency, freshness and validity checks on a normalised batch.

Record-level failures make a record invalid (it is NOT saved, and the reason is logged). Batch-level
findings (missing intervals, duplicates, freshness) are reported in the quality report. Nothing is
silently corrected.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.connectors.base import Issue
from app.normalisation.engine import NormalisedRecord

# ISO 3166-1 alpha-2 codes of ENTSO-E member/observer countries, plus "EU" for pan-European datasets.
EUROPEAN_COUNTRY_CODES = set(
    "AL AT BA BE BG CH CY CZ DE DK EE ES FI FR GB GE GR HR HU IE IS IT LT LU LV MD ME MK MT NL NO PL PT RO RS "
    "SE SI SK TR UA XK EU".split()
)
ALLOWED_SOURCES_BY_METRIC = {
    "consumption": {"total", "pumped_storage"},
    "residual_load": {"total"},
    "day_ahead_price": {"all"},
}
EARLIEST_PLAUSIBLE = datetime(2015, 1, 1, tzinfo=UTC)


@dataclass
class SeriesQuality:
    series_key: str
    dataset_key: str
    interval_minutes: int
    expected: int
    present: int  # non-null values
    nulls: int
    latest_timestamp: datetime | None
    missing_periods: list[dict[str, Any]]
    freshness_status: str
    lag_minutes: float | None

    @property
    def completeness(self) -> float:
        return 100.0 if self.expected == 0 else round(100.0 * min(self.present, self.expected) / self.expected, 2)


@dataclass
class ValidationResult:
    valid: list[NormalisedRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    invalid_count: int = 0
    duplicate_count: int = 0
    conflicting_duplicates: int = 0
    null_count: int = 0
    series: list[SeriesQuality] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def completeness_score(self) -> float | None:
        expected = sum(s.expected for s in self.series)
        if expected == 0:
            return None
        return round(100.0 * sum(min(s.present, s.expected) for s in self.series) / expected, 2)

    @property
    def missing_interval_count(self) -> int:
        return sum(s.expected - min(s.present, s.expected) for s in self.series)

    @property
    def freshness_status(self) -> str:
        order = ["fresh", "delayed", "stale"]
        statuses = [s.freshness_status for s in self.series if s.freshness_status in order]
        return max(statuses, key=order.index) if statuses else "unknown"

    @property
    def overall_status(self) -> str:
        total = len(self.valid) + self.invalid_count
        invalid_rate = self.invalid_count / total if total else 0.0
        comp = self.completeness_score
        if comp is None or comp < 80 or invalid_rate > 0.05 or self.freshness_status == "stale":
            return "fail"
        weak_series = any(s.expected and s.completeness < 90 for s in self.series)
        if comp < 98 or weak_series or self.invalid_count or self.duplicate_count or self.freshness_status == "delayed":
            return "warn"
        return "pass"


def _floor(dt: datetime, minutes: int) -> datetime:
    epoch_min = int(dt.timestamp() // 60)
    return datetime.fromtimestamp((epoch_min - epoch_min % minutes) * 60, tz=UTC)


def _ceil(dt: datetime, minutes: int) -> datetime:
    f = _floor(dt, minutes)
    return f if f == dt else f + timedelta(minutes=minutes)


def _record_problems(r: NormalisedRecord, rules: dict[str, Any], now: datetime, publishes_ahead: bool) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    # validity
    if r.timestamp_utc < EARLIEST_PLAUSIBLE:
        problems.append(("invalid_timestamp", f"Timestamp {r.timestamp_utc.isoformat()} is before 2015"))
    horizon = timedelta(days=3) if publishes_ahead else timedelta(minutes=r.interval_minutes)
    if r.timestamp_utc > now + horizon:
        problems.append(("future_timestamp", f"Timestamp {r.timestamp_utc.isoformat()} is in the future for an actuals dataset"))
    if r.interval_minutes <= 60 and (r.timestamp_utc.minute % r.interval_minutes or r.timestamp_utc.second):
        problems.append(("misaligned_timestamp", f"Timestamp not aligned to {r.interval_minutes}-minute grid"))
    if r.value is not None:
        if r.metric_type in rules.get("non_negative_metrics", []) and r.value < 0:
            problems.append(("negative_value", f"Negative {r.metric_type} value {r.value:g} {r.unit}"))
        max_mw = rules.get("max_mw", {}).get(r.metric_type)
        if max_mw is not None and r.value > max_mw:
            problems.append(("out_of_range", f"{r.value:g} MW exceeds plausible maximum {max_mw} MW"))
        if r.metric_type == "day_ahead_price":
            lo, hi = rules.get("price_range", [-500, 5000])
            if not lo <= r.value <= hi:
                problems.append(("out_of_range", f"Price {r.value:g} EUR/MWh outside harmonised range [{lo}, {hi}]"))
    # consistency
    if r.country_code not in EUROPEAN_COUNTRY_CODES:
        problems.append(("invalid_country_code", f"Unknown country code '{r.country_code}'"))
    allowed = ALLOWED_SOURCES_BY_METRIC.get(r.metric_type)
    if allowed is not None and r.energy_source not in allowed:
        problems.append(("inconsistent_category", f"energy_source '{r.energy_source}' is not valid for {r.metric_type}"))
    return problems


def _missing_periods(expected_slots: list[datetime], present: set[datetime], minutes: int) -> list[dict[str, Any]]:
    periods: list[dict[str, Any]] = []
    run_start: datetime | None = None
    run_len = 0
    for slot in expected_slots:
        if slot not in present:
            if run_start is None:
                run_start, run_len = slot, 0
            run_len += 1
        elif run_start is not None:
            periods.append({"start": run_start.isoformat(), "end": (run_start + timedelta(minutes=minutes * run_len)).isoformat(), "intervals": run_len})
            run_start = None
    if run_start is not None:
        periods.append({"start": run_start.isoformat(), "end": (run_start + timedelta(minutes=minutes * run_len)).isoformat(), "intervals": run_len})
    return periods


def validate_batch(
    normalised,
    mapping: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
    expected_lag_minutes: int,
    *,
    expected_series: list[str] | None = None,
    publishes_ahead_series: set[str] | None = None,
    lag_by_series: dict[str, int] | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    now = now or datetime.now(UTC)
    rules = mapping.get("validation", {})
    publishes_ahead_series = publishes_ahead_series or set()
    lag_by_series = lag_by_series or {}
    out = ValidationResult()

    seen_ids: dict[str, NormalisedRecord] = {}
    seen_logical: dict[tuple[str, datetime, int], str] = {}
    problem_counts: Counter[str] = Counter()

    for r in normalised.records:
        # duplicates
        if r.source_record_id in seen_ids:
            out.duplicate_count += 1
            if seen_ids[r.source_record_id].value != r.value:
                out.conflicting_duplicates += 1
                out.issues.append(Issue("validate", "conflicting_duplicate",
                                        f"{r.source_record_id} delivered twice with different values",
                                        context={"first": seen_ids[r.source_record_id].original_value, "second": r.original_value}))
            continue
        logical = (r.dataset_key, r.timestamp_utc, r.interval_minutes)
        if logical in seen_logical:
            out.duplicate_count += 1
            continue
        problems = _record_problems(r, rules, now, r.series_key in publishes_ahead_series)
        if problems:
            out.invalid_count += 1
            for code, msg in problems:
                problem_counts[code] += 1
                if problem_counts[code] <= 50:  # cap detail rows; totals are kept in checks
                    out.issues.append(Issue("validate", code, msg, context={
                        "source_record_id": r.source_record_id, "original_value": r.original_value,
                        "original_unit": r.original_unit, "location": r.location}))
            continue
        seen_ids[r.source_record_id] = r
        seen_logical[logical] = r.source_record_id
        if r.value is None:
            out.null_count += 1
        out.valid.append(r)

    # completeness + freshness per series
    by_series: dict[str, list[NormalisedRecord]] = defaultdict(list)
    for r in out.valid:
        by_series[r.series_key].append(r)
    series_keys = list(dict.fromkeys((expected_series or []) + list(by_series)))
    for key in series_keys:
        recs = by_series.get(key, [])
        spec = mapping["series"].get(key, {})
        minutes = Counter(r.interval_minutes for r in recs).most_common(1)[0][0] if recs else \
            {"PT15M": 15, "PT60M": 60, "P1D": 1440}.get(spec.get("frequency", "PT15M"), 15)
        lag = lag_by_series.get(key, expected_lag_minutes)
        ahead = key in publishes_ahead_series
        effective_end = window_end if ahead else min(window_end, now - timedelta(minutes=lag))
        slots: list[datetime] = []
        t = _ceil(window_start, minutes)
        while t + timedelta(minutes=minutes) <= effective_end:
            slots.append(t)
            t += timedelta(minutes=minutes)
        present = {r.timestamp_utc for r in recs if r.value is not None}
        slot_set = set(slots)
        latest = max((r.timestamp_utc for r in recs if r.value is not None), default=None)
        if latest is None:
            fresh, lag_min = "stale", None
        else:
            lag_min = (now - (latest + timedelta(minutes=minutes))).total_seconds() / 60
            fresh = "fresh" if lag_min <= lag else "delayed" if lag_min <= 2 * lag else "stale"
        sq = SeriesQuality(
            series_key=key,
            dataset_key=spec.get("dataset_key", key),
            interval_minutes=minutes,
            expected=len(slots),
            present=len(present & slot_set),
            nulls=sum(1 for r in recs if r.value is None),
            latest_timestamp=latest,
            missing_periods=_missing_periods(slots, present, minutes),
            freshness_status=fresh,
            lag_minutes=round(lag_min, 1) if lag_min is not None else None,
        )
        out.series.append(sq)
        if not recs:
            out.issues.append(Issue("validate", "missing_series", f"No values received for expected series '{key}'",
                                    severity="warning", context={"series": key}))

    out.checks = {
        "completeness": {
            "score": out.completeness_score,
            "missing_intervals": out.missing_interval_count,
            "null_values": out.null_count,
            "missing_series": [s.series_key for s in out.series if s.present == 0],
        },
        "consistency": {
            "duplicates": out.duplicate_count,
            "conflicting_duplicates": out.conflicting_duplicates,
            "unexpected_units": sum(1 for i in normalised.issues if i.code == "unexpected_unit"),
            "invalid_country_codes": problem_counts.get("invalid_country_code", 0),
            "inconsistent_categories": problem_counts.get("inconsistent_category", 0),
            "unmapped_series": normalised.unmapped_series,
        },
        "validity": {
            "invalid_records": out.invalid_count,
            "rejected_in_normalisation": normalised.rejected,
            "by_rule": dict(problem_counts),
        },
        "freshness": {
            "status": out.freshness_status,
            "series": {s.series_key: {"latest": s.latest_timestamp.isoformat() if s.latest_timestamp else None,
                                      "lag_minutes": s.lag_minutes, "status": s.freshness_status} for s in out.series},
        },
    }
    return out
