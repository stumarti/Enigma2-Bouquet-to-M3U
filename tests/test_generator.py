import gzip
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from unittest import mock

from BouquetToM3U import generator

SREF_A = "1:0:19:1B1D:802:2:11A0000:0:0:0:"
SREF_B = "1:0:1:189E:7E4:2:11A0000:0:0:0:"
MARKER = "1:64:1:0:0:0:0:0:0:0::Sports"


def fake_owif(services, epg):
    """Build a replacement for generator._http_get serving OpenWebif JSON.

    services: list of (sref, name) returned by /api/getservices
    epg: dict sref -> list of event dicts for /api/epgservice
    """
    calls = []

    def _http_get(url, timeout=15):
        calls.append(url)
        parsed = urllib.parse.urlparse(url)
        sref = urllib.parse.parse_qs(parsed.query)["sRef"][0]
        if parsed.path == "/api/getservices":
            return json.dumps({"services": [
                {"servicereference": s, "servicename": n}
                for s, n in services]}).encode()
        if parsed.path == "/api/epgservice":
            if sref not in epg:
                raise OSError("no EPG")
            return json.dumps({"events": epg[sref]}).encode()
        raise AssertionError("unexpected URL " + url)

    _http_get.calls = calls
    return _http_get


class HelpersTest(unittest.TestCase):

    def test_bouquet_bref_uses_basename(self):
        self.assertEqual(
            generator._bouquet_bref("/etc/enigma2/userbouquet.fav.tv"),
            '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.fav.tv" '
            'ORDER BY bouquet')

    def test_is_marker(self):
        self.assertTrue(generator._is_marker(MARKER))
        self.assertTrue(generator._is_marker("1:320:0:0:0:0:0:0:0:0:"))
        self.assertFalse(generator._is_marker(SREF_A))
        self.assertFalse(generator._is_marker(""))

    def test_is_real_name(self):
        self.assertTrue(generator._is_real_name("BBC One"))
        for bad in ("", None, "<n/a>", "1:0:19:1B1D:802:2:11A0000:0:0:0:"):
            with self.subTest(name=bad):
                self.assertFalse(generator._is_real_name(bad))

    def test_tvg_id(self):
        self.assertEqual(generator._tvg_id(SREF_A),
                         "1_0_19_1B1D_802_2_11A0000_0_0_0")

    def test_fmt_xmltv_is_utc(self):
        self.assertEqual(generator._fmt_xmltv(0), "19700101000000 +0000")
        self.assertEqual(generator._fmt_xmltv("1700000000"),
                         "20231114221320 +0000")

    def test_xml_escape(self):
        self.assertEqual(generator._xml_escape('A & B <C> "D"'),
                         'A &amp; B &lt;C&gt; "D"')
        self.assertEqual(generator._xml_escape(None), "")


class GeneratorFilesTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_list_channels_filters_markers_and_placeholders(self):
        fake = fake_owif(
            [(SREF_A, " BBC One "), (MARKER, "Sports"),
             (SREF_B, "<n/a>"), ("1:0:1:1:1:1:1:0:0:0:", "")], {})
        with mock.patch.object(generator, "_http_get", fake):
            channels = generator.list_channels(
                "/etc/enigma2/userbouquet.fav.tv", "box", 8080)
        self.assertEqual(channels, [(SREF_A, "BBC One")])
        self.assertTrue(fake.calls[0].startswith(
            "http://box:8080/api/getservices?sRef="))

    def test_write_m3u(self):
        picons = os.path.join(self.dir, "picon")
        os.mkdir(picons)
        # Lower-case picon file must still be found.
        open(os.path.join(picons, "1_0_19_1b1d_802_2_11a0000_0_0_0.png"),
             "w").close()
        out = os.path.join(self.dir, "channels.m3u")

        count = generator.write_m3u(
            [(SREF_A, 'Say "Hi"'), (SREF_B, "No Logo")], out,
            box_host="192.168.1.2", stream_port=8001, serve_port=8888,
            picon_dir=picons, epg_url="http://192.168.1.2:8888/m3u/epg.xml.gz")

        self.assertEqual(count, 2)
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(
            lines[0], '#EXTM3U url-tvg="http://192.168.1.2:8888/m3u/epg.xml.gz"')
        self.assertEqual(
            lines[1],
            '#EXTINF:-1 tvg-id="1_0_19_1B1D_802_2_11A0000_0_0_0" '
            'tvg-name="Say \'Hi\'" tvg-logo="http://192.168.1.2:8888/m3u/'
            'picon/1_0_19_1b1d_802_2_11a0000_0_0_0.png",Say "Hi"')
        self.assertEqual(lines[2], "http://192.168.1.2:8001/" + SREF_A)
        self.assertNotIn("tvg-logo", lines[3])
        self.assertEqual(len(lines), 5)
        self.assertFalse(os.path.exists(out + ".tmp"))

    def test_write_m3u_without_epg_url(self):
        out = os.path.join(self.dir, "channels.m3u")
        generator.write_m3u([], out, box_host="h", picon_dir=None)
        with open(out) as f:
            self.assertEqual(f.read(), "#EXTM3U\n")

    def test_write_epg(self):
        epg = {
            SREF_A: [
                {"begin_timestamp": 1700000000, "duration_sec": 1800,
                 "title": "News & Weather", "shortdesc": "Headlines",
                 "longdesc": "All the <latest> headlines"},
                {"begin_timestamp": 1700001800, "duration_sec": 600,
                 "title": "Short", "shortdesc": "Same", "longdesc": "Same"},
                {"begin_timestamp": None, "title": "Skipped"},
            ],
            # SREF_B has no EPG: the fetch fails and the channel is skipped.
        }
        out = os.path.join(self.dir, "epg.xml")
        progress = []
        with mock.patch.object(generator, "_http_get", fake_owif([], epg)):
            chans, events = generator.write_epg(
                [(SREF_A, "BBC One"), (SREF_B, "ITV")], out,
                progress_cb=lambda i, n, name: progress.append((i, n, name)))

        self.assertEqual((chans, events), (2, 2))
        self.assertEqual(progress, [(1, 2, "BBC One"), (2, 2, "ITV")])

        root = ET.parse(out).getroot()
        self.assertEqual(root.tag, "tv")
        self.assertEqual(
            [c.findtext("display-name") for c in root.findall("channel")],
            ["BBC One", "ITV"])
        progs = root.findall("programme")
        self.assertEqual(progs[0].get("start"), "20231114221320 +0000")
        self.assertEqual(progs[0].get("stop"), "20231114224320 +0000")
        self.assertEqual(progs[0].get("channel"),
                         "1_0_19_1B1D_802_2_11A0000_0_0_0")
        self.assertEqual(progs[0].findtext("title"), "News & Weather")
        self.assertEqual(progs[0].findtext("sub-title"), "Headlines")
        self.assertEqual(progs[0].findtext("desc"),
                         "All the <latest> headlines")
        # Identical short/long description: no sub-title.
        self.assertIsNone(progs[1].find("sub-title"))

        with open(out, "rb") as plain, gzip.open(out + ".gz") as gz:
            self.assertEqual(plain.read(), gz.read())

    def test_write_epg_without_gzip(self):
        out = os.path.join(self.dir, "epg.xml")
        with mock.patch.object(generator, "_http_get", fake_owif([], {})):
            generator.write_epg([], out, keep_gz=False)
        self.assertTrue(os.path.exists(out))
        self.assertFalse(os.path.exists(out + ".gz"))

    def test_refresh_all(self):
        picons = os.path.join(self.dir, "picons-src")
        os.mkdir(picons)
        output = os.path.join(self.dir, "www", "m3u")
        fake = fake_owif(
            [(SREF_A, "BBC One")],
            {SREF_A: [{"begin_timestamp": 1700000000, "duration_sec": 60,
                       "title": "T"}]})
        with mock.patch.object(generator, "_http_get", fake):
            result = generator.refresh_all(
                "/etc/enigma2/userbouquet.fav.tv", output,
                box_host="10.0.0.5", serve_port=9000, picon_dir=picons)

        self.assertEqual(result, {
            "channels": 1,
            "events": 1,
            "m3u_url": "http://10.0.0.5:9000/m3u/channels.m3u",
            "epg_url": "http://10.0.0.5:9000/m3u/epg.xml.gz",
        })
        for name in ("channels.m3u", "epg.xml", "epg.xml.gz"):
            self.assertTrue(os.path.isfile(os.path.join(output, name)), name)
        self.assertEqual(os.readlink(os.path.join(output, "picon")), picons)


if __name__ == "__main__":
    unittest.main()
