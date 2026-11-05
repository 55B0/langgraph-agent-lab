# Fictional controller input interface

Source ID: SPEC-CONTROLLER-V1

All behavior in this document is synthetic and describes this learning case.

## Input interpretation

For each test object, the controller samples the input three milliseconds after the sensor's internal object decision. It increments object_count only when input_level equals controller_active_level. The value in the saved configuration is the value actually used during the run. HIGH and LOW represent the two digital levels, not the sensor's internal object decision.

## Startup warning

LINK_RECOVERED means the link was restored before the test began. Input sampling proceeds normally after that event. A LINK_RECOVERED warning does not by itself establish the cause of a later object count failure.

## Intended interface

The records show the configured output polarity and active level. They do not establish which interface convention the installation was intended to use. Confirm that convention with the configuration owner before recommending a change to either device.
