#!/usr/bin/env python3
"""Deep Research Engine v14.1 — Headless Notebook Execution & Verification.

Fail-closed nbformat v4 validation + headless notebook execution via nbclient.
Produces tamper-evident `notebook_execution_receipt.json`.

Stdlib + nbformat/nbclient. Windows UTF-8-safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def verify_notebook(nb_path: Path, timeout: int = 300) -> dict[str, Any]:
    """Execute all code cells headlessly and return execution receipt dict."""
    import nbformat  # hard dependency: absence = FAIL, never skip
    from nbclient import NotebookClient

    if not nb_path.exists():
        return {
            "notebook": nb_path.name,
            "passed": False,
            "error": f"Notebook file not found: {nb_path}",
        }

    nb = nbformat.read(nb_path, as_version=4)
    nbformat.validate(nb)  # raises ValidationError -> FAIL

    client = NotebookClient(
        nb,
        timeout=timeout,
        kernel_name="python3",
        allow_errors=False,
        resources={"metadata": {"path": str(nb_path.parent)}},
    )
    client.execute()

    errors = [
        o
        for c in nb.cells
        if c.cell_type == "code"
        for o in c.get("outputs", [])
        if o.get("output_type") == "error"
    ]

    nb_sha = hashlib.sha256(nb_path.read_bytes()).hexdigest()

    receipt: dict[str, Any] = {
        "notebook": nb_path.name,
        "notebook_sha256": nb_sha,
        "nbformat": nb.nbformat,
        "nbformat_minor": nb.nbformat_minor,
        "cells": len(nb.cells),
        "code_cells": sum(c.cell_type == "code" for c in nb.cells),
        "cell_errors": [f"{e.get('ename')}: {e.get('evalue')}" for e in errors],
        "passed": not errors,
    }
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Headless Jupyter Notebook execution verifier.")
    ap.add_argument("notebook", type=Path, help="Path to notebook (.ipynb)")
    ap.add_argument("--receipt", type=Path, default=None, help="Path to write receipt (.json)")
    ap.add_argument("--timeout", type=int, default=300, help="Per-cell timeout in seconds")
    a = ap.parse_args(argv)

    try:
        r = verify_notebook(a.notebook, a.timeout)
    except Exception as e:
        nb_sha = hashlib.sha256(a.notebook.read_bytes()).hexdigest() if a.notebook.exists() else None
        r = {
            "notebook": a.notebook.name,
            "notebook_sha256": nb_sha,
            "passed": False,
            "error": f"{type(e).__name__}: {e}",
        }

    if a.receipt:
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
