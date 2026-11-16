"""Headless checks of the project-level selection and of the tools that use it.

Each sel_*.py script builds a real ProjectWindow (and, where needed, real views) with an offscreen
Qt platform, prints one PASS/FAIL line per check and ends with "RESULT: ALL PASSED" or
"RESULT: FAILED". This module runs every script in its own process, so that Qt/VTK state does not
leak between them. Run with:

    pytest tests/selection

or run a single script directly, e.g. python tests/selection/sel_trees.py
(sel_tables_part.py is not a standalone script: it is executed by sel_store_and_tables.py).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = sorted(p for p in HERE.glob("sel_*.py") if p.name != "sel_tables_part.py")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_selection_script(script):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=900,
        env=env,
        cwd=HERE.parents[1],
    )
    output = result.stdout + result.stderr
    failed_checks = [line for line in output.splitlines() if line.startswith("FAIL ")]
    assert "RESULT: ALL PASSED" in output, (
        f"{script.name} did not pass.\nFailed checks: {failed_checks}\n"
        f"Last output:\n{output[-3000:]}"
    )
