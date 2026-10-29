"""Read the synthetic records that future graph nodes will use."""

import json
from pathlib import Path


def load_run(data_dir: Path, run_id: str) -> tuple[dict, dict]:
    """Read a recorded run and the configuration it actually references."""
    run_path = data_dir / "runs" / f"{run_id}.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    config_path = data_dir / "configs" / f"{run['config_id']}.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return run, config
