#!/usr/bin/env python3
"""Convert Apps text files to Unix LF. Thin wrapper around fix_lf.py."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.argv = [str(HERE.with_name("fix_lf.py")), str(ROOT / "Apps"), *sys.argv[1:]]
runpy.run_path(str(HERE.with_name("fix_lf.py")), run_name="__main__")
