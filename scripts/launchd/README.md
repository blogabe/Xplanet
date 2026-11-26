# Xplanet LaunchAgents

The `.plist.example` files are optional login and scheduled jobs. See
[management](../../docs/management.md) for setup.

`local.xplanet.desktop.plist.template` defines the renderer job that
`xplanet.sh` manages. Do not install or link the template yourself. The
launcher fills in the checkout paths and creates a regular file in
`~/Library/LaunchAgents`. The optional `local.xplanet.start` job calls
`xplanet.sh start` at login; it does not run the renderer itself.
