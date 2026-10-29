# Section 1: environment and first case

Section 1 prepares the evidence that the first LangGraph workflow will process. The current command is a deterministic inspector; graph orchestration comes in section 2.

Verified locally on Windows with Python 3.11.7 and LangGraph 1.2.18: the inspector runs, all three fixture checks pass, `StateGraph` imports successfully, and `pip check` reports no broken requirements. Dependency versions are recorded in `requirements.lock`.

## What is available

- `pyproject.toml`: project metadata, the LangGraph dependency, and the test dependency.
- `requirements.lock`: resolved third-party dependencies for the verified Windows/Python 3.11 environment.
- `data/runs/`: two fictional test runs with configuration and specification references.
- `data/configs/`: the configuration used by each run.
- `data/specs/SPEC-DETECTION-V1.md`: the fictional detection rule.
- `src/sensorassist/`: a small evidence loader and command-line inspector.
- `tests/test_case_data.py`: consistency checks and expected outcomes, outside the future agent's source data directory.

## Understand the result

The rule is `signal >= detection_threshold`:

| Run | Comparison | Actual detection | Expected detection | Test outcome |
|---|---|---|---|---|
| R-104 | 0.55 >= 0.40 | true | true | passed |
| R-105 | 0.55 >= 0.70 | false | true | failed |

The changed threshold explains the recorded change. The fixture keeps the sensor, firmware version, test ID, input signal, and test expectation the same. It does not establish whether the threshold change was intentional. That missing intent matters when deciding whether to change the configuration or the test expectation.

All records and rules are synthetic and deliberately simplified.

## Run it

After following the setup commands in the [README](../README.md), use these commands from the repository root:

```powershell
& .\.venv\Scripts\python.exe -m sensorassist
& .\.venv\Scripts\python.exe -m pytest -q
```

The inspector reads from `data/` by default. To inspect a different copy of the evidence, supply `--data-dir` followed by its directory path.

## Optional two-minute experiment

Predict what happens if the second threshold changes from `0.70` to `0.50`. The rule would then predict detection. Changing configuration alone would make the unchanged recorded `actual_detection: false` inconsistent with the fictional specification, and the fixture checks should fail.

This distinguishes changing a configuration record from generating a new test run. Prefer a separate copy of `data/` for this experiment so the reference case stays intact.

## What becomes LangGraph next

The next step will give the workflow explicit shared state and three nodes:

```text
START -> load_case -> assess_case -> report -> END
```

The loader will place evidence into state. Assessment will add findings. The report node will consume those findings. Inspecting each node's state update is the first LangGraph lesson.
