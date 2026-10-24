# Herdr integration and keybindings

These examples use the Herdr 0.9.3 configuration syntax. Herdr is a terminal
multiplexer with its own config; these are not tmux bindings.

## The three keys

Add the following to `~/.config/herdr/config.toml` **only if those keys are not
already configured**. The English activation script normally adds F6/F7 for you.
F8 requires the [Russian installation](russian.md).

```toml
[[keys.command]]
key = "f7"
type = "shell"
command = '"$HOME/.local/bin/gerda-english" dictate'
description = "English dictation: start/stop"

[[keys.command]]
key = "f6"
type = "shell"
command = '"$HOME/.local/bin/gerda-english" speak'
description = "English dictation and spoken Codex reply"

[[keys.command]]
key = "f8"
type = "shell"
command = '"$HOME/.local/bin/herdr-dictate"'
description = "Russian dictation: start/stop"
```

Apply changes to the running session:

```bash
herdr server reload-config
```

The installer uses absolute paths in its generated commands. The manual examples
above use `$HOME`, expanded by the shell. Both forms avoid depending on the
background server's PATH.

## Command types

| `type` | Herdr behavior | When to use it |
| --- | --- | --- |
| `shell` | Runs a command detached in the background | Gerda's recording toggles |
| `pane` | Opens a temporary pane; closes it when the command exits | Interactive tools needing their own pane |
| `popup` | Opens a modal terminal over the session | Tools such as a Git browser |

Use **`shell` for all three Gerda keys**. Gerda needs the context of the original
pane and runs recording through its background process. Opening another terminal
for the hotkey is unnecessary.

## Direct keys and prefix bindings

`f7` is a direct shortcut. `prefix+g` means press Herdr's prefix, release it, then
press G. The default prefix is Ctrl+B. For example, edit the F7 entry to:

```toml
[[keys.command]]
key = "prefix+g"
type = "shell"
command = '"$HOME/.local/bin/gerda-english" dictate'
description = "English dictation: start/stop"
```

Use that same sequence to start and stop. A chord such as `ctrl+alt+g` can also be
used, provided your terminal and desktop pass it through. Function keys are a
useful starting point. Check existing bindings before choosing replacements.
Change existing entries instead of adding duplicates, then reload the config.

To change the prefix itself, edit the existing `[keys]` table (do not create a
second copy):

```toml
[keys]
prefix = "ctrl+a"
```

Some status messages still name F6/F7/F8 even if you choose other keys.
`herdr --default-config` shows supported settings. See Herdr's
[keyboard guide](https://herdr.dev/docs/keyboard/) and
[configuration reference](https://herdr.dev/docs/configuration/).

## How Gerda finds the destination

Herdr passes `HERDR_ACTIVE_PANE_ID` (or `HERDR_PANE_ID`) and
`HERDR_SOCKET_PATH` to the command. The English hotkey sends that context to the
local Gerda service. Recording and insertion remain attached to the starting
pane. Before inserting text or speaking a reply, Gerda checks the pane and its
Codex session again.

F6 observes the next submitted user turn in the matched Codex session and reads
one completed final answer. It uses the local `history.jsonl` and `sessions/`
files under `~/.codex/`. It does not submit Enter, create a Codex request itself,
or read unrelated conversations aloud.

Run Gerda and Herdr as the same desktop user. English hotkeys carry the session's
socket path, but the documented setup and manual checks use a local default
Herdr session. Remote microphone forwarding is not implemented. Russian F8 is
also documented for the default local session.

## Different paths

The English installer finds Herdr on PATH. If necessary, set an explicit path:

```bash
HERDR_BIN_PATH=/opt/herdr/bin/herdr \
  .venv-english/bin/python scripts/activate-english-modes.py
```

It writes that path into the service. `HERDR_CONFIG_PATH` selects an alternate
config file during activation; use the same config and session as your Herdr
server. For the Russian launcher, set `HERDR_BIN_PATH` in the binding if Herdr is
not at `~/.local/bin/herdr`:

```toml
command = 'HERDR_BIN_PATH=/opt/herdr/bin/herdr "$HOME/.local/bin/herdr-dictate"'
```

If Codex uses a custom data directory, add it to the English service using
`systemctl --user edit gerda-english.service`:

```ini
[Service]
Environment="CODEX_HOME=/absolute/path/to/codex-data"
```

Then run `systemctl --user daemon-reload` and
`systemctl --user restart gerda-english.service`.

## Troubleshooting

- **Nothing happens on a key:** check Herdr's key help (Ctrl+B, then `?`), reload
  its config, and check whether the outer terminal or desktop consumes that key.
- **English mode unavailable:** inspect `systemctl --user status gerda-english`
  and `journalctl --user -u gerda-english -n 50`. A shell command in an ordinary
  external terminal has no Herdr pane context; use the binding inside Herdr.
- **No recorded audio:** run `wpctl status` to inspect the selected microphone.
  Gerda records from PipeWire's default source.
- **F7 works but F6 cannot identify the conversation:** confirm that Codex runs
  in the selected pane and its local history is readable. Try one distinctive
  typed prompt, wait for completion, then use F6 again. Identical recent prompts
  in multiple sessions can make matching ambiguous; Gerda refuses playback then.
- **Recognition is slow:** look for `Whisper ready` in the service journal to see
  whether CUDA or CPU was selected. After a GPU failure, Whisper stays on CPU
  until the service restarts. First use also includes model loading.
- **A moved checkout no longer starts:** reinstall the service and launcher from
  the new path, then restart the service. The old installed paths are absolute.

## Remove the integration

Disable and stop the English service, and stop the on-demand Russian service if installed:

```bash
systemctl --user disable --now gerda-english.service
systemctl --user stop gerda-russian.service
```

Remove only Gerda's `[[keys.command]]` entries from Herdr's config, then reload it.
Remove the corresponding files from `~/.config/systemd/user/` and the launchers
`~/.local/bin/gerda-english` and `~/.local/bin/herdr-dictate` if you no longer use
them. Run `systemctl --user daemon-reload` afterwards. Model directories and
virtual environments can then be removed with the checkout.
