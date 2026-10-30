"""Shared file loading for the inspector and evidence-state graph.

This helper does no LangGraph routing and makes no diagnosis. Its caller
decides whether missing files should surface as errors or incomplete evidence.
"""

import json
from pathlib import Path


def load_run(data_dir: Path, run_id: str) -> tuple[dict, dict]:
    """Read a recorded run and the configuration it actually references."""
    run_path = data_dir / "runs" / f"{run_id}.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    # Follow the actual reference in the run; do not infer a configuration ID
    # from a similar-looking filename. The link is part of the evidence.
    config_path = data_dir / "configs" / f"{run['config_id']}.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return run, config
