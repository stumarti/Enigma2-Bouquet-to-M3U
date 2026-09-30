# Bouquet to M3U

An Enigma 2 plugin that exports a bouquet as an **M3U playlist** plus an **XMLTV EPG**, served over HTTP on the LAN. Point any IPTV player — TiviMate, IPTV Smarters, OTT Navigator, Jellyfin Live TV, Kodi PVR IPTV Simple Client — at one URL and you get your live channels with a full programme guide.

Tested on Zgemma H7 running PurE2; should work on any modern Enigma 2 image (OpenPLi, OpenATV, OpenViX, OpenSPA, etc.) with OpenWebif and Python 3.

**Requirements:** a Python 3 based image with OpenWebif installed (`enigma2-plugin-extensions-openwebif`). The plugin reads channel lists and EPG from OpenWebif's API, and opkg pulls it in automatically if it's missing.

## Features

- One M3U URL on your LAN that any IPTV app can read.
- Full per-channel XMLTV EPG (the same data your box's own EPG shows), gzipped.
- Picons (channel logos) served from the same URL.
- Auto-discovers your LAN IP, so the URLs work from any device on your network.
- M3U embeds the EPG URL via the `url-tvg` header — most players auto-load the guide.
- Bundled background HTTP server, tied to enigma2's lifecycle. No external services to configure.
- Scheduled refresh (15 min to once a day, or manual only).
- Drops `placeholder` and `Unknown` channels and skips bouquet markers automatically.

## Install

Every tagged release on the [Releases page](https://github.com/stumarti/Enigma2-Bouquet-to-M3U/releases) has a ready-built IPK, compiled by GitHub Actions. It's a pure-Python package (`Architecture: all`), so the same file works on every receiver.

### Option 1: install straight from GitHub on the box

SSH (or telnet) into your receiver and run:

```sh
cd /tmp
wget -O bouquettom3u.ipk https://github.com/stumarti/Enigma2-Bouquet-to-M3U/releases/latest/download/enigma2-plugin-extensions-bouquettom3u.ipk
opkg install bouquettom3u.ipk
init 4 && sleep 3 && init 3   # restart enigma2 so the autostart hook fires
```

That URL always points at the newest release. If your image's `wget` can't do HTTPS (you'll see an SSL error), use `curl -L -o bouquettom3u.ipk <url>` if you have curl, or use option 2.

### Option 2: copy it over from your PC

1. Download `enigma2-plugin-extensions-bouquettom3u_<version>_all.ipk` from the [latest release](https://github.com/stumarti/Enigma2-Bouquet-to-M3U/releases/latest).
2. Copy it to the box and install it:

   ```sh
   scp enigma2-plugin-extensions-bouquettom3u_*_all.ipk root@<box-ip>:/tmp/
   ssh root@<box-ip>
   opkg install /tmp/enigma2-plugin-extensions-bouquettom3u_*_all.ipk
   init 4 && sleep 3 && init 3
   ```

   No `scp`? Use FileZilla / WinSCP to drop the file in `/tmp`, then run the `opkg install` line from a telnet/SSH session. Some images can also install it from **Menu → Setup → Software management → Install local extension** after you put the file in `/tmp`.

### Upgrading

Install the newer IPK the same way. `opkg install` replaces the old version and keeps your settings. Restart enigma2 afterwards. The installed version appears in the plugin's title bar, or you can check it with:

```sh
opkg list-installed | grep bouquettom3u
```

### After installing

When enigma2 is back up, you'll find the plugin under:

- **Menu → Plugins → Bouquet to M3U**
- **Extensions menu** (blue button on most images)

## Configuration

Open the plugin and you'll see four options:

| Setting | Default | Description |
|---|---|---|
| Bouquet | `userbouquet.favourites.tv` | The bouquet to export. The dropdown shows every TV bouquet on the box by its display name. |
| Refresh interval | Every hour | How often to regenerate the M3U/EPG. Choose between 15 min and once a day, or "Manual only". |
| HTTP server port | 8888 | Port the bundled web server binds to. Must be ≥1024 and not already in use. |
| Picon directory | `/usr/share/enigma2/picon` | Where your channel logos live. Change this if you store picons on a USB stick or HDD. |

Buttons:

- **Green** — Save (port changes restart the server live, no enigma2 restart needed).
- **Yellow** — Refresh now (shows a progress screen while it runs).
- **Blue** — Show URLs (handy when setting up an IPTV app — read them off your TV instead of having to SSH in).
- **Red** — Cancel.

## URLs

After installation and one successful refresh, the following URLs are available on your LAN:

- **M3U playlist** → `http://<box-ip>:8888/m3u/channels.m3u`
- **EPG (gzipped XMLTV)** → `http://<box-ip>:8888/m3u/epg.xml.gz`
- **EPG (uncompressed)** → `http://<box-ip>:8888/m3u/epg.xml`
- **Picons** → `http://<box-ip>:8888/m3u/picon/<service_id>.png`

The M3U references the EPG URL in its header, so most IPTV players load the EPG automatically when you add just the M3U URL.

## Notes

### EPG depth

The EPG output is only as good as the EPG cached in your box. If you only see "now and next" data, your box isn't downloading the full week's EPG in the background. Fix that first with one of:

- **CrossEPG** plugin (recommended — fastest, pulls a week in one short tune)
- **EPGRefresh** plugin (tunes every channel briefly to collect EPG)
- Whatever EPG plugin ships with your image

Once your box has a full week's EPG cached, run "Refresh now" from this plugin and the XMLTV output will jump from ~1,200 events to tens of thousands.

### Streams

Generated stream URLs target port 8001 (raw TS, no transcoding). Most IPTV players play these directly. If you have a transcoding-capable box and want lower-bitrate streams, change `STREAM_PORT` in `src/BouquetToM3U/plugin.py` to `8002` and rebuild.

### LAN only

The bundled HTTP server has **no authentication**. It's intended for LAN use behind your home router. Don't port-forward it to the internet without putting something in front of it (reverse proxy with auth, VPN, etc.).

## Building from source

You need a Linux/macOS environment with `make`, `tar`, `ar`, and `python3`:

```sh
git clone https://github.com/stumarti/Enigma2-Bouquet-to-M3U.git
cd Enigma2-Bouquet-to-M3U
make ipk                     # version taken from CONTROL/control
make ipk VERSION=1.2.0-test  # or override it
```

The IPK will be in `dist/`. The version is written into the package metadata and into the plugin (`__version__`, shown in its title bar).

## Continuous integration and releases

`.github/workflows/build.yml` builds the IPK on every push to `main`, every pull request and every `v*` tag:

- **Pushes and PRs** produce a development build versioned `<control version>+git<run>.<sha>`, e.g. `1.1.0+git12.abc1234`. Download it from the run's **Artifacts** section on the Actions tab.
- **Tags** (`v1.2.0`) build using the tag's version and publish a GitHub Release with generated notes. The release carries two copies of the IPK: the versioned file and `enigma2-plugin-extensions-bouquettom3u.ipk`, a copy with a fixed name that the `releases/latest/download` link above uses.

To cut a release:

1. Bump `Version:` in `CONTROL/control` (e.g. `1.2.0`) and commit it.
2. Tag and push:

   ```sh
   git tag v1.2.0
   git push origin main v1.2.0
   ```

The workflow warns if the tag and `CONTROL/control` disagree. The tag version wins.

## For feed and image maintainers

Bouquet to M3U is ready to package in an image or plugin feed:

- **Prebuilt IPK:** every GitHub release has an `Architecture: all` IPK with full metadata (Homepage, Source, License, Depends). You can add it to a feed as it is.
- **Build from source:** [`contrib/openembedded/enigma2-plugin-extensions-bouquettom3u.bb`](contrib/openembedded/enigma2-plugin-extensions-bouquettom3u.bb) is a BitBake recipe (`allarch`, `gitpkgv`) that installs the plugin into `${libdir}/enigma2/python/Plugins/Extensions/BouquetToM3U` and stamps the version. Drop it into your enigma2-plugins layer. Pin `SRCREV` to a release tag's commit if you prefer reproducible builds.
- **Runtime dependencies:** OpenWebif, plus the Python 3 core, json, html, compression, netclient and netserver modules.
- **Maintainer scripts:** they skip on-box steps when `$D` is set, so offline rootfs installs are safe.
- **Changelog:** see [CHANGELOG.md](CHANGELOG.md).

## Uninstall

```sh
opkg remove enigma2-plugin-extensions-bouquettom3u
init 4 && sleep 3 && init 3
```

The output directory `/var/www/m3u` is left in place so any IPTV apps referencing it don't break immediately. Remove it manually if you want a clean state:

```sh
rm -rf /var/www/m3u
```

## Project layout

```
.
├── CONTROL/              opkg package metadata
│   ├── control           name, version, deps
│   ├── postinst          post-install hook
│   ├── prerm             pre-uninstall hook
│   └── postrm            post-uninstall cleanup
├── src/BouquetToM3U/     Enigma 2 plugin sources
│   ├── __init__.py
│   ├── plugin.py         UI, lifecycle, config, scheduling
│   ├── generator.py      M3U + XMLTV generation
│   ├── httpserver.py     bundled background HTTP server
│   └── plugin.png        icon shown in Plugin Browser
├── .github/workflows/    CI build + release workflow
├── contrib/openembedded/ BitBake recipe for feeds / images
├── dist/                 locally built IPKs (not committed)
├── Makefile              `make ipk` to build
├── CHANGELOG.md          release notes
├── README.md             this file
└── LICENSE
```

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

Built for and tested on PurE2 / Zgemma H7. Uses OpenWebif's `/api/getservices` and `/api/epgservice` endpoints for service enumeration and EPG retrieval — thanks to the OpenWebif team for making them stable and well-documented.
