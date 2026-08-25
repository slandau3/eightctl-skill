<img src="eightctl-mark.svg" alt="eightctl mark" width="96" height="96" align="right">

# eightctl

[![Tests](https://github.com/slandau3/eightctl-skill/actions/workflows/test.yml/badge.svg)](https://github.com/slandau3/eightctl-skill/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/slandau3/eightctl-skill)](LICENSE)

**Agent-native control for Eight Sleep Pods.**

This skill gives OpenCode, Claude, Codex, and other compatible runtimes one
careful interface for Pod inspection, verified Smart Alarms, and personalized
sleep-recovery screening.

Human overview: this README. Machine summary: [`llms.txt`](llms.txt). Runtime
rules: [`skills/eightctl/SKILL.md`](skills/eightctl/SKILL.md).

## Capabilities

- Inspect Pod status, presence, schedules, temperature, and sleep metrics.
- Create or update alarms only through the verified Eight Sleep Smart Alarm API.
- Read back every alarm mutation and fail if light-sleep support is not persisted.
- Compare recent sleep, heart rate, HRV, respiratory rate, movement, and score
  against a personal baseline.
- Produce machine-readable JSON or concise human-readable reports without
  writing account data.

## For Agents

- Use `SKILL.md` as the source of truth for triggers, safety, and operating rules.
- Use `scripts/alarm.py` for Smart Alarm writes and persisted read-back.
- Use `scripts/health_watch.py` for read-only recovery screening.
- Never expose config files, passwords, tokens, or raw authenticated responses.

## Install

Install `eightctl` separately, then expose this repository's skill directory to
the runtimes you use:

```sh
REPO_DIR="$HOME/src/eightctl-skill"
git clone https://github.com/slandau3/eightctl-skill.git "$REPO_DIR"
mkdir -p "$HOME/.config/opencode/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.config/opencode/skills/eightctl"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.claude/skills/eightctl"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.codex/skills/eightctl"
```

Inspect an existing destination before replacing it. Do not overwrite a skill
directory that contains local changes.

## Configure

Keep `~/.config/eightctl/config.yaml` private with mode `600`. The alarm helper
reads `email`, `password`, `client_id`, and `client_secret` from that file, with
matching `EIGHTCTL_*` environment variables as overrides. Set `user_id` in the
private config or pass `--target-user-id` for a shared household.

The repository contains no credentials, tokens, or OAuth client secrets. Never
commit a real config file, `.env` file, password, or token.

## Smart Alarms

Use the bundled helper because the native one-off command does not expose a
verifiable Smart Alarm field:

```sh
python3 skills/eightctl/scripts/alarm.py create-one-off \
  --time 07:20 --thermal-level 100 --vibration-level 100 --pattern INTENSE
```

Every write includes and then verifies:

```json
{
  "smart": {
    "lightSleepEnabled": true,
    "sleepCapEnabled": false,
    "sleepCapMinutes": 480
  }
}
```

A fixed-time fallback is never used. The helper reads the current alarm list
after creating or updating an alarm and refuses success unless the persisted
record confirms light-sleep mode.

## Health Watch

Run a read-only screening report over the latest 42 days:

```sh
python3 skills/eightctl/scripts/health_watch.py --format json
```

The report uses a personal baseline rather than population averages. It needs
seven valid baseline nights by default, treats zero physiological values as
missing, and only escalates to `possible_illness_or_recovery_stress` when
multiple abnormal signals repeat across recent nights. Add context without
persisting it:

```sh
python3 skills/eightctl/scripts/health_watch.py \
  --confounder alcohol --confounder hard-exercise --format json
```

Possible signals are not a diagnosis. Confirm meaningful changes with symptoms,
a thermometer or appropriate test, and professional medical care when needed.

## Development

The helpers use only the Python standard library:

```sh
python3 -m unittest discover -s tests -v
```

Eight Sleep endpoints are undocumented and cloud-only. Provider behavior can
change without notice; report failures rather than guessing credentials or
falling back to an unverified alarm.
