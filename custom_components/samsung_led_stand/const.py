"""Constants for the Samsung SmartThings LED Stand (local) integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "samsung_led_stand"

SCAN_INTERVAL = timedelta(seconds=10)

# Values of the device's `activityLightingMode` resource (verified on the real lamp).
# Samsung app label -> value the lamp reports:
#   학습(언어) reading, 학습(수리) writing, 학습(멀티미디어) computer,
#   야간 night, 수면 sleepPreparation
# Any other value the lamp reports is added to the list automatically.
LIGHTING_MODES: list[str] = ["reading", "writing", "computer", "night", "sleepPreparation"]

# The lamp reports "sleepPreparation" but only accepts "sleep" when writing.
# (Verified: writing "sleep" switches the lamp to sleepPreparation.)
MODE_WRITE_VALUE: dict[str, str] = {"sleepPreparation": "sleep"}
