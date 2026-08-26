import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "skills/eightctl/scripts/alarm.py"
SPEC = importlib.util.spec_from_file_location("alarm", SCRIPT)
alarm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alarm)


class AlarmTests(unittest.TestCase):
    def test_normalize_time(self):
        self.assertEqual(alarm.normalize_time("07:00"), "07:00:00")
        self.assertEqual(alarm.normalize_time("07:00:15"), "07:00:15")
        with self.assertRaises(ValueError):
            alarm.normalize_time("tomorrow")

    def test_verify_smart_alarm_requires_light_sleep_and_no_cap(self):
        alarm.verify_smart_alarm(
            {"smart": {"lightSleepEnabled": True, "sleepCapEnabled": False}}
        )
        with self.assertRaises(RuntimeError):
            alarm.verify_smart_alarm({"smart": {"lightSleepEnabled": False}})

    def test_extract_alarm_accepts_envelope_or_direct_response(self):
        self.assertEqual(alarm.extract_alarm({"alarm": {"id": "one"}})["id"], "one")
        self.assertEqual(alarm.extract_alarm({"id": "two"})["id"], "two")
        self.assertEqual(alarm.extract_alarm({}), {})

    def test_create_payload_always_enables_smart_alarm(self):
        args = types.SimpleNamespace(
            time="07:00",
            no_vibration=False,
            vibration_level=100,
            pattern="INTENSE",
            thermal_level=100,
            thermal_off=False,
            sound=None,
        )
        calls = []

        def fake_request(url, method, token, body=None):
            calls.append((url, method, body))
            return {"alarm": dict(body, id="test")}

        with patch.object(alarm, "request_json", side_effect=fake_request):
            with patch.object(
                alarm,
                "list_alarms",
                return_value=[{"id": "test", "smart": alarm.SMART_ALARM}],
            ):
                with patch("builtins.print"):
                    alarm.create_one_off(args, "token", "user")

        self.assertEqual(calls[0][2]["smart"], alarm.SMART_ALARM)

    def test_update_payload_forces_smart_alarm(self):
        args = types.SimpleNamespace(
            alarm_id="test",
            time=None,
            vibration_level=None,
            pattern=None,
            no_vibration=False,
            thermal_level=None,
            thermal_off=False,
        )
        calls = []

        def fake_request(url, method, token, body=None):
            calls.append((url, method, body))
            return {"alarm": dict(body, id="test")}

        with patch.object(
            alarm,
            "list_alarms",
            side_effect=[
                [{"id": "test"}],
                [{"id": "test", "smart": alarm.SMART_ALARM}],
            ],
        ):
            with patch.object(alarm, "request_json", side_effect=fake_request):
                with patch("builtins.print"):
                    alarm.update_alarm(args, "token", "user")

        self.assertEqual(calls[0][2]["smart"], alarm.SMART_ALARM)


if __name__ == "__main__":
    unittest.main()
