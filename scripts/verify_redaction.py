#!/usr/bin/env python3
"""Search output files for forbidden terms without modifying them."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def terms_from_manifest(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = data.get("forbidden_terms", [])
    if not isinstance(terms, list) or not all(isinstance(x, str) for x in terms):
        raise ValueError("forbidden_terms must be a list of strings")
    return [x for x in terms if x]


def read_ooxml(path: Path) -> tuple[str, list[str]]:
    chunks: list[str] = []
    warnings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith((".xml", ".rels", ".txt", ".vml")):
                try:
                    chunks.append(archive.read(name).decode("utf-8", errors="ignore"))
                except Exception as exc:
                    warnings.append(f"{name}: {exc}")
    return "\n".join(chunks), warnings


def read_pdf(path: Path) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages), []
    except Exception as first_error:
        exe = shutil.which("pdftotext")
        if exe:
            proc = subprocess.run([exe, str(path), "-"], capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                return proc.stdout, [f"pypdf unavailable/failed: {first_error}"]
            return "", [f"pypdf failed: {first_error}", f"pdftotext failed: {proc.stderr.strip()}"]
        return "", [f"PDF extraction unavailable: {first_error}"]


def inspect(path: Path) -> tuple[str, list[str]]:
    if path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
        return read_ooxml(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    try:
        return path.read_text(encoding="utf-8", errors="ignore"), []
    except Exception as exc:
        return "", [str(exc)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    terms = terms_from_manifest(args.manifest)
    report: dict[str, object] = {"files": [], "terms_checked": len(terms)}
    found_any = False
    incomplete = False

    for path in args.files:
        entry: dict[str, object] = {"file": str(path), "found": [], "warnings": []}
        if not path.is_file():
            entry["warnings"] = ["file not found"]
            incomplete = True
        else:
            body, warnings = inspect(path)
            entry["warnings"] = warnings
            if not body and warnings:
                incomplete = True
            found = [term for term in terms if term in body]
            entry["found"] = found
            found_any = found_any or bool(found)
        report["files"].append(entry)  # type: ignore[union-attr]

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.write_text(output + "\n", encoding="utf-8")
    print(output)
    if incomplete:
        return 3
    return 2 if found_any else 0


if __name__ == "__main__":
    sys.exit(main())
