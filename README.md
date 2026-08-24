# eightctl Agent Skill

An agent skill for controlling Eight Sleep Pods through [`eightctl`](https://github.com/steipete/eightctl), with an enforced Smart Alarm path.

## Install

Clone this repository, then expose `skills/eightctl` to the agent runtime you use. The commands below create destination directories and fail safely if a skill already exists there:

```sh
REPO_DIR="$HOME/src/eightctl-skill"
git clone https://github.com/slandau3/eightctl-skill.git "$REPO_DIR"
mkdir -p "$HOME/.config/opencode/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.config/opencode/skills/eightctl"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.claude/skills/eightctl"
ln -s "$REPO_DIR/skills/eightctl" "$HOME/.codex/skills/eightctl"
```

Use one link per runtime. If the destination already exists, replace it only
after checking whether it contains local changes.

## Configure

Install `eightctl` and keep `~/.config/eightctl/config.yaml` private with mode
`600`. The helper reads `email`, `password`, `client_id`, and `client_secret`
from that file, with matching `EIGHTCTL_*` environment variables as overrides.

Set `user_id` in the private config or pass `--target-user-id` when a shared
household has more than one sleeper.

The repository intentionally contains no credentials, tokens, or OAuth client
secrets. Do not commit a real config file or `.env` file.

## Smart Alarms

Alarm creation and updates always send:

```json
{
  "smart": {
    "lightSleepEnabled": true,
    "sleepCapEnabled": false,
    "sleepCapMinutes": 480
  }
}
```

The helper refuses to report success unless the API response confirms
`lightSleepEnabled: true`. A fixed-time fallback is never used.

## Development

The helper uses only the Python standard library. Run the tests with:

```sh
python3 -m unittest discover -s tests -v
```

Eight Sleep endpoints are undocumented and cloud-only. Provider behavior can
change without notice.
