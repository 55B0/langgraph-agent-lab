# Investigating a controller count failure

This is a fictional interface integration case. The question is: why did the controller count one object in R-206 and none in R-207, even though both runs logged OBJECT_PRESENT at the sensor?

## Evidence

The case lives in `data/cases/controller-mismatch`. Run records link to configurations. Event logs show the sensor decision, digital output, and controller input. Two specifications describe the sensor's output encoding and the controller's input interpretation.

The case has its own source directory so its specification passages remain separate from the original threshold lesson.

## Read the evidence

Run these commands from the project folder in PowerShell.

```powershell
& .\.venv\Scripts\python.exe -m sensorassist --data-dir data/cases/controller-mismatch --read-log R-206
& .\.venv\Scripts\python.exe -m sensorassist --data-dir data/cases/controller-mismatch --read-log R-207
& .\.venv\Scripts\python.exe -m sensorassist --data-dir data/cases/controller-mismatch --tools --before-run R-206 --after-run R-207 --spec-query "output polarity controller input"
```

The log tool reads the file and returns exact line numbers and a source ID. It accepts a run ID and bounded page arguments, keeping filesystem paths outside the model's tool arguments.

## What the evidence supports

- Both logs record OBJECT_PRESENT at line 3.
- R-206 records HIGH output and a controller count of 1 at lines 4-5. R-207 records LOW output and a count of 0.
- The sensor output polarity changed from active_high to active_low. The controller's active level stayed HIGH.
- SPEC-OUTPUT-V1 explains that active_low encodes OBJECT_PRESENT as LOW. SPEC-CONTROLLER-V1 explains that the controller counts only its configured active level.

Together, these artifacts support an interface mismatch as the explanation within this fictional case. The startup LINK_RECOVERED warning appears before both tests, and the controller specification states that input sampling proceeds normally afterward.

The intended interface convention remains unknown. The next question for the human is whether the controller and sensor should use a HIGH or LOW active level. Either side could require a configuration correction depending on that answer.

## Next implementation

These commands expose the evidence for manual inspection. The current ScriptedModel follows the original threshold recipe and does not choose a log investigation strategy. The next step is to connect a real tool-calling model to the existing graph and let it choose between reading runs, reading log pages, comparing configurations, and searching specifications.

Use this question for the first live test:

> Why did R-207 count zero objects when R-206 counted one? Investigate the records, logs, and relevant specifications. Cite the evidence and identify what you still need to ask a human.

The fixed `--graph` assessment implements only the original steady-state detection specification. This case uses a different controller count test.
