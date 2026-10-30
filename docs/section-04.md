# Section 4: evidence tools

A tool wraps a function with a name, description, and input schema. Those definitions will let a model request the function in Section 5. In this section, our code selects the calls so we can inspect and test the tools independently.

## Run it

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m sensorassist --tools
```

The demonstration prints four calls using three tools: read R-104, read R-105, compare their referenced configurations, and search for `detection threshold`. No model or API key is used.

Each call prints `Tool`, `Input`, and `Result`. The result is data returned by the tool, rather than a final diagnosis.

## Contracts

| Tool | Arguments | Successful result |
|---|---|---|
| `read_test_run` | `run_id`, for example `R-105` | `status: found` and the recorded `run` |
| `compare_configs` | `before_config_id`, `after_config_id` | `status: compared`, `source_ids`, and a `changes` list |
| `search_spec` | A `query` containing words or digits, up to 500 characters | `status: found` and a `matches` list with original text and line references |

IDs use `R-` or `CFG-` followed by digits, with a maximum length of 64 characters. The read tool returns a configuration reference; it does not silently retrieve or diagnose the configuration.

For the reference case, `compare_configs` returns a change in `detection_threshold` from `0.4` to `0.7`. It excludes the records' own `source_id` and `config_id` fields from the differences. Presence flags distinguish an absent field from one whose JSON value is `null`.

Search is deterministic keyword lookup over Markdown paragraphs in `data/specs/`. It matches any query word, ranks passages by the number of distinct matched words, and breaks ties by path and line order. Headings and source-ID metadata are excluded from results. It returns at most three passages. Line numbers refer to the original source file and start at 1. No vector database, embeddings, or semantic interpretation are involved.

## Expected missing-data outcomes

- A missing run or configuration returns `status: not_found` and `missing_evidence`.
- A missing or empty specification directory also returns `not_found`.
- Existing specifications with no matching words return `status: no_matches` and `matches: []`.
- An invalid ID or query returns `status: invalid_argument` and a message.

Malformed JSON or inconsistent record identity remains a developer error. Broad recovery behavior will be considered in Section 6. Input types are checked by the tool schema before the function executes.

## Try a missing record

```powershell
& .\.venv\Scripts\python.exe -m sensorassist --tools --after-run R-999
```

The first lookup succeeds, the second returns `not_found`, the demo skips comparison, and specification search still runs. No source files are changed.

## How it is built

`build_tools(data_dir)` returns three LangChain Core tool objects. Each uses the `@tool` decorator, typed arguments, and a description. `.invoke({...})` validates the input and executes the function.

The source directory is configured when the tools are created. It is not a tool argument that the future model can choose. IDs cannot contain file paths, and resolved source paths must stay within the configured data directory. Keep evaluation answers outside that source directory, as in the existing layout.

`langchain-core` is now an explicit project dependency because the tools import it directly. Its pinned version was already present in the dependency snapshot, so no additional third-party dependency version is needed.

The existing graph still performs its Section 3 investigation using its loader. In Section 5, an LLM node will request these tools, an execution node will run them, and results will return to the model through graph state.

## Verification

Run the suite with:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
```

Tests cover actual run contents, configuration changes and changed fixtures, source passage text and line ranges, missing records, invalid IDs, schema boundaries, and the scripted command. The earlier graph and fixture tests remain part of the same suite.

## Official reference

- [Tool names, descriptions, schemas, and execution](https://docs.langchain.com/oss/python/langchain/tools)
