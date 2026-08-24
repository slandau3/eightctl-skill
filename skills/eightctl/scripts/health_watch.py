#!/usr/bin/env python3
"""Read-only, personalized Eight Sleep recovery-deviation screening."""

import argparse
import json
import math
import statistics
import subprocess
from datetime import date, timedelta


METRIC_RULES = {
    "heart_rate": {"label": "heart rate", "direction": "high", "unit": "bpm"},
    "hrv": {"label": "HRV", "direction": "low", "unit": "ms"},
    "respiratory_rate": {
        "label": "respiratory rate",
        "direction": "high",
        "unit": "breaths/min",
    },
    "sleep_duration": {
        "label": "sleep duration",
        "direction": "high",
        "unit": "seconds",
    },
    "presence_duration": {
        "label": "time in bed",
        "direction": "high",
        "unit": "seconds",
    },
    "score": {"label": "sleep score", "direction": "low", "unit": "points"},
    "tnt": {"label": "toss-and-turn count", "direction": "high", "unit": "events"},
}

STATUS_LABELS = {
    "insufficient_data": "Insufficient data",
    "normal_variation": "Normal variation",
    "physiological_deviation": "Physiological deviation",
    "possible_illness_or_recovery_stress": "Possible illness or recovery stress",
}


def _number(value, allow_zero=False):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        return None
    return number


def _path_value(mapping, path):
    value = mapping
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _first_number(mapping, paths, allow_zero=False):
    for path in paths:
        value = _number(_path_value(mapping, path), allow_zero=allow_zero)
        if value is not None:
            return value
    return None


def _series_median(session, names, allow_zero=False):
    timeseries = session.get("timeseries") or {}
    for name in names:
        values = []
        for point in timeseries.get(name) or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                value = _number(point[1], allow_zero=allow_zero)
                if value is not None:
                    values.append(value)
        if values:
            return statistics.median(values)
    return None


def _session_fallback(day_data, metric):
    paths = {
        "heart_rate": [
            ("heartRate",),
            ("averageHeartRate",),
            ("sleepQualityScore", "heartRate", "current"),
        ],
        "hrv": [
            ("hrv",),
            ("hrvScore",),
            ("sleepQualityScore", "hrv", "current"),
        ],
        "respiratory_rate": [
            ("respiratoryRate",),
            ("respRate",),
            ("sleepQualityScore", "respiratoryRate", "current"),
        ],
        "sleep_duration": [
            ("sleepDuration",),
            ("sleepDurationSeconds",),
            ("stageSummary", "sleepDuration"),
        ],
        "presence_duration": [
            ("presenceDuration",),
            ("totalDuration",),
            ("duration",),
        ],
        "score": [("score",), ("sleepScore",)],
        "tnt": [
            ("tnt",),
            ("tossAndTurnCount",),
            ("tossAndTurns",),
            ("tossesAndTurns",),
        ],
    }
    value = _first_number(
        day_data,
        paths[metric],
        allow_zero=metric == "tnt",
    )
    if value is not None:
        return value

    for session in day_data.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        value = _first_number(
            session,
            paths[metric],
            allow_zero=metric == "tnt",
        )
        if value is not None:
            return value

        stage_summary = session.get("stageSummary") or {}
        value = _first_number(
            {"stageSummary": stage_summary},
            paths[metric],
            allow_zero=metric == "tnt",
        )
        if value is not None:
            return value

        if metric == "presence_duration":
            value = _first_number(session, [("totalDuration",), ("duration",)])
            if value is not None:
                return value
        if metric == "sleep_duration":
            value = _first_number(session, [("sleepDuration",)])
            if value is not None:
                return value

        series_names = {
            "heart_rate": ("heartRate", "heart_rate"),
            "hrv": ("hrv", "heartRateVariability"),
            "respiratory_rate": ("respiratoryRate", "respRate"),
        }.get(metric)
        if series_names:
            value = _series_median(session, series_names)
            if value is not None:
                return value
    return None


def _day_list(payload):
    if isinstance(payload, list):
        direct_days = [
            item for item in payload if isinstance(item, dict) and (item.get("day") or item.get("date"))
        ]
        if direct_days:
            return direct_days
        nested_days = []
        for item in payload:
            nested_days.extend(_day_list(item))
        return nested_days

    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("days"), list):
        return payload["days"]
    if isinstance(payload.get("trends"), (dict, list)):
        return _day_list(payload["trends"])
    if isinstance(payload.get("data"), (dict, list)):
        return _day_list(payload["data"])
    if payload.get("day") or payload.get("date"):
        return [payload]
    return []


def normalize_trends(payload):
    """Convert the provider's nested trends response into dated night metrics."""
    normalized = []
    for day_data in _day_list(payload):
        if not isinstance(day_data, dict):
            continue
        day = day_data.get("day") or day_data.get("date")
        if not day:
            continue
        metrics = {}
        for metric in METRIC_RULES:
            value = _session_fallback(day_data, metric)
            if value is not None:
                metrics[metric] = value
        normalized.append({"date": str(day), "metrics": metrics})
    return sorted(normalized, key=lambda item: item["date"])


def _baseline_scale(metric, values, median):
    mad = statistics.median([abs(value - median) for value in values])
    robust_scale = 1.4826 * mad
    floors = {
        "heart_rate": 1.0,
        "hrv": 1.0,
        "respiratory_rate": 0.25,
        "sleep_duration": 300.0,
        "presence_duration": 300.0,
        "score": 3.0,
        "tnt": 2.0,
    }
    relative_floor = abs(median) * {
        "heart_rate": 0.02,
        "hrv": 0.05,
        "respiratory_rate": 0.03,
        "sleep_duration": 0.05,
        "presence_duration": 0.05,
        "score": 0.05,
        "tnt": 0.10,
    }[metric]
    return max(robust_scale, floors[metric], relative_floor)


