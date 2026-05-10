# -*- coding: utf-8 -*-
"""
Bouquet -> M3U + XMLTV generator for Enigma 2 / OpenWebif.

Reads channels via OpenWebif's /api/getservices and full per-channel
EPG via /api/epgservice, writes channels.m3u and epg.xml(.gz) to the
output directory.
"""

import os
import json
import gzip
import html
import socket
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_lan_ip():
    """Best-effort detection of the box's primary IPv4 address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("1.1.1.1", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _http_get(url, timeout=15):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _bouquet_bref(bouquet_filename):
    name = os.path.basename(bouquet_filename)
    return ('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % name)


def _is_marker(sref):
    parts = sref.split(":")
    return len(parts) > 1 and parts[1] in ("64", "320", "832", "512")


def _is_real_name(name):
    if not name:
        return False
    if name == "<n/a>":
        return False
    if name.startswith("1:0:"):
        return False
    return True


def _tvg_id(sref):
    return sref.replace(":", "_").rstrip("_")


def _fmt_xmltv(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y%m%d%H%M%S +0000")


def _xml_escape(s):
    return html.escape(s or "", quote=False)


# ---------------------------------------------------------------------------
# Channel enumeration
# ---------------------------------------------------------------------------

def list_channels(bouquet_filename, owif_host="localhost", owif_port=80):
    """Return list of (sref, name) for playable services in the bouquet."""
    bref = urllib.parse.quote(_bouquet_bref(bouquet_filename), safe="")
    url = "http://%s:%d/api/getservices?sRef=%s" % (owif_host, owif_port, bref)
    data = json.loads(_http_get(url))
    out = []
    for s in data.get("services", []):
        sref = s.get("servicereference", "")
        name = (s.get("servicename") or "").strip()
        if _is_marker(sref):
            continue
        if not _is_real_name(name):
            continue
        out.append((sref, name))
    return out


# ---------------------------------------------------------------------------
# M3U
# ---------------------------------------------------------------------------

def write_m3u(channels, output_path, box_host, stream_port=8001,
              serve_port=8888, picon_dir="/usr/share/enigma2/picon",
              epg_url=None):
    """Write the M3U playlist atomically. Returns number of entries."""
    lines = []
    if epg_url:
        lines.append('#EXTM3U url-tvg="%s"' % epg_url)
    else:
        lines.append("#EXTM3U")

    for sref, name in channels:
        tvg = _tvg_id(sref)
        logo = ""
        if picon_dir:
            for case_id in (tvg.upper(), tvg.lower()):
                if os.path.isfile(os.path.join(picon_dir, case_id + ".png")):
                    logo = "http://%s:%d/m3u/picon/%s.png" % (
                        box_host, serve_port, case_id)
                    break
        safe_name = name.replace('"', "'")
        attrs = 'tvg-id="%s" tvg-name="%s"' % (tvg, safe_name)
        if logo:
            attrs += ' tvg-logo="%s"' % logo
        lines.append("#EXTINF:-1 %s,%s" % (attrs, name))
        lines.append("http://%s:%d/%s" % (box_host, stream_port, sref))

    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, output_path)
    os.chmod(output_path, 0o644)
    return len(channels)


# ---------------------------------------------------------------------------
# EPG (XMLTV)
# ---------------------------------------------------------------------------

def write_epg(channels, output_path, owif_host="localhost", owif_port=80,
              keep_gz=True, progress_cb=None):
    """Fetch per-channel EPG and write XMLTV. Returns (channel_count, event_count)."""
    tmp = output_path + ".tmp"
    total_events = 0

    with open(tmp, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        f.write('<tv generator-info-name="enigma2-bouquettom3u">\n')

        # Channel section
        for sref, name in channels:
            cid = _tvg_id(sref)
            f.write('  <channel id="%s">\n' % _xml_escape(cid))
            f.write('    <display-name>%s</display-name>\n' % _xml_escape(name))
            f.write('  </channel>\n')

        # Programme section
        for idx, (sref, name) in enumerate(channels):
            if progress_cb:
                progress_cb(idx + 1, len(channels), name)
            try:
                enc = urllib.parse.quote(sref, safe="")
                url = "http://%s:%d/api/epgservice?sRef=%s" % (
                    owif_host, owif_port, enc)
                data = json.loads(_http_get(url))
            except Exception:
                continue
            cid = _tvg_id(sref)
            for e in data.get("events", []):
                begin = e.get("begin_timestamp")
                duration = e.get("duration_sec", 0)
                if not begin:
                    continue
                end = int(begin) + int(duration)
                title = e.get("title", "")
                short = e.get("shortdesc", "")
                long_ = e.get("longdesc", "")
                desc = long_ or short
                f.write('  <programme start="%s" stop="%s" channel="%s">\n' % (
                    _fmt_xmltv(begin), _fmt_xmltv(end), _xml_escape(cid)))
                f.write('    <title>%s</title>\n' % _xml_escape(title))
                if short and long_ and short != long_:
                    f.write('    <sub-title>%s</sub-title>\n' % _xml_escape(short))
                if desc:
                    f.write('    <desc>%s</desc>\n' % _xml_escape(desc))
                f.write('  </programme>\n')
                total_events += 1

        f.write('</tv>\n')

    os.replace(tmp, output_path)
    os.chmod(output_path, 0o644)

    if keep_gz:
        gz_path = output_path + ".gz"
        tmp_gz = gz_path + ".tmp"
        with open(output_path, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=9) as dst:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        os.replace(tmp_gz, gz_path)
        os.chmod(gz_path, 0o644)

    return len(channels), total_events


# ---------------------------------------------------------------------------
# Convenience: full refresh
# ---------------------------------------------------------------------------

def refresh_all(bouquet_filename, output_dir, box_host=None,
                stream_port=8001, serve_port=8888,
                owif_host="localhost", owif_port=80,
                picon_dir="/usr/share/enigma2/picon",
                make_picon_symlink=True,
                progress_cb=None):
    """Generate both M3U and EPG. Returns a dict with counts."""
    if box_host is None:
        box_host = _get_lan_ip()

    os.makedirs(output_dir, exist_ok=True)

    # Picon symlink (so the served HTTP root can also serve picons)
    if make_picon_symlink and picon_dir and os.path.isdir(picon_dir):
        link_path = os.path.join(output_dir, "picon")
        if not os.path.exists(link_path):
            try:
                os.symlink(picon_dir, link_path)
            except OSError:
                pass

    channels = list_channels(bouquet_filename, owif_host, owif_port)

    epg_url = "http://%s:%d/m3u/epg.xml.gz" % (box_host, serve_port)
    m3u_count = write_m3u(
        channels, os.path.join(output_dir, "channels.m3u"),
        box_host=box_host, stream_port=stream_port, serve_port=serve_port,
        picon_dir=picon_dir, epg_url=epg_url)

    chan_count, event_count = write_epg(
        channels, os.path.join(output_dir, "epg.xml"),
        owif_host=owif_host, owif_port=owif_port,
        progress_cb=progress_cb)

    return {
        "channels": chan_count,
        "events": event_count,
        "m3u_url": "http://%s:%d/m3u/channels.m3u" % (box_host, serve_port),
        "epg_url": "http://%s:%d/m3u/epg.xml.gz" % (box_host, serve_port),
    }
