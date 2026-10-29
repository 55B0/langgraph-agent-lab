# Fictional detection specification

Source ID: `SPEC-DETECTION-V1`.

This specification and all related sensor data are synthetic. They describe a learning fixture, not a real product.

## Recorded behavior

- The normalized input signal and configured detection threshold are numbers between 0 and 1.
- Detection is `true` when `signal >= detection_threshold` and `false` otherwise.
- Equality therefore counts as detection.
- A test passes when the actual detection equals the test's expected detection.

This deliberately simplified fixture describes steady-state behavior. Timing, physical optics, electrical behavior, and real firmware execution are outside its scope.

## Missing information

The records do not state whether the threshold change between CFG-104 and CFG-105 was intentional. Confirm that intent before deciding whether to change configuration or test expectations.
