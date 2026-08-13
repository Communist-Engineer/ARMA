from __future__ import annotations

import os
from pathlib import Path

import pytest

from amra.adapters.execution.sat import SatToolchain, ToolPin

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def toolchain() -> SatToolchain:
    binary_root = ROOT / "build/toolchain/bin"
    paths = {
        "cadical": Path(os.environ.get("AMRA_CADICAL_PATH", binary_root / "cadical")),
        "drat-trim": Path(os.environ.get("AMRA_DRAT_TRIM_PATH", binary_root / "drat-trim")),
        "cake_lpr": Path(os.environ.get("AMRA_CAKE_LPR_PATH", binary_root / "cake_lpr")),
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        pytest.skip("proof toolchain has not been built: " + ", ".join(missing))
    return SatToolchain(
        ToolPin(
            "cadical",
            paths["cadical"],
            "c60730422e758ef1cebe7aeddf2dda31c996bf04",
            "https://github.com/arminbiere/cadical",
            "local-test-build",
        ),
        ToolPin(
            "drat-trim",
            paths["drat-trim"],
            "2e3b2dc0ecf938addbd779d42877b6ed69d9a985",
            "https://github.com/marijnheule/drat-trim",
            "local-test-build",
        ),
        ToolPin(
            "cake_lpr",
            paths["cake_lpr"],
            "a36874a8b750b43fe4b385b8ddbf5b033e46a3fa",
            "https://github.com/tanyongkiam/cake_lpr",
            "local-test-build",
        ),
    )
