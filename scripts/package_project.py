"""Create a source ZIP from an explicit allowlist, excluding local credentials/state."""

from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.md", "pyproject.toml", "requirements.lock", "streamlit_app.py",
    ".env.example", ".gitignore", "run.sh", ".streamlit/config.toml",
}
DIRECTORIES = {"src", "tests", "examples", "docs", "reports", "scripts"}


def source_paths(root: Path = ROOT) -> list[Path]:
    selected = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for directory in DIRECTORIES:
        for path in (root / directory).rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(p.startswith(".") or p == "__pycache__" for p in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo"} or "api-key" in path.name or "api_key" in path.name:
                continue
            if any(p.endswith(".egg-info") for p in relative.parts):
                continue
            selected.append(path)
    return sorted(set(selected))


def build_archive(output: Path | None = None) -> Path:
    output = output or ROOT / "dist/project_3e_code_review_agent.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in source_paths():
            archive.write(path, "project_3e_code_review_agent/" + path.relative_to(ROOT).as_posix())
    return output


if __name__ == "__main__":
    archive = build_archive()
    print(archive)
    print("SHA-256: " + hashlib.sha256(archive.read_bytes()).hexdigest())
