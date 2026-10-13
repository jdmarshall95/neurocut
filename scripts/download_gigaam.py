#!/usr/bin/env python3
"""Download GigaAM (NeMo-CTC) offline STT model + Silero VAD for sherpa-onnx.

Used both at Docker build time (INSTALL_GIGAAM=1) and for local setup:

    python scripts/download_gigaam.py --dest storage/models

Downloads (upstream archive names kept as published by sherpa-onnx):
  - sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19 → <dest>/gigaam-ru/
  - silero_vad.onnx → <dest>/silero_vad.onnx
"""
from __future__ import annotations

import argparse
import bz2
import shutil
import tarfile
import urllib.request
from pathlib import Path

GIGAAM_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19.tar.bz2"
)
GIGAAM_ARCHIVE_ROOT = "sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19"
SILERO_VAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)
    print(f"  -> {dest} ({dest.stat().st_size // (1024 * 1024)} MB)")


def _extract_model(archive: Path, model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    with bz2.open(archive) as raw, tarfile.open(fileobj=raw) as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if name in {"model.int8.onnx", "tokens.txt"} and member.isfile():
                member.name = name
                tar.extract(member, model_dir)
                print(f"  extracted {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default="storage/models",
        help="Destination directory for models (default: storage/models)",
    )
    args = parser.parse_args()

    dest = Path(args.dest).resolve()
    model_dir = dest / "gigaam-ru"
    vad_path = dest / "silero_vad.onnx"

    if (model_dir / "model.int8.onnx").is_file() and (model_dir / "tokens.txt").is_file():
        print(f"GigaAM model already present at {model_dir}")
    else:
        archive = dest / "gigaam.tar.bz2"
        _download(GIGAAM_ARCHIVE_URL, archive)
        _extract_model(archive, model_dir)
        archive.unlink(missing_ok=True)

    if vad_path.is_file():
        print(f"Silero VAD already present at {vad_path}")
    else:
        _download(SILERO_VAD_URL, vad_path)

    print("GigaAM assets ready.")


if __name__ == "__main__":
    main()
