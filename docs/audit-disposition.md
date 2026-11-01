# Audit disposition

Read-only audit dated 2026-11-01, source `340790b`; remediation is isolated on
`audit/reliability-20261101`. IDs refer to the original independent audit. Grouped
rows distinguish behavior fixes, tests, documentation, intentional contracts and
remaining decisions; they do not claim every finding is a defect or closed.
No authentic provider evidence, redistribution rights or live macOS validation is
inferred from offline tests. Original audit remains unchanged.

| Audit IDs | Disposition | Result or remaining reason |
| --- | --- | --- |
| XP-001, XP-002, XP-016, XP-018 | Addressed; source rule retained | Distinct storm conditions/identity/times; residual-TCFA regression and bounded latest rejection evidence. No guessed supersession exception. |
| XP-003, XP-075, XP-085, XP-144, XP-150 | Documented | Mutable-main trust and detached tag update limitation; no new release/pinning policy. |
| XP-004, XP-005, XP-006, XP-028, XP-041, XP-102 | Deferred by user | Asset payload/intermediates and per-source rights need provenance and distribution/license decisions. No assets or history removed; no license inferred. |
| XP-007, XP-008, XP-009, XP-024, XP-032 | Fixed/documented | Exporter supports committed assets, checks HEAD blob IDs/modes before candidate history; real-tree, hidden-dirty and ignored-asset regressions. Deliberate asset add policy retained. |
| XP-010, XP-011, XP-035 | Fixed/tested | Cloud verified-fetch time and failed source invalidation separated; failed cache cannot claim success; label-only preserves provider failure facts. |
| XP-012, XP-030 | Mitigated/documented | Shipped example intervals leave launchd jitter margin; existing personal values and strict interval rules unchanged. |
| XP-013, XP-055, XP-062, XP-064, XP-124, XP-132 | Retained | Explicit config/validation and legacy accepted syntax preserved. Broad schema/type normalization has no demonstrated benefit warranting compatibility risk. |
| XP-014, XP-034, XP-073, XP-133 | Agreed conservative recovery | Actionable pending/multiple-journal errors and read-only health detection; intent preserved. Cross-product isolation needs shared-state replay design; never skip/discard journals. |
| XP-015 | Addressed | CI full macOS suite plus explicit portable data/publication subset. No broad skip batch applied; hosted checks await publication. |
| XP-017, XP-019, XP-020, XP-021, XP-022, XP-039, XP-042, XP-091, XP-092, XP-096, XP-098, XP-099, XP-106, XP-108, XP-116, XP-117, XP-153, XP-160 | Boundary tests added; live evidence required | Keep strict source/date/forecast/season/type rules and renderer assumptions. Missing authentic empty/current/final/renewal/boundary captures or renderer validation not fabricated. Fixture limits clarified; temporal error messages improved. |
| XP-023, XP-026, XP-151 | Deferred | Mixed fixture attribute strategy and GVP byte-exact policy remain; structural fixture valid, current autocrlf differs from audit. No blanket capture-byte conversion. |
| XP-025 | Not current | No Git mode diff on canonical recheck; 533 files had filesystem 0655 versus tracked100644, with owner execute bit unchanged. Cause unproven; permissions/settings left untouched. |
| XP-027, XP-101, XP-103, XP-149 | Fixed | README health verbose option and volcano access wording aligned. |
| XP-029 | Retained | Quoted filenames with spaces have no demonstrated breakage. |
| XP-031 | Deferred cosmetic | Small config fixtures remain explicit; no need to generate them from product examples. |
| XP-033 | Deferred | No metadata leak found; first-64KiB scan is not complete metadata coverage. Binary provenance review needed. |
| XP-036 | Evidence required | Two absent private NORAD capture tests remain explicitly skipped; no fabricated public capture. |
| XP-037, XP-044, XP-045 | Fixed/tested | 17-selection retention, catalog-verified sanitized fallback names, configured cooldown wording/failure facts. Existing named-member mismatch rejection retained. |
| XP-038 | Partly tested | Added unmatched304 and unsafe-stored-validator no-fetch/last-good regressions. Renderer escaping remains a separate unverified contract. |
| XP-040, XP-047, XP-048, XP-049 | Fixed/tested | Parser-level encoded DTD rejection, bounded iterative HTML structure, malformed citation normalization and control sanitization; last-good preserved. |
| XP-043 | Deferred product contract | Optional eclipse scheduling and disable-time file ownership need a policy; no implicit output clearing. |
| XP-046 | Evidence required | Renderer quote/backslash semantics need finite render/upstream-parser validation before changing escaping. |
| XP-050, XP-061, XP-063 | Fixed/documented | NORAD string syntax clarified; native type errors name safe keys; DEL rejected in URLs. No broad international URL policy change. |
| XP-051, XP-052, XP-054 | Tested | CLI misuse before config, real loopback urllib302/304, and resolve/open symlink race regressions. |
| XP-053, XP-066, XP-067, XP-105 | Fixed/tested; compatibility noted | Per-product output/probe errors continue report including disabled outputs; saved enabled failure exit1, local storage/recovery exit2. Additive JSON statuses/error fields documented. |
| XP-056, XP-059, XP-060, XP-122 | Deferred compatibility | Legacy DEFAULT/empty/unknown-key policy needs explicit choice; current parsing/deferred behavior preserved. Native key diagnostic improved separately. |
| XP-057, XP-065, XP-094, XP-118, XP-120, XP-121, XP-131 | Deferred cosmetic | Stale package prose, harmless unused imports/version duplication/lint do not justify unrelated churn. |
| XP-058, XP-070 | Deferred diagnostic categories | No unsafe traceback logging; current fixed transport errors remain sanitized. |
| XP-069 | Fixed/tested | Shared 60–300s monotonic network refresh budget; supervised network-only child bounds DNS/headers/trickle and is reaped on timeout. |
| XP-068 | Deferred | Live stale classification still message-based; structured reason API is a separate additive change. |
| XP-071, XP-129 | Retained pending ownership choice | Disabled/duplicate user-owned label rows preserved; automatic removal/re-aging would change ownership semantics. |
| XP-072, XP-137 | Manual option added; no automatic rotation | Explicit 30-day event JSONL trim with dry-run/age/counts and shared-writer lock. Ambiguous records and uncoordinated launchd text logs preserved. |
| XP-074, XP-076, XP-088 | Fixed/tested | Strict Git ref validation before helper download; negative test asserts no download. |
| XP-077, XP-078, XP-079 | Fixed/tested | Controlled host interpreter fixture and precise reinstall/plist failure assertions; no generic early-failure false pass. |
| XP-080, XP-081, XP-082, XP-086, XP-087, XP-135 | Guest verified, scoped | Idempotent verified desktop, explicit narrow restart, monthly catch-up, correct-job setup rerun and consented retry coverage. Broad stop unchanged; identity ambiguity refuses. |
| XP-139 | Guest verified | Real fork/executable/argv/birth identity, repeated start and narrow restart passed on macOS27 ARM64. |
| XP-146 | Login evidence pending | Explicit loading and repeat setup verified; no logout/reboot test of automatic symlinked LaunchAgent discovery. |
| XP-083 | Mitigated/tested | Normal-signal lock cleanup and actionable manual recovery; no unsafe stale-lock stealing after crash/SIGKILL. |
| XP-084 | Fixed/tested | Fetch actual configured tracking ref including custom mappings; recheck upstream mapping/HEAD/branch; no force update. |
| XP-089 | Deferred convenience | Symlink entrypoint aliases not part of cwd-independent CLI promise; no root-discovery redesign. |
| XP-090 | Fixed/tested | Preview temp/cache isolated like render, outside persistent product state. |
| XP-093 | Tested | Exact24h/+1s NHC forecast threshold and multi-cycle selection regressions. |
| XP-095 | Fixed | Parser-version rationale corrected. |
| XP-097 | Fixed/tested | Narrow gzip/zlib/ZIP/URL errors become operational FeedError and retain diagnostic facts. |
| XP-100 | Deferred environment choice | Sync-folder risks remain hypothetical; source relocation and settings excluded. |
| XP-104, XP-145 | Retained intentional | Personal shell configuration executes code by design; no pseudo-sandbox added. |
| XP-107 | Retained intentional | Corrupt stored validator remains storage error; no writing failure facts into suspect state. |
| XP-109, XP-114, XP-154, XP-157, XP-159, XP-162 | Retained intentional | Documented bounded selection, strict event validation, cache-check success and source/model conventions preserved. |
| XP-110, XP-113, XP-156 | Deferred refactor | Small helper/publisher duplication accepted; preserve product-specific policies and journal compatibility. |
| XP-111, XP-112 | Deferred product scope | Santa remains inert; no help/runtime redesign or diagnostic migration. |
| XP-115 | Retained compatibility | Legacy quality-token semantics unchanged. |
| XP-119 | No defect | Immediate loop-lambda consumption is not a late-binding failure. |
| XP-123 | Deferred defense in depth | Raw parsed unrelated values retained for compatibility; no current serialization leak found. |
| XP-125 | Retained isolation | Live NORAD probe does not persist cooldown; no normal-state mutation introduced. |
| XP-126 | Deferred wording | Future cloud time terminology differs; label remains UNKNOWN and no freshness fabricated. |
| XP-127, XP-128 | Retained transport policy | Environment proxies disabled; validators may cross origin while credentials remain scoped. No leak shown; changes need explicit policy. |
| XP-130 | No escape demonstrated | Lexical symlink semantics remain confined by descriptor/no-follow checks. |
| XP-134, XP-136, XP-138, XP-148 | Retained intentional | Routing, template readability, user-wide stop and internal setup seam preserved. |
| XP-140, XP-142, XP-143 | Integration evidence required | Fresh Homebrew source build/trust/receipts and formula dependency coverage not established by stubs; no UTM/installer run in this batch. |
| XP-141 | Deferred consistency | PATH-vs-absolute plutil difference not privilege escalation; no unrelated tool-selection change. |
| XP-147 | Documented | Distinguish scheduled-job unload from stopping display; preserve personal plists. |
| XP-152 | No defect | Normalized fixture excerpts disclosed honestly; no raw-byte provenance invented. |
| XP-155 | Documented limitation | Pair journal is recoverable, not simultaneous visibility; interruption can persist mixed generation until replay. |
| XP-158, XP-161 | Retained meaningful validation | Required-group model checks and final completeness attestation are useful; cosmetic dead guards not broadened into redesign. |

