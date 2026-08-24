import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "skills/eightctl/scripts/health_watch.py"
SPEC = importlib.util.spec_from_file_location("health_watch", SCRIPT)
health_watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health_watch)


class HealthWatchTests(unittest.TestCase):
    def test_normalize_trends_extracts_supported_night_metrics(self):
        payload = [
            {
                "trends": {
                    "days": [
                        {
                            "day": "2026-08-10",
                            "presenceDuration": 28800,
                            "sleepDuration": 25200,
                            "score": 80,
                            "tnt": 23,
                            "sleepQualityScore": {
                                "heartRate": {"current": 72},
                                "hrv": {"current": 30.5},
                                "respiratoryRate": {"current": 15.2},
                            },
                        }
                    ]
                }
            }
        ]

        self.assertEqual(
            health_watch.normalize_trends(payload),
            [
                {
                    "date": "2026-08-10",
                    "metrics": {
                        "heart_rate": 72.0,
                        "hrv": 30.5,
                        "respiratory_rate": 15.2,
                        "sleep_duration": 25200.0,
                        "presence_duration": 28800.0,
                        "score": 80.0,
                        "tnt": 23.0,
                    },
                }
            ],
        )

    def test_normalize_trends_treats_missing_zero_vitals_as_missing(self):
        payload = {
            "trends": {
                "days": [
                    {
                        "day": "2026-08-11",
                        "heartRate": 0,
                        "hrv": 0,
                        "respiratoryRate": 0,
                        "sleepDuration": 0,
                        "presenceDuration": 0,
                        "score": 0,
                        "tnt": 0,
                    }
                ]
            }
        }

        normalized = health_watch.normalize_trends(payload)

        self.assertEqual(normalized[0]["metrics"], {"tnt": 0.0})

    def test_normalize_trends_keeps_all_direct_days(self):
        payload = [
            {"day": "2026-08-10", "score": 80},
            {"day": "2026-08-11", "score": 81},
        ]

        normalized = health_watch.normalize_trends(payload)

        self.assertEqual([night["date"] for night in normalized], ["2026-08-10", "2026-08-11"])

    def test_analyze_nights_flags_repeated_multi_signal_deviation(self):
        baseline = [
            {
                "date": f"2026-08-{day:02d}",
                "metrics": {
                    "heart_rate": 60,
                    "hrv": 50,
                    "respiratory_rate": 14,
                    "sleep_duration": 24000,
                    "presence_duration": 26000,
                    "score": 85,
                    "tnt": 20,
                },
            }
            for day in range(1, 9)
        ]
        recent = [
            {
                "date": "2026-08-09",
                "metrics": {
                    "heart_rate": 72,
                    "hrv": 30,
                    "respiratory_rate": 17,
                    "sleep_duration": 28000,
                    "presence_duration": 30000,
                    "score": 65,
                    "tnt": 40,
                },
            },
            {
                "date": "2026-08-10",
                "metrics": {
                    "heart_rate": 71,
                    "hrv": 31,
                    "respiratory_rate": 17,
                    "sleep_duration": 27900,
                    "presence_duration": 29900,
                    "score": 66,
                    "tnt": 39,
                },
            },
        ]

        result = health_watch.analyze_nights(baseline + recent)

        self.assertEqual(result["status"], "possible_illness_or_recovery_stress")
        self.assertEqual(result["data_quality"]["baseline_nights"], 8)
        self.assertGreaterEqual(result["nights"][-1]["signal_count"], 2)

    def test_analyze_nights_requires_a_minimum_personal_baseline(self):
        nights = [
            {
                "date": "2026-08-10",
                "metrics": {"heart_rate": 60, "hrv": 50},
            }
        ]

        result = health_watch.analyze_nights(nights)

        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["data_quality"]["baseline_nights"], 0)

    def test_fetch_trends_converts_command_timeout_to_safe_error(self):
        with patch.object(
            health_watch.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("eightctl", 90),
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                health_watch.fetch_trends("2026-08-01", "2026-08-10")


if __name__ == "__main__":
    unittest.main()
