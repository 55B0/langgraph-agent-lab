"""Section 4: reusable evidence functions exposed as named tool objects.

The @tool decorator uses each function's description and typed arguments to
define its model-visible interface. Tools retrieve facts; they do not decide
which tool runs next. That choice belongs to the script or a future model.
"""

import json
import re
from pathlib import Path

from langchain_core.tools import BaseTool, tool


def build_tools(data_dir: Path) -> dict[str, BaseTool]:
    """Bind tools to one source directory, outside their model-visible inputs."""
    # Capture the configured directory here. A model can supply IDs or a query,
    # but the directory itself is not part of any tool's argument schema.
    root = data_dir.resolve()

    def source_path(folder: str, filename: str) -> Path:
        # Resolve links and relative paths before enforcing the source boundary.
        path = (root / folder / filename).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Evidence path must remain inside the configured data directory.")
        return path

    def read_record(folder: str, record_id: str, prefix: str, id_field: str) -> dict:
        # Validate IDs before constructing paths: accept R-105, not a filename
        # or a path into unrelated files such as tests or local credentials.
        if len(record_id) > 64 or not re.fullmatch(rf"{prefix}-[0-9]+", record_id):
            return {"status": "invalid_argument", "message": f"Expected an ID such as {prefix}-104."}
        path = source_path(folder, f"{record_id}.json")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            # not_found is data the caller can act on, not a fabricated record.
            return {"status": "not_found", "missing_evidence": [f"{folder}/{record_id}.json"]}
        if record[id_field] != record_id or record["synthetic"] is not True:
            raise ValueError("Evidence record identity or synthetic label is inconsistent.")
        return {"status": "found", "record": record}

    # The following decorated functions become invokable tools with schemas.
    @tool
    def read_test_run(run_id: str) -> dict:
        """Read a fictional test run by ID, for example R-105.

        Returns recorded observations, outcome, configuration ID, and source ID.
        Use compare_configs separately to inspect configuration changes.
        """
        result = read_record("runs", run_id, "R", "run_id")
        if result["status"] != "found":
            return result
        return {"status": "found", "run": result["record"]}

    @tool
    def compare_configs(before_config_id: str, after_config_id: str) -> dict:
        """Compare two fictional configurations, such as CFG-104 and CFG-105.

        Returns changed fields and both source IDs. Identity fields are excluded
        from the changes. This tool returns differences, not a diagnosis.
        """
        before = read_record("configs", before_config_id, "CFG", "config_id")
        after = read_record("configs", after_config_id, "CFG", "config_id")
        for result in (before, after):
            if result["status"] == "invalid_argument":
                return result
        missing = [path for result in (before, after) for path in result.get("missing_evidence", [])]
        if missing:
            return {"status": "not_found", "missing_evidence": list(dict.fromkeys(missing))}
        before_record, after_record = before["record"], after["record"]
        changes = []
        # An absent field and an explicit JSON null are different changes.
        absent = object()
        # Record IDs identify the two inputs; their difference is not a changed
        # sensor setting. Source IDs are returned separately for citations.
        fields = (before_record.keys() | after_record.keys()) - {"source_id", "config_id"}
        for field in sorted(fields):
            if before_record.get(field, absent) != after_record.get(field, absent):
                changes.append({
                    "field": field,
                    "before": before_record.get(field),
                    "after": after_record.get(field),
                    "before_present": field in before_record,
                    "after_present": field in after_record,
                })
        return {
            "status": "compared",
            "source_ids": [before_record["source_id"], after_record["source_id"]],
            "changes": changes,
        }

    @tool
    def search_spec(query: str) -> dict:
        """Search fictional specifications using words such as detection threshold.

        Returns up to three matching paragraphs with source IDs, exact text,
        and line numbers. This is literal keyword search, not semantic search.
        """
        # Literal keyword matching keeps retrieval transparent and reproducible.
        # This does not use embeddings or understand synonyms.
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        if not terms or len(query) > 500:
            return {"status": "invalid_argument", "message": "Use a nonempty query of at most 500 characters containing letters or digits."}
        spec_dir = source_path("specs", ".")
        if not spec_dir.is_dir():
            return {"status": "not_found", "missing_evidence": ["specs/"]}
        spec_files = sorted(spec_dir.glob("*.md"))
        if not spec_files:
            return {"status": "not_found", "missing_evidence": ["specs/*.md"]}
        matches = []
        for candidate in spec_files:
            path = source_path("specs", candidate.name)
            lines = path.read_text(encoding="utf-8").splitlines()
            start = 0
            # Blank lines delimit paragraphs. Keep the original line positions
            # so each returned quotation can be checked against its source file.
            for end in range(len(lines) + 1):
                if end < len(lines) and lines[end].strip():
                    continue
                text = "\n".join(lines[start:end])
                matched = terms & set(re.findall(r"[a-z0-9]+", text.lower()))
                if text and matched and not text.startswith(("#", "Source ID:")):
                    matches.append({
                        "source_id": path.stem,
                        "path": f"specs/{candidate.name}",
                        "start_line": start + 1,
                        "end_line": end,
                        "text": text,
                        "matched_terms": sorted(matched),
                    })
                start = end + 1
        # More matched query words rank first; ties have a stable source order.
        matches.sort(key=lambda match: (-len(match["matched_terms"]), match["path"], match["start_line"]))
        return {"status": "found" if matches else "no_matches", "matches": matches[:3]}

    return {item.name: item for item in (read_test_run, compare_configs, search_spec)}
