# Fictional sensor output interface

Source ID: SPEC-OUTPUT-V1

All behavior in this document is synthetic and describes this learning case.

## Output polarity

The sensor first makes an internal object decision. The output polarity determines how that decision is encoded on the digital output. With active_high polarity, OBJECT_PRESENT produces HIGH and OBJECT_ABSENT produces LOW. With active_low polarity, OBJECT_PRESENT produces LOW and OBJECT_ABSENT produces HIGH.

## Internal sensing

The sensor reports OBJECT_PRESENT when the signal is at least the configured detection_threshold. Changing output polarity does not change this internal decision.
