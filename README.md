# KubeScope Gabi · AI assistant

[![CI](https://github.com/dcotecnologia/kubescope-ai-gabi/actions/workflows/ci.yml/badge.svg)](https://github.com/dcotecnologia/kubescope-ai-gabi/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fdcotecnologia%2Fkubescope-ai-gabi%2Fbadges%2Fcoverage.json)](https://github.com/dcotecnologia/kubescope-ai-gabi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.15](https://img.shields.io/badge/python-3.15-blue.svg)

**Gabi** is the assistant of [KubeScope](https://github.com/dcotecnologia/kubescope). Ask about your
cluster in plain language, in the chat in the corner of the window or in your terminal, and she reads the
workloads, events, logs and live CPU and memory, explains what is wrong and how to fix it, and takes you to
the right list or tab.

She does not bring a model of her own: she answers through the coding assistant you already installed and
signed in to on your computer (**Claude Code** or **Codex**). KubeScope asks for no credentials and stores
none.

Gabi is an **extension** written against the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk)
and nothing else of the app. KubeScope installs her on the first run, and you can uninstall and reinstall her
in **Settings → Extensions**.

## What she does

- **Answers about the cluster.** Workloads, Pods, events, logs, resources and their YAML, with the context,
  namespace and screen you are on as her starting point.
- **Moves the window for you.** Opens a list, a page, a tab or the logs of a Pod, as if you had clicked.
- **Reads, and writes only when you let her.** With the write mode off she cannot change anything. With it
  on she can scale, restart or delete, and every change is shown to you and **confirmed first**.
- **Remembers the conversation.** The history is kept on your computer and can be cleared in her section of
  the Settings.
- **Works in the terminal too.** `kubescope chat` is the same conversation without the window.
- **Speaks your language.** She answers in the language of the app.

## Requirements

- KubeScope 1.12 or newer (the extension API `0`).
- One of the coding assistants, installed and signed in:
  [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`) or
  [Codex](https://developers.openai.com/codex) (`codex`). She finds them even when the app was started from
  a menu and its path is shorter than your terminal's.

## Install

She comes with KubeScope: the first time it runs, it downloads the version it expects, checks the files
against a hash it knows, and installs it. To install or reinstall by hand open **Settings → Extensions** and
either:

- **Install from GitHub...** and type `dcotecnologia/kubescope-ai-gabi`, or
- **Install from a folder...** and pick the `kubescope-extension.toml` of a clone of this repository.

A dialog shows where she comes from, her permissions and the sha256 of her content before anything of her
runs.

## Use

| How | What happens |
| --- | ------------ |
| The chat button in the corner of the window | Opens the chat |
| `Ctrl+G` | Asks the assistant (change it in **Settings → Shortcuts**) |
| `kubescope chat` or `kubescope assistant` | The conversation in the terminal |
| **Settings → Gabi** | Choose the assistant, its model and effort and its program, and clear the history |

The first time you ask, she tells you what she will send to the assistant and asks for your consent.

## Permissions

| Permission | Why she needs it |
| ---------- | ---------------- |
| `cluster.read` | Read workloads, Pods, logs, usage and resources to answer |
| `cluster.write` | Change the cluster when you ask her to, in the write mode and after you confirm |
| `subprocess` | Start the coding assistant installed on your computer |
| `ui.window` | The chat, messages, tasks and her shortcut |
| `ui.settings` | Her section of the Settings |
| `cli` | The commands `chat` and `assistant` of the terminal |

She is code that runs with your permissions, like any extension: read
[the security notes of the SDK](https://github.com/dcotecnologia/kubescope-sdk/blob/main/docs/permissions.md).

## Develop

She is a project of her own, in the namespace `kubescope` that she shares with the app and the SDK (there is
no `__init__.py` in it). Her tests run her inside the window of the app and lend her its real services, so
the app is a development dependency only. While the extension API is unstable (`api = "0"`), develop against
a checkout of the app next to this one:

```text
workspace/
├── kubescope/        # the app
├── kubescope-sdk/    # the SDK
└── kubescope-gabi/   # this project
```

```bash
make setup                          # dependencies and the pre-commit hook
make test FILE=tests/test_cli.py    # one test file; `make test` runs them all
make lint typecheck
```

To see your changes in the app as you make them, tick **Development mode** in **Settings → Extensions** and
install this folder: the app runs Gabi from it, without a copy, and reloads her when a file changes.

A test (`tests/test_independence.py`) keeps her imports to `kubescope.sdk` and herself, so she can be
installed and run without the app being importable.

### Layout

| Path | What it is |
| ---- | ---------- |
| `kubescope-extension.toml` | The manifest the app reads before installing: id, version, API, entry point, permissions and commands |
| `src/kubescope/gabi/extension.py` | `activate(ctx)`: the chat, the shortcut, the Settings section and the commands |
| `src/kubescope/gabi/claude.py`, `codex.py`, `runner.py` | The coding assistants and how they are started |
| `src/kubescope/gabi/knowledge.py` | What she knows about KubeScope and the rules she follows |
| `src/kubescope/gabi/actions.py`, `dispatch.py`, `executor.py` | What she can ask the app to do, and how each action is checked and run |
| `src/kubescope/gabi/cli.py` | `kubescope chat` |
| `languages/` | Her translations, one file per language |
| `tests/` | The tests |

## License

MIT. See [LICENSE](LICENSE).
