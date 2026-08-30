"""Process fixture that terminates after a durable solver activity completes."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from amra.config import Settings
from amra.workflows.models import ActivityCommand
from amra.workflows.worker import LocalActivityHandlers


async def main() -> None:
    artifact_root, workspace_root, command_path, cadical, drat_trim, cake_lpr = map(
        Path, sys.argv[1:]
    )
    handlers = LocalActivityHandlers(
        Settings(
            artifact_root=artifact_root,
            workspace_root=workspace_root,
            cadical_path=cadical,
            drat_trim_path=drat_trim,
            cake_lpr_path=cake_lpr,
        )
    )
    command = ActivityCommand.model_validate_json(command_path.read_bytes())
    result = await handlers.solve(command)
    if result.checkpoint != "solver-output-durable":
        raise RuntimeError("solver output was not durable before termination")
    os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    asyncio.run(main())
