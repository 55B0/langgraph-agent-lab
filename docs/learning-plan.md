# SensorAssist: build and learning plan

## Goal and working method

Build SensorAssist yourself in small increments and understand its graph well enough to explain and change it. Python is the implementation language; explanations focus on LangGraph and the application behavior.

Use sessions of roughly 60-90 minutes. Split longer sections across sessions instead of treating their upper estimate as a deadline.

The estimates describe time spent learning and experimenting. Setup and implementation can be delegated to the assistant, followed by a short walkthrough. Sections 1-3 have been prepared this way; see the [Section 1 walkthrough](section-01.md), [Section 2 walkthrough](section-02.md), and [Section 3 walkthrough](section-03.md).

For each increment:

1. Explain one concept and why the investigation needs it.
2. Sketch the path and predict the state update.
3. Implement a small change together; leave a meaningful modification for you to make.
4. Run the graph and inspect the actual state updates or tool calls.
5. Change one input or failure condition and explain the new outcome.
6. Add a focused check and update the relevant documentation.

Commits and pushes require explicit approval. Before each one, verify the Uni account **55B0** and the destination **55B0/langgraph-agent-lab**. Show the changes and proposed commit message before asking. Keep identity configuration local to this project.

## Time budget

| Section | Estimate | Visible result |
|---|---:|---|
| 1. Setup and case | 60-90 min | Reproducible environment and a case we can explain by hand |
| 2. First graph | 60-90 min | A running graph with visible state updates |
| 3. Routing | 45-75 min | Different paths for complete and incomplete evidence |
| 4. Tools | 60-90 min | Three independently verifiable evidence tools |
| 5. Agent loop | 90-150 min | A model chooses tools and consumes their results |
| 6. Reliable outcomes | 60-120 min | Structured reports and bounded failure handling |
| 7. Human input and persistence | 90-150 min | A paused investigation survives a process restart |
| 8. Evaluation and presentation | 120-180 min | Baseline comparison, documented results, and a short demo |

The sum is about **10-16 focused hours**. Reserve **12-20 hours** including environment, provider setup, and debugging. These are estimates for a deliberately small implementation. Reassess them after section 2 and again after the first live model run.

The first executable graph should appear after about 2-3 focused hours. The first model-driven investigation should appear after about 5-8.5 hours. Finish a section's completion criteria before adding the next feature.

## Section 1: local setup and a verifiable case

**Time:** 60-90 minutes.

**Understand:** the distinction between a request, evidence, an expected test outcome, and an investigation's conclusion.

**Build:** verify the repository remote and Uni author identity, prepare a Python 3.11 virtual environment, declare initial dependencies, and ignore generated files and credentials before staging anything. Create two fictional run records, their configuration records, and a short behavior specification. Use stable IDs and explicit run-to-configuration references.

Use the README's R-104/R-105 threshold example. Keep expected investigation answers in test/evaluation data that the future agent's tools cannot access.

**Your experiment:** calculate both detection results yourself, then change only the second threshold. Explain which observation or conclusion changes.

**Done when:** the environment can import LangGraph, the artifacts are internally consistent, and you can explain why the evidence does not prove whether the configuration change was intentional. Record the working setup commands and dependency versions.

## Section 2: state, nodes, and the first graph

**Time:** 60-90 minutes.

**Understand:** `StateGraph`, a state schema, node updates, fixed edges, `START`, `END`, compilation, and invocation.

**Build:** a deterministic graph that loads the known case, assesses its recorded values against the fictional rule, and formats a short report. Initial state holds the requested run IDs, evidence, status, and report. Define each field because a node needs to read or write it.

```text
START -> load_case -> assess_case -> report -> END
```

Stream state updates so we can inspect the input and output of each step. Label this version as a scripted workflow. Add one meaningful check of its result and evidence references.

**Your experiment:** add a small report field yourself. Predict which node should write it and which node should read it.

**Done when:** you can reconstruct the execution path and explain how a node's returned update changes the shared state.

## Section 3: conditional routing and incomplete evidence

**Time:** 45-75 minutes.

**Understand:** conditional edges, explicit statuses, and reducer behavior. Observe the difference between overwriting a field and accumulating entries.

**Build:** a branch after loading the case. Complete evidence continues to assessment; a missing required record produces an incomplete result. At this stage it returns a missing-information request; actual pause/resume comes in section 7.

```text
START -> load_case -> assess_case -> report -> END
                  -> missing_data -> END
```

**Your experiment:** use an unknown run ID, remove a configuration record, and restore the artifacts with unchanged thresholds. Predict the path and whether the original explanation remains supported.

**Done when:** the graph follows the expected branches, tests cover the outcomes, and missing data does not produce an invented explanation.

## Section 4: evidence tools

**Time:** 60-90 minutes.

**Understand:** a tool schema, argument validation, returned observations, and the distinction between retrieving facts and drawing conclusions.

**Build:** three narrow, read-only tools:

| Tool | Input | Output |
|---|---|---|
| `read_test_run` | Run ID | Recorded results, configuration reference, and source ID |
| `compare_configs` | Two configuration IDs | Changed fields with before/after values and source IDs |
| `search_spec` | Query | Relevant local passages and source IDs |

Start specification search with a simple local lookup. Tools must only access source artifacts, not expected evaluation answers. Give missing records and empty search results explicit outcomes. Test the data transformations independently of an LLM.

