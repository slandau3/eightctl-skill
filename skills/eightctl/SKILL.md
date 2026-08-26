---
name: eightctl
description: Use when inspecting or controlling Eight Sleep Pods with eightctl, including status, temperature, alarms, Autopilot, base, audio, schedules, sleep metrics, or read-only recovery screening.
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
- Treat health-watch output as a screening signal, never as a diagnosis or emergency assessment.

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
python3 <skill-directory>/scripts/health_watch.py --format json
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
  --target-user-id USER_ID --time HH:MM:SS
```

Defaults are `100 INTENSE` vibration and `100` thermal (hot) — the safe, loud wake-up. Override only when the user explicitly asks for a gentler setting. Scale: vibration `20` low / `50` mid / `100` max (plus off via `--no-vibration`); thermal `-100` cold → `+100` hot (plus off via `--thermal-off`). A negative thermal level means colder; do not silently convert the user's requested level.

To convert or change an existing alarm while preserving unspecified settings:

```sh
python3 <skill-directory>/scripts/alarm.py update \
  --target-user-id USER_ID --alarm-id ID --thermal-level 100 \
  --vibration-level 100 --pattern INTENSE
```

The helper forces Smart Alarm light-sleep settings on updates, reads the alarm
back through the current list endpoint, and fails if persisted data does not
confirm them.

## Recovery Screening

Use the read-only health watcher when the user asks whether recent sleep data
looks unusual:

```sh
python3 <skill-directory>/scripts/health_watch.py --format json
```

It fetches `metrics trends`, normalizes dated nights, treats zero physiological
values as missing, and compares recent nights with a personal baseline. The
default window is 42 days with 28 baseline nights, at least 7 valid baseline
nights, and 2 recent nights. It considers heart rate, HRV, respiratory rate,
sleep duration, time in bed, sleep score, and toss-and-turn count when those
fields are available.

The statuses mean:

- `insufficient_data`: not enough valid personal history.
- `normal_variation`: no configured deviation pattern.
- `physiological_deviation`: one or more unusual signals need context.
- `possible_illness_or_recovery_stress`: multiple signals repeated across recent nights.

Ask about confounders such as alcohol, hard exercise, stress, poor sleep,
medication, travel, and menstrual-cycle changes. These can mimic illness. Add
known context to a single report with repeated `--confounder` flags; nothing is
persisted. Recommend symptoms, a thermometer or appropriate test, and medical
care when warranted. Never label the user as sick from Pod data alone.

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
clearly instead of guessing credentials or changing unrelated settings. Native
`eightctl` builds should use a trusted macOS Keychain application access list;
older builds may prompt repeatedly while reading the token cache. Never read
or print the token to troubleshoot that behavior.
