# Changelog

## 1.2.0

- New "LAN access only" setting (on by default) with a configurable,
  comma-separated list of allowed subnets. Other clients get 403.
- Fix: the bundled HTTP server now answers on the advertised `/m3u/...`
  paths (`/m3u/channels.m3u`, `/m3u/epg.xml.gz`, `/m3u/picon/...`).
  Previously these returned 404 because files were served from `/`.
- The plugin version is shown in the setup screen title.
- Package metadata: added Homepage, Source and License fields, and a
  dependency on OpenWebif (used for channel and EPG lookups).
- Maintainer scripts skip on-box steps during offline (image build)
  installs; uninstall now removes leftover compiled bytecode.
- GitHub Actions builds the IPK on every push/PR and publishes tagged
  releases.
- OpenEmbedded recipe in `contrib/openembedded/` for feed and image builders.

## 1.1.0

- Initial public release.
