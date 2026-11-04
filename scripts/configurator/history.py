"""Session-local draft history; raw edits are retained without validating them."""
import math
from .model import NUMERIC_FIELDS


def comparable(field, value):
    if field in NUMERIC_FIELDS:
        try:
            numeric = float(value)
            if math.isfinite(numeric):
                return numeric
        except (ValueError, TypeError):
            pass
    return value


class DraftHistory:
    """Bounded snapshots with an independent baseline and input-edit grouping."""
    def __init__(self, values, limit=100):
        if limit < 1:
            raise ValueError('History limit must be positive.')
        self.limit = limit
        self.reset(values)

    def reset(self, values):
        self.baseline = dict(values)
        self._states = [dict(values)]
        self._index = 0
        self.break_group()

    def mark_saved(self):
        """Advance the baseline without dropping undo/capture history."""
        self.baseline=self.current
        self.break_group()

    @property
    def current(self):
        return dict(self._states[self._index])

    @property
    def can_undo(self):
        return self._index > 0

    @property
    def can_redo(self):
        return self._index < len(self._states) - 1

    def break_group(self):
        self._group = None

    def record(self, values, group=None):
        if values.keys() != self.baseline.keys():
            raise ValueError('A draft must retain the same fields.')
        values = dict(values)
        if values == self.current:
            return
        self._states = self._states[:self._index + 1]
        if group is not None and group == self._group and self.can_undo:
            self._states[self._index] = values
        else:
            self._states.append(values)
            if len(self._states) > self.limit + 1:
                self._states.pop(0)
            self._index = len(self._states) - 1
        self._group = group

    def undo(self):
        self.break_group()
        if self.can_undo:
            self._index -= 1
        return self.current

    def redo(self):
        self.break_group()
        if self.can_redo:
            self._index += 1
        return self.current

    def changes(self):
        return [(field, before, self.current[field])
                for field, before in self.baseline.items()
                if comparable(field, before) != comparable(field, self.current[field])]

    @property
    def dirty(self):
        return bool(self.changes())
