# KubeScope Gabi - AI Assistant

Gabi is the assistant of [KubeScope](https://github.com/dcotecnologia/kubescope): you ask about your
cluster in the chat in the corner of the window, and she answers using a coding assistant
(Claude Code or Codex) that you installed and signed in to on your computer. KubeScope asks for no
credentials and stores none.

Gabi is an **extension**. KubeScope ships with her installed, and you can uninstall and reinstall
her in **Settings → Extensions**, where you can also install her from this repository.

> Work in progress: this project was extracted from the app. It is waiting for the app to load
> extensions with `activate(ctx)`, so `kubescope_gabi.activate` does not exist yet.

## Install

In KubeScope, open **Settings → Extensions → Install from GitHub...** and type
`dcotecnologia/kubescope-gabi`, or **Install from a zip...** with a zip from the releases. A dialog
shows where it came from, its permissions and the sha256 before anything of it runs.

## Develop

Gabi depends on KubeScope the way a pytest plugin depends on pytest. While the extension API is
unstable (`api = "0"`), develop against a checkout of the app next to this one:

```text
workspace/
├── kubescope/        # the app
└── kubescope-gabi/   # this project
```

```bash
uv sync                      # installs the app from ../kubescope, editable
uv run pytest                # the tests
uv run ruff check . && uv run ruff format --check .
uv run pyright
python tools/build_zip.py    # dist/kubescope-gabi-<version>.zip, what the app installs
```

## Layout

| Path | What it is |
| ---- | ---------- |
| `kubescope-extension.toml` | The manifest the app reads before installing: id, version, API, entry point and permissions |
| `src/kubescope_gabi/` | The code |
| `languages/` | The translations of her texts, one file per language |
| `tests/` | The tests |

## License

MIT, like KubeScope.