Health compatibility: an enabled saved failed refresh now returns 1; local storage,
pending-recovery and probe errors return 2. JSON may add `refresh_failed`,
`output.error` and `recovery_error`. Existing keys/configuration and journal formats
remain compatible. Label-only aging does not supersede provider failure facts.

Validation commands and counts are recorded with the branch delivery. The normal
macOS suite remains complete; Linux CI uses the explicit portable subset rather
than broad skips. Two unavailable private NORAD captures remain known skips.

Verified locally after remediation on macOS with Python 3.15.2:

- `TZ=UTC ./scripts/xplanet.sh test`: 552 tests, zero failures, two known private-fixture skips.
- `TZ=Pacific/Honolulu PYTHONPATH=scripts:dev python -m tests.run_portable`: 412 tests, zero failures, the same two skips.
- Non-UTC monthly-map, lifecycle/render, health-format, diagnostics and shared-label tests: 48 passed.
- Python 3.11 syntax parsing, zsh syntax and `git diff --check`: passed.
- Independent runtime, shell/capture and distribution reviews: findings corrected and re-reviewed.

Python 3.11/3.13 runtime jobs are configured but have not run on hosted CI; those
interpreters were unavailable locally. No UTM, fresh install/source build, host
service or installed deployment checks were performed in this batch.

