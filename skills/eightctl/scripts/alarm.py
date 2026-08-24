#!/usr/bin/env python3
"""Small stdlib-only helper for Eight Sleep's current alarm API."""

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


AUTH_URL = "https://auth-api.8slp.net/v1/tokens"
APP_API_URL = "https://app-api.8slp.net/v1"
APP_API_V2_URL = "https://app-api.8slp.net/v2"
SMART_ALARM = {
    "lightSleepEnabled": True,
    "sleepCapEnabled": False,
    "sleepCapMinutes": 480,
}


def read_config():
    values = {}
    config_path = Path.home() / ".config/eightctl/config.yaml"
    if not config_path.exists():
        return values
    if os.name != "nt" and config_path.stat().st_mode & 0o077:
        raise RuntimeError("Eight Sleep config must be readable only by the current user (chmod 600)")
    for line in config_path.read_text().splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = json.loads(value)
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


def read_credentials(target_user_id=None):
    values = read_config()
    email = os.environ.get("EIGHTCTL_EMAIL") or values.get("email")
    password = os.environ.get("EIGHTCTL_PASSWORD") or values.get("password")
    client_id = os.environ.get("EIGHTCTL_CLIENT_ID") or values.get("client_id")
    client_secret = os.environ.get("EIGHTCTL_CLIENT_SECRET") or values.get("client_secret")
    missing = [
        name
        for name, value in (
            ("email", email),
            ("password", password),
            ("client_id", client_id),
            ("client_secret", client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "configure Eight Sleep " + ", ".join(missing) + " in the private config or environment"
        )
    configured_user_id = os.environ.get("EIGHTCTL_TARGET_USER_ID") or values.get("user_id")
    return email, password, client_id, client_secret, target_user_id or configured_user_id


def request_json(url, method, token, body=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "eightctl-alarm-helper",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Eight Sleep request failed with HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Eight Sleep request failed: {error.reason}") from None


def authenticate(target_user_id=None):
    email, password, client_id, client_secret, target_user_id = read_credentials(target_user_id)
    request = urllib.request.Request(
        AUTH_URL,
        data=urllib.parse.urlencode(
            {
                "grant_type": "password",
                "username": email,
                "password": password,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            auth = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Eight Sleep authentication failed with HTTP {error.code}") from None
    token = auth.get("access_token")
    user_id = auth.get("userId")
    if not token or not user_id:
        raise RuntimeError("Eight Sleep authentication returned incomplete account data")
    return token, target_user_id or user_id


def normalize_time(value):
    for layout in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, layout).strftime("%H:%M:%S")
        except ValueError:
            pass
    raise ValueError("time must be HH:MM or HH:MM:SS")


def validate_settings(vibration_level, pattern, thermal_level):
    if vibration_level not in (20, 50, 100):
        raise ValueError("vibration level must be 20, 50, or 100")
    if pattern.upper() not in ("RISE", "INTENSE"):
        raise ValueError("pattern must be RISE or INTENSE")
    if thermal_level is not None and not -100 <= thermal_level <= 100:
        raise ValueError("thermal level must be between -100 and 100")


def list_alarms(token, user_id):
    response = request_json(f"{APP_API_V2_URL}/users/{user_id}/alarms", "GET", token)
    return response.get("alarms", [])


def print_alarm(alarm):
    print(
        json.dumps(
            {
                "id": alarm.get("id"),
                "time": alarm.get("time"),
                "enabled": alarm.get("enabled"),
                "nextTimestamp": alarm.get("nextTimestamp"),
                "repeat": alarm.get("repeat"),
                "vibration": alarm.get("vibration"),
                "thermal": alarm.get("thermal"),
                "smart": alarm.get("smart"),
            },
            indent=2,
        )
    )


def extract_alarm(response):
    alarm = response.get("alarm")
    if isinstance(alarm, dict):
        return alarm
    if response.get("id"):
        return response
    return {}


def verify_smart_alarm(alarm):
    smart = alarm.get("smart") or {}
    if smart.get("lightSleepEnabled") is not True:
        raise RuntimeError(
            "Eight Sleep did not confirm Smart Alarm/light-sleep support in the response"
        )
    if smart.get("sleepCapEnabled") is not False:
        raise RuntimeError("Eight Sleep did not confirm that the sleep cap is disabled")


def read_back_alarm(token, user_id, alarm_id):
    alarm = next(
        (item for item in list_alarms(token, user_id) if item.get("id") == alarm_id),
        None,
    )
    if alarm is None:
        raise RuntimeError(
            "alarm write may have succeeded, but the alarm was not found during read-back; "
            "inspect the alarm list before retrying"
        )
    verify_smart_alarm(alarm)
    return alarm


def create_one_off(args, token, user_id):
    pattern = args.pattern.upper()
    validate_settings(args.vibration_level, pattern, args.thermal_level)
    payload = {
        "time": normalize_time(args.time),
        "enabled": True,
        "vibration": {
            "enabled": not args.no_vibration,
            "powerLevel": args.vibration_level,
            "pattern": pattern,
        },
        "thermal": {
            "enabled": args.thermal_level is not None,
            "level": args.thermal_level if args.thermal_level is not None else 0,
        },
        "smart": dict(SMART_ALARM),
    }
    if args.sound:
        payload["sound"] = args.sound
    response = request_json(
        f"{APP_API_URL}/users/{user_id}/alarms", "POST", token, payload
    )
    created = extract_alarm(response)
    if not created.get("id"):
        raise RuntimeError(
            "alarm create response did not include an alarm ID; inspect the alarm list before retrying"
        )
    print_alarm(read_back_alarm(token, user_id, created["id"]))


def update_alarm(args, token, user_id):
    alarms = list_alarms(token, user_id)
    alarm = next((item for item in alarms if item.get("id") == args.alarm_id), None)
    if alarm is None:
        raise RuntimeError("alarm ID was not found")

    payload = dict(alarm)
    for key in ("nextTimestamp", "startTimestamp", "endTimestamp", "dismissedUntil", "snoozedUntil"):
        payload.pop(key, None)
    if args.time:
        payload["time"] = normalize_time(args.time)
    vibration = dict(payload.get("vibration") or {})
    pattern = args.pattern.upper() if args.pattern else vibration.get("pattern", "RISE")
    vibration_level = args.vibration_level or vibration.get("powerLevel", 50)
    validate_settings(vibration_level, pattern, args.thermal_level)
    vibration["powerLevel"] = vibration_level
    vibration["pattern"] = pattern
    if args.no_vibration:
        vibration["enabled"] = False
    payload["vibration"] = vibration
    if args.thermal_level is not None:
        payload["thermal"] = {"enabled": True, "level": args.thermal_level}
    elif args.thermal_off:
        payload["thermal"] = {"enabled": False, "level": 0}
    payload["smart"] = dict(SMART_ALARM)

    request_json(
        f"{APP_API_URL}/users/{user_id}/alarms/{args.alarm_id}",
        "PUT",
        token,
        payload,
    )
    print_alarm(read_back_alarm(token, user_id, args.alarm_id))


def add_target_user_id(parser):
    parser.add_argument(
        "--target-user-id",
        help="Eight Sleep user ID whose alarm should be read or changed",
    )


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    add_target_user_id(list_parser)

    create_parser = subparsers.add_parser("create-one-off")
    add_target_user_id(create_parser)
    create_parser.add_argument("--time", required=True)
    create_parser.add_argument("--thermal-level", type=int)
    create_parser.add_argument("--vibration-level", type=int, default=50)
    create_parser.add_argument("--pattern", default="RISE")
    create_parser.add_argument("--sound")
    create_parser.add_argument("--no-vibration", action="store_true")

    update_parser = subparsers.add_parser("update")
    add_target_user_id(update_parser)
    update_parser.add_argument("--alarm-id", required=True)
    update_parser.add_argument("--time")
    update_parser.add_argument("--thermal-level", type=int)
    update_parser.add_argument("--thermal-off", action="store_true")
    update_parser.add_argument("--vibration-level", type=int)
    update_parser.add_argument("--pattern")
    update_parser.add_argument("--no-vibration", action="store_true")

    args = parser.parse_args()
    token, user_id = authenticate(args.target_user_id)
    if args.command == "list":
        for alarm in list_alarms(token, user_id):
            print_alarm(alarm)
    elif args.command == "create-one-off":
        create_one_off(args, token, user_id)
    else:
        update_alarm(args, token, user_id)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
