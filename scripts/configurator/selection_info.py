"""Explicit read-only selected-for-next-start inspection, never running-state claims."""
from dataclasses import dataclass,field
from pathlib import Path
from .selection import inspect_selection,read_revision,REVISIONS
from .workspace import open_view
from .cloud_capture import describe_capture
from .observation_capture import describe as describe_observations
from .resources import safe


@dataclass(frozen=True)
class SelectedScene:
    selection:object
    root:Path
    record:dict|None=field(default=None,repr=False)
    document:object=field(default=None,repr=False)

    @property
    def native_path(self):
        return self.root/REVISIONS/self.selection.revision/self.record['snapshot_config'] if self.record else None

    def sections(self):
        lines=['Selected for the NEXT explicit start/restart — not a claim about the running renderer. No service or process inspection occurred.']
        if self.record is None:
            return lines+['Selection: custom configuration default (no selector). The desktop path will use personal xp.def/xp.conf. This inspector does not read or execute them.']
        record=self.record;view=self.document.view
        lines += [safe('Revision: '+self.selection.revision+'\nOriginal library source: '+record['scene']+'\nImmutable native snapshot: '+str(self.native_path)),
                  safe('Selected local renderer: '+record['renderer']['path']+'\nReviewed desktop geometry: '+record['geometry']+'\nStored native preview geometry: '+view.geometry),
                  safe('Native scene: '+view.summary()),
                  'Known snapshot/resource hashes verified at this check. Stock/implicit resources, desktop capability and actual running state are not certified. Later library edits do not change this revision.',
                  'Opening the native snapshot uses its stored preview geometry, not an implicit desktop-geometry override. The current editor renderer is retained. Save creates a new library copy; the revision/selector stay unchanged.']
        if self.document.capture:
            lines.append('Frozen cloud metadata; active now: '+str(view.uses_capture())+'\n'+describe_capture(self.document.capture.metadata))
        if self.document.observations:
            lines.append('Frozen observation metadata; active layers: '+(', '.join(view.uses_observations()) or 'none')+'\n'+describe_observations(self.document.observations))
        return lines


def inspect_selected(root):
    root=Path(root);selection=inspect_selection(root)
    if selection.revision is None:return SelectedScene(selection,root)
    record=read_revision(root,selection.revision)
    document=open_view(root/REVISIONS/selection.revision/record['snapshot_config'])
    # Refuse a changing selection rather than presenting a mixed report.
    if inspect_selection(root)!=selection:raise ValueError('Selection changed during inspection; refresh explicitly.')
    return SelectedScene(selection,root,record,document)