**Your experiment:** change a configuration value and verify that the comparison tool reports the actual change. Query for a term absent from the specification and inspect the empty result.

**Done when:** every tool has a clear contract, predictable missing-data behavior, and results you can verify manually. No tool secretly performs the whole diagnosis.

## Section 5: the tool-calling agent loop

**Time:** 90-150 minutes, including basic provider setup.

**Understand:** model tool binding, AI tool requests, tool-result messages, matching call IDs, accumulated message state, and the edge that routes back to the model.

**Build:** choose a tool-calling model and its integration, configure local credentials, and connect one model node to one explicit tool execution node. Use LangGraph's Graph API so the execution path remains visible. Keep scripted graph tests separate from live model runs.

```text
START -> model -> requested tools -> model
              -> final report -> END
```

Enforce an initial six-tool-call budget in code before execution, counting every individual call even if several arrive in one request. Also bound model turns, per-call timeouts, and retries so the investigation has a finite execution budget. Provide a bounded stop outcome. Preserve the tool-message protocol when rejecting or stopping requests.

**Your experiment:** compare a question about one run with a question comparing two runs. Inspect the selected tools and arguments; explain what evidence each result adds. Do not require one exact call sequence when several are valid.

**Done when:** a live model selects and consumes evidence tools, produces a supported answer, and cannot continue beyond the budget. You can distinguish model choices from transitions enforced by graph code.

## Section 6: structured reports and reliable failure behavior

**Time:** 60-120 minutes.

**Understand:** output validation, expected tool errors, bounded retries, and the difference between a valid reference and a supported claim.

**Build:** report fields for status, explanation, evidence IDs, missing information, and next check. Mechanically verify that cited IDs were retrieved. Inspect whether the referenced content supports each substantive claim. Handle expected missing data and recoverable tool errors explicitly; surface unexpected programming errors during development.

Add checks for a missing specification, contradictory artifacts, a tool failure, and budget exhaustion. Avoid asserting the model's exact wording. Do not use a self-reported confidence score as evidence of accuracy.

**Your experiment:** temporarily fail one tool, then supply conflicting records. Inspect whether the report preserves the uncertainty and stops appropriately.

**Done when:** the program produces supported findings or a useful unresolved report, and tests verify that failures cannot cause endless execution.

## Section 7: checkpointing, human input, and restart

**Time:** 90-150 minutes.

**Understand:** a checkpointer, `thread_id`, `interrupt()`, `Command(resume=...)`, and node re-execution on resume. Distinguish investigation state from cross-thread long-term memory.

**Build:** ask the user whether the threshold change was intentional when that answer is necessary for the next recommendation. Start with an in-memory checkpointer to inspect the mechanics; then use a local SQLite-backed checkpointer for process restart. Resume the saved investigation with the same thread ID.

Operations before an interrupt can run again when its node resumes. Keep them repeatable, and avoid introducing actions that would be duplicated. Keep generated checkpoint data out of version control.

**Your experiment:** pause, close the process, restart, and answer the question. Repeat with a different thread ID to verify that independent investigations do not share evidence.

**Done when:** restart/resume works, the human answer changes the recommendation appropriately, and the tests show that thread state stays isolated.

## Section 8: evaluation, README, and demonstration

**Time:** 120-180 minutes.

**Understand:** graph correctness versus model quality, a baseline, held-out cases, and the limits of evidence from a small synthetic dataset.

**Build:** compare the adaptive agent with a fixed evidence-retrieval workflow using the same model, source artifacts, and report requirements. Use the threshold case plus unchanged configuration, unknown run, missing specification, conflicting evidence, tool failure, and budget exhaustion. Add a pause/resume integration check.

Keep evaluation answers outside the tool-accessible data and add held-out variations. Record supported conclusions, unsupported claims, appropriate unresolved outcomes, tool calls, latency, and model usage. Use comparable budgets for the baseline and agent, and document any differences in evidence provided to the model. Repeat a few live cases and record the model and dependency versions. Report failures as well as successes; the agent is not required to outperform the simpler workflow.

Keep ordinary tests independent of paid API access. Prepare CI for those tests when publication is approved; make live model evaluation a separate explicit action. Update the README with commands that were actually executed successfully, a graph diagram, measured results, current limitations, and implemented versus planned features.

**Your experiment:** present one explained failure, one unresolved case, and one paused/resumed investigation in a 3-5 minute demo. Answer: why did this graph structure help, and what would a simpler implementation do equally well?

**Done when:** another developer can reproduce the demonstration, and you can explain state updates, tool choices, stopping, persistence, and evaluation without reading a prepared answer.

## Milestones and review points

- After section 3: a small reproducible LangGraph workflow with conditional routing.
- After section 5: the first genuine tool-using agent.
- After section 7: a stateful investigation with human input and durable resume.
- After section 8: an evaluated portfolio demonstration with accurate documentation.

At each milestone, review the diff, test evidence, Uni identity, and proposed commit message. Ask for approval before each commit and each push. A documentation-only first commit can be reviewed before implementation, but this plan does not authorize it.

## GitHub repository description

> Learning LangGraph by building an agent that investigates fictional sensor software test failures.

## Official reading, used as needed

Read the relevant page while implementing its concept rather than completing a long tutorial first.

- Sections 2-3: [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
- Sections 4-5: [Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart) and [workflows versus agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents).
- Section 7: [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
- Throughout: [Testing graphs](https://docs.langchain.com/oss/python/langgraph/test).
