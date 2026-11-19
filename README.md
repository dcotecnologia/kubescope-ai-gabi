# KubeScope Gabi - AI Assistant

Gabi is the assistant of [KubeScope](https://github.com/dcotecnologia/kubescope): you ask about your
cluster in the chat in the corner of the window, and she answers using a coding assistant
(Claude Code or Codex) that you installed and signed in to on your computer. KubeScope asks for no
credentials and stores none.

Gabi is an **extension**. KubeScope ships with her installed, and you can uninstall and reinstall
her in **Settings → Extensions**, where you can also install her from this repository.

She depends on the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk) and on Qt, and on
nothing else of KubeScope: the app runs her with `activate(ctx)` and gives her, through `ctx`, what she
needs (the cluster, the window, the theme, her preferences, the terminal). A test keeps her imports to
`kubescope.sdk` and herself, so she can be installed and run without the app being importable.

## Install

In KubeScope, open **Settings → Extensions** and either:

- **Install from GitHub...** and type `dcotecnologia/kubescope-gabi`, or
- **Install from a folder...** and pick the `kubescope-extension.toml` of a clone of this repository.

KubeScope looks for the `kubescope-extension.toml` itself, so there is no zip to build. A dialog shows
where it came from, its permissions and the sha256 of its content before anything of it runs.

## Develop

She is a project of her own, in the namespace `kubescope` that she shares with the app and the SDK
(there is no `__init__.py` in it). Her tests run her inside the window of the app and lend her its real
services, so the app is a development dependency only. While the extension API is unstable
(`api = "0"`), develop against a checkout of the app next to this one:

```text
workspace/
├── kubescope/        # the app
├── kubescope-sdk/    # the SDK
└── kubescope-gabi/   # this project
```

```bash
uv sync                      # installs the SDK from GitHub and the app from ../kubescope, editable
uv run pytest tests/test_x.py
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

To see your changes in the app as you make them, install this folder in **development mode**: in
**Settings → Extensions** tick **Development mode**, then **Install from a folder...** and pick the
`kubescope-extension.toml`. The app runs Gabi from this folder, without a copy, and reloads her when a
file changes.

## Layout

| Path | What it is |
| ---- | ---------- |
| `kubescope-extension.toml` | The manifest the app reads before installing: id, version, API, entry point and permissions |
| `src/kubescope.gabi/` | The code |
| `languages/` | The translations of her texts, one file per language |
| `tests/` | The tests |

## License

MIT, like KubeScope.
