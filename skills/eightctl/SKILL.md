---
name: eightctl
description: Use when controlling Eight Sleep Pods with eightctl, including status, temperature, alarms, Autopilot, base, audio, schedules, or sleep metrics.
---

# Eight Sleep via eightctl

Use the installed `eightctl` command for normal Pod operations. It reads the
user's local configuration and may cache authentication tokens in the operating
system keyring.

## Safety

- Never read, print, or repeat the Eight Sleep config file, password, tokens, or command-line credentials.
- Treat Pod, alarm, schedule, audio, base, Autopilot, travel, and device changes as mutations.
- Before a mutation, state the exact action, value, duration, and target side, then get explicit confirmation in the immediately preceding turn.
- Do not assume a write applies to one side. Use `--side left|right|solo` or `--target-user-id` when the target is known.
- After a mutation, run a read-only command and verify the result.
- Do not repeatedly retry authentication. Eight Sleep uses undocumented cloud endpoints and may rate-limit or change them.

## Mandatory Smart Alarm Rule

- Every requested alarm must be a verified Eight Sleep Smart Alarm that can wake during light sleep. A fixed-time fallback is never acceptable.
- Use an API payload that explicitly sets `smart.lightSleepEnabled` to `true`. Do not infer Smart Alarm support from a target time, vibration pattern, or thermal setting.
- The helper also sets `smart.sleepCapEnabled` to `false` and `smart.sleepCapMinutes` to `480`.
- After creating or updating an alarm, read it back and verify `smart.lightSleepEnabled` is `true`. Missing or false confirmation is a failed operation.
- Never invoke a native one-off command that does not expose and verify Smart Alarm fields.
- Alarm API operations target the authenticated Eight Sleep user by default. In a shared household, use `--target-user-id` for the intended sleeper and state that target before confirmation.

## Read-Only Commands

Prefer structured output for ordinary inspection:

```sh
eightctl --quiet --output json status
eightctl --quiet --output json presence
eightctl --quiet --output json schedule list
eightctl --quiet --output json metrics
```

The native alarm read route may target a retired endpoint. Use the bundled
helper for current alarm data:

```sh
python3 <skill-directory>/scripts/alarm.py list
```

Summarize results in human terms. Do not expose raw authentication or HTTP
responses when they contain sensitive data.

## Alarm Mutations

Use the helper for one-off alarms. It sends the Smart Alarm payload and refuses
to report success unless the API confirms light-sleep mode:

```sh
python3 <skill-directory>/scripts/alarm.py create-one-off \
  --target-user-id USER_ID --time HH:MM:SS --thermal-level -10
```

To convert or change an existing alarm while preserving unspecified settings:

```sh
python3 <skill-directory>/scripts/alarm.py update \
  --target-user-id USER_ID --alarm-id ID --thermal-level -10 \
  --vibration-level 50 --pattern RISE
```

The helper defaults to vibration level `50` and pattern `RISE`. Use `INTENSE`
and level `100` only when requested or already configured. A negative thermal
level means colder; do not silently convert the user's requested level.

The helper forces Smart Alarm light-sleep settings on updates, reads the alarm
back through the current list endpoint, and fails if persisted data does not
confirm them.

## Setup

Install `eightctl` separately and keep its config private with mode `600`:

```sh
chmod 600 ~/.config/eightctl/config.yaml
```

The helper reads `email` and `password` from that config. It reads the OAuth
client values from `client_id` and `client_secret` in the same private config,
or from `EIGHTCTL_CLIENT_ID` and `EIGHTCTL_CLIENT_SECRET`. It optionally uses
`user_id` or `EIGHTCTL_TARGET_USER_ID` as the alarm target; the CLI flag takes
precedence. This repository intentionally contains no credentials or client
secrets.

## Limitations

Eight Sleep control is cloud-only and based on undocumented provider APIs. The
provider can change endpoints or payloads without notice. Report failures
clearly instead of guessing credentials or changing unrelated settings.