Agreed continuation preserves every asset/provenance file and conservative journal
recovery. Lifecycle, finite network budgets and explicit manual event-log trimming
are authorized; no existing user logs, installed renderer or services were touched.
Strict Jan/July season, forecastless-final/null-forecast and isolated-capture tests
clarify current contracts without inventing authentic provider evidence.

Native UTM validation (macOS 27.0.1 / ARM64, Python 3.15.2, existing Xplanet
1.3.1_99): real native identity, idempotent start, renamed invocation, narrow
restart preserving another checkout and a finite render, and October-to-November
map catch-up passed. An isolated namespace changed only fixture labels/filenames;
actual launchd registered six jobs after an initial invalid-source failure,
repeat setup performed no loads and preserved config, and an interval job retried.

The guest exposed omitted cwd/environment fields in `launchctl list`. Fix
`2f87728` requires exact absolute program identity, reports missing settings as
unknown, and leaves jobs untouched; reported mismatches still fail. Independent
review and 73 targeted tests passed. Guest full UTC suite: 557 run, zero failures,
two known private-fixture skips; 85 non-UTC checks passed. Manual trim was exercised
only on disposable dated fixtures; dry-run preserved bytes/mtime and created no lock.

No reset, snapshot change, user-log trim, fresh Homebrew build or publication.
Test renderers/jobs were stopped/unloaded; original five guest jobs and old checkout
were preserved. Test-only launchctl enable-override entries and isolated test roots
remain for inspection. Real login/reboot, future provider availability and hosted
Python 3.11/3.13 checks remain unverified.

## Follow-on lifecycle simplification

The original native audit validation above describes the merged audit branch,
not the replacement lifecycle. The user has explicitly chosen broad stop/restart:
all current-user Xplanet instances, including finite renders and other checkouts.
XP-080/081/082/086/087/135/138/139 now use a launchd-owned foreground renderer and
zsh lifecycle. Exact executable/argv/birth adoption and narrow restart are removed.
The old login trigger remains separate; explicit restart migrates unmanaged -fork
processes. Setup uses on-disk plutil validation and registered-label presence only;
loaded settings are not reverified. No Python registration-display parser remains.
Validation of this follow-on is recorded separately; old ABI tests are removed
with their implementation rather than retained as misleading coverage.

Follow-on validation (`15b935b`): host and disposable macOS guest each ran 528 tests,
zero failures, two existing unavailable-capture skips, plus 77 passing non-UTC
checks. Removed 34 tests of the deleted identity/parser implementation and added
five behavior regressions; no new skips. Native checks covered repeated start with
Python unavailable, foreground job ownership, monthly catch-up, broad restart of
another checkout and finite render, stopped-stays-stopped, explicit unmanaged
migration, configured executable symlink, setup rerun and the old-shaped login
trigger without recursion. Only test labels were namespaced; original jobs and
snapshots were preserved. Test processes/jobs were removed afterwards.

An initial native harness counted only the normal process name and missed a long
symlink alias; execution now resolves configured symlinks before exec and the final
run passed. No arbitrary executable/argv discovery was reintroduced. macOS's
19-character process-name lookup limit for unmanaged physically renamed binaries
is documented. Start acknowledges launchd acceptance; renderer errors remain in
its error log. No fresh Homebrew build, actual login/reboot, hosted CI for this
unpublished branch, or future provider validation is claimed.
