Official public source excerpts captured 2026-10-19 UTC for offline parsing tests.
NHC: CurrentStorms.json, ATCF bep212026.dat, latest OFCL cycle from aep212026.dat.gz.
JTWC: jtwc.rss, wp2926web.txt, sh0127web.txt, and doc.kml only from each official KMZ.
Selected forecast rows and KMZ doc.kml preserve source records; KMZ package assets were removed. Text line endings and trailing spaces were normalized.

Additional official JTWC 2026-10-19 ABIO/ABPW advisory text is included for invest observations. The 2023 bio01/bio08 BEST decks are extracted from products/best-tracks/2023/2023s-bio/bio2023.zip; they verify historical North Indian ATCF coordinates only, not a live warning or forecast. Text line endings/trailing spaces were normalized.

`jtwc-abio-20261019-1230.txt` is the unmodified, CRLF official
`https://www.metoc.navy.mil/jtwc/products/abioweb.txt` response retrieved
2026-10-19 15:01 UTC (1952 bytes; SHA-256
`5166677217dc05b43ccadf83658b172bca4d215ee5693823bafae75f3bed10d6`).
The 191230Z reissue says Invest 96A was *previously* at 4.0N 57.0E, then
"HAS DISSIPATED AND IS NO LONGER SUSPECT". It gives no current position for
96A. The same bulletin still gives Invest 93S a current position at 3.2N
57.1E. This is the live-source regression case, and the old coordinate must
not become a marker or arc point.

`live-20261020/` holds raw public JTWC RSS, its linked numbered warning and
formation alert, and both significant advisories. `manifest.json` records
their URLs, retrieval times, byte counts and SHA-256 hashes. The RSS labels
`sh9327web.txt` as `TCFA Text`; its bulletin is an alert for Invest 93S,
not a numbered warning. ABIO supplies the same current position. The ABPW
issue interval occurs on the `SUBJ` line.

`live-20261020-promotion/` captures raw official JTWC ABIO, ABPW, RSS,
linked WP29/SH02 warning text and KMZ, plus the contemporaneous empty NHC
index on 2026-10-20 at 16:01–16:04 UTC. Its manifest gives each URL,
retrieval time, HTTP metadata, byte count and SHA-256. ABIO's 08:30 UTC
reissue explicitly promotes Invest 93S to the warning listed at paragraph
2.A.(1), Tropical Cyclone 02S. It gives only the invest's previous position.
The prior parser rejected this valid transition as lacking a current invest
position; 02S's warning supplies the current point and forecast. The rejected
overnight HTTP body was not saved, so this captured current bulletin reproduces
the same reported error but cannot establish byte identity with that poll.

`live-20261021-indian-wrap/` holds the raw official ABIO bulletin captured
2026-10-21 at 20:33 UTC. Its subject breaks between `INDIAN` and `OCEAN`,
followed by a valid dated interval; its manifest records the exact response
hash and retrieval metadata. The earlier rejected production response was not
saved, so this fixture establishes the current format failure, not byte
identity with the first failed poll.

`live-20261020-interval-wrap/` holds the raw ABIO response retrieved
2026-10-20 at 19:39 UTC. Its issue interval wraps after the hyphen; the
manifest preserves the retrieval metadata and byte hash.

`jtwc-abpw-20261026-2230.txt` and `jtwc-rss-20261027-reissue.xml` exercise
ABPW's distinct reissue header and validity start, plus the matching RSS
reissue link. Their byte hashes are pinned in `test_storm_sources.py`.
Their exact indexed fixture bytes are pinned in the shared
[fixture provenance receipt](../provenance.json). Original retrieval times, request
URL, HTTP metadata and transformation history are not independently established;
the historical provider attribution is not a newly authenticated response capture.

The residual-TCFA promotion regression deliberately combines the older
captured alert with an injected link in the later promotion RSS. This is
synthetic source sequencing, not evidence that JTWC published that sequence.

`live-20261106-final-warning/` contains independently downloaded, unmodified
public NHC/JTWC responses with per-response URL, HTTP date and SHA-256 receipts.
ABPW retains an explicitly cross-referenced final warning for 30W after RSS
retires that warning. The snapshot still includes the active 99W and 94S
invests. Final-warning recognition must not excuse a missing active warning,
ambiguous reference, expired source interval or failed publication.

`live-20261113-no-warnings/` preserves unmodified public NHC/JTWC responses
captured November 13 at 04:08 UTC with URL, response Date, retrieval timestamp,
byte count and SHA-256 in `sources.json`. JTWC combines all regions into one
explicit no-active-warning item instead of separate north/south categories.
Both significant advisories remain required: this real packet contains invests
92B and 95P, so it is not a globally empty storm dataset. The separate rejected
RSS is byte-identical to the response saved by TotalMarker at the November 13
03:10 UTC failed refresh (its capture timestamp and hash are in the receipt).
The globally empty advisory test is synthetic, not a natural empty-feed claim.

`live-20261114-corrected/` captures the November 14 16:48 UTC public packet,
with URLs, HTTP dates and hashes in `sources.json`. ABPW uses `CORRECTED`,
a `COR` header suffix and a correction-justification footer. Its TCFA for 95P
is still an invest, not a numbered warning or forecast track. Tests cover
strict date/section validation and first-run creation of both output files.
