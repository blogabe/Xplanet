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

At 2026-10-19 15:05 UTC, a storm-only run fetched the then-current official
sources and published into a temporary root under `dev/tests/.tmp`: four
markers (Trudy, Wati, Invest 93S, Champi), 11 marker-file lines and 107
arc-file lines with observed and forecast segments. It did not write the
working `markers/storm` or `arcs/storm` paths.

`live-20261020/` holds raw public JTWC RSS, its linked numbered warning and
formation alert, and both significant advisories. `manifest.json` records
their URLs, retrieval times, byte counts and SHA-256 hashes. The RSS labels
`sh9327web.txt` as `TCFA Text`; its bulletin is an alert for Invest 93S,
not a numbered warning. ABIO supplies the same current position. The ABPW
issue interval occurs on the `SUBJ` line. On 2026-10-20, a separate storm-only
live validation produced three storm records and isolated marker/arc text under
ignored `dev/reference/`; it did not update runtime markers or arcs.

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
