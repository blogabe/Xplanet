"""Shared bindings for the two editable cloud appearance numbers.

Scene-version gates and the rules for selecting cloud imagery stay in the model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CloudControl:
    name: str
    label: str
    minimum: float
    maximum: float
    default: float
    editor_suffix: str
    native_hint: str
    whole: bool = False

    @property
    def limits(self):
        return (self.label, self.minimum, self.maximum)

    @property
    def bounds_text(self):
        return f"{self.minimum:g}–{self.maximum:g}"

    @property
    def input_id(self):
        return self.name.replace("_", "-")

    @property
    def definition_key(self):
        return "XPLANET_" + self.name.upper()


CLOUD_GAMMA = CloudControl(
    "cloud_gamma",
    "Cloud gamma",
    0.1,
    5,
    1,
    " (studio range)",
    "Cloud brightness gamma; no cloud map is enabled or inferred.",
)
CLOUD_THRESHOLD = CloudControl(
    "cloud_threshold",
    "Cloud threshold",
    0,
    255,
    90,
    " whole brightness level",
    "Hide cloud pixels below this {bounds} threshold; requires an existing cloud map.",
    whole=True,
)
# Membership and order are part of the native scene format from v5 onward.
CLOUD_CONTROLS = (CLOUD_GAMMA, CLOUD_THRESHOLD)
