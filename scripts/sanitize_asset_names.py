"""Copia un árbol de archivos con nombres ASCII/UTF-8 seguros para Cloud Run."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path


def safe_component(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in nfkd if ord(ch) < 128)
    ascii_only = ascii_only.replace("#", "n").replace("?", "")
    ascii_only = " ".join(ascii_only.split())
    ascii_only = ascii_only.strip(" .")
    return ascii_only or "file"


def copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst.joinpath(*[safe_component(part) for part in rel.parts])
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stem, suffix = target.stem, target.suffix
            n = 2
            candidate = target
            while candidate.exists():
                candidate = target.with_name(f"{stem}_{n}{suffix}")
                n += 1
            target = candidate
        target.write_bytes(path.read_bytes())


if __name__ == "__main__":
    copy_tree(Path(sys.argv[1]), Path(sys.argv[2]))