def analyze_nights(
    nights,
    baseline_nights=28,
    minimum_baseline_nights=7,
    recent_nights=2,
    confounders=None,
):
    """Classify deviations without diagnosing illness or writing account data."""
    ordered = sorted(nights, key=lambda item: item["date"])
    recent = ordered[-recent_nights:] if ordered else []
    baseline_pool = ordered[:-recent_nights] if len(ordered) > recent_nights else []
    baseline_pool = baseline_pool[-baseline_nights:]
    usable_baseline = [night for night in baseline_pool if night.get("metrics")]
    usable_recent = [night for night in recent if night.get("metrics")]

    report = {
        "status": "insufficient_data",
        "label": STATUS_LABELS["insufficient_data"],
        "data_quality": {
            "nights": len(ordered),
            "valid_nights": len([night for night in ordered if night.get("metrics")]),
            "baseline_nights": len(usable_baseline),
            "recent_nights": len(usable_recent),
            "minimum_baseline_nights": minimum_baseline_nights,
        },
        "baseline": {},
        "nights": [],
        "confounders": list(confounders or []),
        "disclaimer": "This is a personalized screening signal, not a medical diagnosis.",
    }
    if len(usable_baseline) < minimum_baseline_nights or not usable_recent:
        return report

    baseline = {}
    for metric in METRIC_RULES:
        values = [night["metrics"][metric] for night in usable_baseline if metric in night["metrics"]]
        if not values:
            continue
        median = statistics.median(values)
        baseline[metric] = {
            "median": median,
            "scale": _baseline_scale(metric, values, median),
            "nights": len(values),
        }
    report["baseline"] = baseline

    for night in recent:
        signals = []
        for metric, rule in METRIC_RULES.items():
            if metric not in night.get("metrics", {}) or metric not in baseline:
                continue
            metric_baseline = baseline[metric]
            z_score = (night["metrics"][metric] - metric_baseline["median"]) / metric_baseline["scale"]
            is_signal = z_score >= 2 if rule["direction"] == "high" else z_score <= -2
            if is_signal:
                signals.append(
                    {
                        "metric": metric,
                        "label": rule["label"],
                        "direction": rule["direction"],
                        "value": night["metrics"][metric],
                        "baseline_median": metric_baseline["median"],
                        "z_score": round(z_score, 2),
                        "unit": rule["unit"],
                    }
                )
        report["nights"].append(
            {
                "date": night["date"],
                "metrics": night.get("metrics", {}),
                "signals": signals,
                "signal_count": len(signals),
            }
        )

    multi_signal_nights = sum(night["signal_count"] >= 2 for night in report["nights"])
    any_signal = any(night["signal_count"] for night in report["nights"])
    if multi_signal_nights >= 2:
        report["status"] = "possible_illness_or_recovery_stress"
    elif any_signal:
        report["status"] = "physiological_deviation"
    else:
        report["status"] = "normal_variation"
    report["label"] = STATUS_LABELS[report["status"]]
    return report


def fetch_trends(from_date, to_date, executable="eightctl"):
    command = [
        executable,
        "--quiet",
        "--output",
        "json",
        "metrics",
        "trends",
        "--from",
        from_date,
        "--to",
        to_date,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("eightctl metrics trends timed out") from None
    except OSError:
        raise RuntimeError("could not run eightctl metrics trends") from None
    if result.returncode:
        raise RuntimeError(f"eightctl metrics trends failed with exit code {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("eightctl metrics trends returned invalid JSON") from None


def render_text(report):
    lines = [report["label"]]
    quality = report["data_quality"]
    lines.append(
        f"Data: {quality['valid_nights']} valid nights; "
        f"{quality['baseline_nights']} baseline nights; {quality['recent_nights']} recent nights."
    )
    if report["confounders"]:
        lines.append("Confounders noted: " + ", ".join(report["confounders"]) + ".")
    for night in report["nights"]:
        if not night["signals"]:
            continue
        signals = ", ".join(
            f"{signal['label']} {signal['value']:.1f} ({signal['z_score']:+.1f} baseline)"
            for signal in night["signals"]
        )
        lines.append(f"{night['date']}: {signals}.")
    if report["status"] == "insufficient_data":
        lines.append(
            f"Need at least {quality['minimum_baseline_nights']} valid baseline nights "
            "before screening deviations."
        )
    lines.append(report["disclaimer"])
    return "\n".join(lines)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    default_to = date.today()
    parser.add_argument("--from", dest="from_date", default=(default_to - timedelta(days=42)).isoformat())
    parser.add_argument("--to", dest="to_date", default=default_to.isoformat())
    parser.add_argument("--baseline-nights", type=int, default=28)
    parser.add_argument("--minimum-baseline-nights", type=int, default=7)
    parser.add_argument("--recent-nights", type=int, default=2)
    parser.add_argument("--confounder", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.recent_nights < 1 or args.baseline_nights < 1 or args.minimum_baseline_nights < 1:
        raise SystemExit("night windows must be positive")
    if args.minimum_baseline_nights > args.baseline_nights:
        raise SystemExit("minimum baseline nights cannot exceed baseline nights")
    nights = normalize_trends(fetch_trends(args.from_date, args.to_date))
    report = analyze_nights(
        nights,
        baseline_nights=args.baseline_nights,
        minimum_baseline_nights=args.minimum_baseline_nights,
        recent_nights=args.recent_nights,
        confounders=args.confounder,
    )
    report["window"] = {"from": args.from_date, "to": args.to_date}
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
