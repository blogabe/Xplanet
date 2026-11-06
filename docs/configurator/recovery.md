# Draft recovery and leaving the editor

Recovery is private editing data under `.state/configurator/drafts`, not a native
scene save, installation setting or desktop-selection journal. Merely opening a
clean editor or browsing recovery creates no files. The first changed studio draft
can create a private session. Native `.def`/`.conf` files are never autosaved.

## Keys and exit choices

- **Ctrl-C during a preview, capture or framing set** cancels that owned operation
  and keeps the editor, draft and previous successful output. Another Ctrl-C
  during cancellation escalates to emergency exit.
- **Ctrl-C while idle** exits promptly using whatever checkpoint already completed.
  It does not wait for a fresh capture-sized checkpoint or save native files.
- **Ctrl-D / Ctrl-Q**, main **Escape**, or **Cancel** requests exit. For a dirty
  studio draft, choose **Keep editing**, **Keep recovery draft and exit**, or
  **Discard draft and exit**. Keep editing has initial focus. Keeping recovery
  checkpoints the latest fields first; a failed checkpoint leaves the editor open.
  An exit request cancels active work before presenting this choice. Keep editing
  retains the draft and last successful output, but does not resume that operation.
- Escape inside a dialog normally returns from that dialog. Open editable dialog
  fields are not included in studio recovery. An exit request from such a form
  requires explicit discard or continued editing; keeping a recovery draft is
  disabled there rather than falsely claiming those fields were saved.

The real CLI returns 130 for an idle/emergency Ctrl-C or external SIGINT, 143 for
SIGTERM and 129 for SIGHUP. Normal cancellation remains 3; an explicitly kept
recovery draft is a completed operation (0). An uncertain scene-selection outcome
keeps its existing attention-required status 5 and diagnostic. Prior native saves
and explicit selections persist; exiting never rolls them back or restarts.

External termination and a disconnected terminal request cleanup without an
unanswerable prompt. Only owned worker process groups are signaled: TERM, up to
two seconds of wait, then KILL as needed. Emergency escalation skips that grace
period. Cleanup is coordinated so repeated requests do not signal the same killed
group again. This is separate from the shell's intentional broad desktop Stop.
SIGKILL, power loss, an unwritable/disconnected terminal and blocking filesystem
calls cannot guarantee final output, terminal restoration or the newest draft.

## Checkpoints and recovery

After edits, checkpointing is debounced for about one second, with a five-second
scheduling ceiling during continuous editing. Busy filesystem operations can take
longer. The recovery line reports success or failure; an older checkpoint is never
presented as the newest unsaved text. Emergency exit reports that recent changes
may be absent.

A checkpoint preserves bounded raw fields, including invalid numeric text and
inactive choices, the comparison baseline, a recognized body-config snapshot and
referenced frozen cloud/observation bytes with their existing provenance. Producer
source/configuration fields are transient and excluded. Private source/executable
hints can be present; treat the recovery folder as local personal data. Preview
images, the undo stack, open dialog forms, provider operations, jobs and selection
operations are not checkpointed or replayed.

Choose **Recovery drafts…**, select a session and **Inspect checkpoint**. Inspection
verifies its hash-bound files and reports when an older complete checkpoint is used.
**Recover inspected draft** copies fields into the editor without rereading the
original source or running anything. The current local executable stays selected
by default. A checkbox explicitly permits restoring the recorded executable as
proposed text; even then Preview remains a separate validated action. Invalid
inputs remain available to correct. The baseline is retained for change review;
undo starts afresh. The original recovery session remains until explicitly discarded.

Separate session identifiers and OS locks protect concurrent editors. An active
session cannot be recovered/discarded by another editor. Opening another document
retains earlier complete checkpoints rather than overwriting that document's
recovery namespace. A successful native save or explicit discard retires only the
current session's verified recovery material; changed/unknown material is retained
with a warning if cleanup cannot be proved safe.

## Bounds and failures

Two complete checkpoints are indexed per session. Capture blobs are content-addressed
and reused, rather than rewritten for every keystroke. New data is flushed before
an atomic index replacement; older unreferenced bytes belonging to that session
can then be removed. No other unsaved session is automatically evicted.

The initial aggregate recovery budget is 256 MiB, including partial/unknown files;
there are also bounded metadata, object, directory-entry and session counts.
Existing capture validation/size limits still apply. A full budget, busy writer,
permission problem or interrupted write preserves earlier complete checkpoints
and reports a warning. Save a native copy or explicitly discard an unwanted verified
session. There is no automatic age purge or permission repair.

Recovery directories/files must be real, private and user-owned; links, unsafe
paths and unsupported versions are refused. A corrupt latest checkpoint may fall
back to the previous complete one, explicitly labeled. If neither validates, data
stays in place for inspection. Unknown material left by an uncatchable crash is
not silently deleted. These checks handle cooperative concurrent changes and
accidental corruption; they are not a security sandbox against the same user
continuously rewriting storage.

## Filesystem operations and interruption

Opening, saving, handoff verification/selection and recovery inspection use one
owned filesystem worker per operation. The editor stays responsive and prevents
conflicting edits while a captured save or open is reconciled. Cancellation is
cooperative at bounded read/write boundaries; the editor waits for its worker,
including cleanup, rather than leaving a writer running after exit. Slow storage
can still delay completion. A selector already published is verified and reported
as completed or uncertain; an interrupt never silently rolls it back.

Finder metadata in the private recovery root counts against the quota but does
not block checkpoints. Explicit discard may remove hash-verified orphan blobs
inside that session. Unknown files, changed blobs and corrupt checkpoints remain
for inspection; permissions are never normalized automatically. Source hints are
non-executable display text and are bounded and sanitized independently of draft
fields.
