"""Pack Gabi as the zip that KubeScope installs as an extension.

The zip has the manifest at its root, the code under `src/`, and the
translations under `languages/`, which is where KubeScope looks for them.
It uses only the standard library, so it runs anywhere.

    python tools/build_zip.py            # dist/kubescope-gabi-<version>.zip
"""

import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__"}


def version() -> str:
    manifest = tomllib.loads((ROOT / "kubescope-extension.toml").read_text("utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    if manifest["version"] != project["version"]:
        raise SystemExit(
            f"kubescope-extension.toml says {manifest['version']} and "
            f"pyproject.toml says {project['version']}: make them the same"
        )
    return manifest["version"]


def files() -> list[Path]:
    found = [ROOT / "kubescope-extension.toml", ROOT / "LICENSE"]
    for folder in ("src", "languages"):
        found += sorted(
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file() and not SKIP & set(path.parts)
        )
    return found


def build(target: Path | None = None) -> Path:
    target = target or ROOT / "dist" / f"kubescope-gabi-{version()}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files():
            archive.write(path, path.relative_to(ROOT).as_posix())
    return target


if __name__ == "__main__":
    print(build())
    sys.exit(0)
