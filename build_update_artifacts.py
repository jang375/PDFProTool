"""Build release update artifacts: full manifest and optional delta zip.

Usage:
  python build_update_artifacts.py --current-dir dist/PDFProTool --target-version 1.1.3 --output-dir dist
  python build_update_artifacts.py --current-dir dist/PDFProTool --target-version 1.1.3 --output-dir dist --base-zip dist/PDFProTool-v1.1.2.zip --base-version 1.1.2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _norm_rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def _scan_current(current_dir: Path) -> dict[str, dict[str, int | str]]:
    files: dict[str, dict[str, int | str]] = {}
    for p in sorted(current_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = _norm_rel(p.relative_to(current_dir))
        files[rel] = {
            "size": p.stat().st_size,
            "sha256": _sha256_file(p),
        }
    return files


def _scan_base_zip(base_zip: Path) -> dict[str, dict[str, int | str]]:
    files: dict[str, dict[str, int | str]] = {}
    with zipfile.ZipFile(base_zip, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("PDFProTool/"):
                name = name[len("PDFProTool/") :]
            if not name:
                continue
            data = zf.read(info.filename)
            files[name] = {
                "size": len(data),
                "sha256": _sha256_bytes(data),
            }
    return files


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _build_delta_zip(
    current_dir: Path,
    output_zip: Path,
    changed_files: list[str],
    deleted_files: list[str],
    base_version: str,
    target_version: str,
) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in changed_files:
            src = current_dir / Path(rel)
            if not src.exists():
                continue
            zf.write(src, arcname=f"payload/{rel}")

        delete_body = "\n".join(deleted_files)
        zf.writestr("delete_files.txt", delete_body)

        meta = {
            "mode": "delta",
            "base_version": base_version,
            "target_version": target_version,
            "changed_count": len(changed_files),
            "deleted_count": len(deleted_files),
        }
        zf.writestr("delta_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current-dir", required=True)
    ap.add_argument("--target-version", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--base-zip", default="")
    ap.add_argument("--base-version", default="")
    args = ap.parse_args()

    current_dir = Path(args.current_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    target_version = args.target_version.strip().lstrip("vV")

    if not current_dir.exists() or not current_dir.is_dir():
        raise SystemExit(f"current dir not found: {current_dir}")

    current_files = _scan_current(current_dir)
    manifest = {
        "version": target_version,
        "files": current_files,
    }

    manifest_path = out_dir / f"app-update-manifest-v{target_version}.json"
    _write_json(manifest_path, manifest)
    print(f"manifest: {manifest_path}")

    base_zip_raw = args.base_zip.strip()
    base_version_raw = args.base_version.strip().lstrip("vV")
    if not base_zip_raw:
        print("delta: skipped (no base zip)")
        return 0

    base_zip = Path(base_zip_raw).resolve()
    if not base_zip.exists():
        print(f"delta: skipped (base zip missing: {base_zip})")
        return 0

    if not base_version_raw:
        print("delta: skipped (no base version)")
        return 0

    base_files = _scan_base_zip(base_zip)

    changed: list[str] = []
    for rel, meta in current_files.items():
        b = base_files.get(rel)
        if b is None or b.get("sha256") != meta.get("sha256"):
            changed.append(rel)

    deleted = sorted([rel for rel in base_files.keys() if rel not in current_files])

    delta_zip = out_dir / f"PDFProTool-delta-from-v{base_version_raw}-to-v{target_version}.zip"
    _build_delta_zip(
        current_dir=current_dir,
        output_zip=delta_zip,
        changed_files=sorted(changed),
        deleted_files=deleted,
        base_version=base_version_raw,
        target_version=target_version,
    )

    print(f"delta: {delta_zip}")
    print(f"delta-changed: {len(changed)}")
    print(f"delta-deleted: {len(deleted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
