"""Attributed, checksum-verified open-source evaluation snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import PROJECT_ROOT
from .models import ReviewRequest, SourceFile


def sample_catalog(root: Path = PROJECT_ROOT) -> list[dict]:
    return json.loads((root / "examples/real_samples.json").read_text())


def load_sample(sample_id: str, root: Path = PROJECT_ROOT) -> ReviewRequest:
    sample = next((s for s in sample_catalog(root) if s["id"] == sample_id), None)
    if sample is None:
        raise ValueError("Unknown sample.")
    files = []
    for record in sample["files"]:
        path = root / "examples" / record["local_path"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("The sample source differs from its attributed snapshot.")
        files.append(SourceFile(path=record["path"], content=data.decode("utf-8")))
    return ReviewRequest(
        title=sample["name"], files=files,
        context=sample["description"] + " Review only this snapshot; respect the tutorial or framework scope.",
        origin=f"{sample['repository_url']} @ {sample['ref']}",
    )


def load_demo(root: Path = PROJECT_ROOT) -> ReviewRequest:
    files = [SourceFile(path=p.name, content=p.read_text()) for p in sorted((root / "examples/demo").glob("*.py"))]
    return ReviewRequest(
        title="Checkout service · intentionally flawed demo", files=files,
        context="Synthetic training example. Request values are controlled by an unauthenticated caller.",
        origin="Synthetic teaching sample; not upstream open-source code",
    )
