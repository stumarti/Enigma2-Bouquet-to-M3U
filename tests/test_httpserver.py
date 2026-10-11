import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

from BouquetToM3U import httpserver
from BouquetToM3U.httpserver import (
    DEFAULT_ALLOWED_NETWORKS, FileServer, is_allowed, parse_networks)

# Talk to the test server directly, even if the environment sets a proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ParseNetworksTest(unittest.TestCase):

    def test_cidr_list(self):
        self.assertEqual(
            parse_networks("192.168.1.0/24, 10.8.0.0/16"),
            [(0xC0A80100, 0xFFFFFF00), (0x0A080000, 0xFFFF0000)])

    def test_bare_address_is_single_host(self):
        self.assertEqual(parse_networks("192.168.1.50"),
                         [(0xC0A80132, 0xFFFFFFFF)])

    def test_host_bits_are_masked_off(self):
        self.assertEqual(parse_networks("192.168.1.77/24"),
                         [(0xC0A80100, 0xFFFFFF00)])

    def test_separators(self):
        self.assertEqual(
            len(parse_networks("10.0.0.0/8;172.16.0.0/12 192.168.0.0/16,,")),
            3)

    def test_empty(self):
        self.assertEqual(parse_networks(""), [])
        self.assertEqual(parse_networks(" , "), [])

    def test_slash_zero_matches_everything(self):
        self.assertEqual(parse_networks("0.0.0.0/0"), [(0, 0)])

    def test_default_is_valid(self):
        self.assertEqual(len(parse_networks(DEFAULT_ALLOWED_NETWORKS)), 3)

    def test_invalid_entries_name_the_culprit(self):
        for bad in ("10.0.0.0/33", "10.0.0.0/-1", "10.0.0.0/x", "abc",
                    "10.1/8", "256.1.1.1", "1.2.3.4.5", "::1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as cm:
                    parse_networks("192.168.0.0/16, " + bad)
                self.assertEqual(str(cm.exception), bad)


class IsAllowedTest(unittest.TestCase):

    def setUp(self):
        self.private = parse_networks(DEFAULT_ALLOWED_NETWORKS)

    def test_none_allows_everyone(self):
        self.assertTrue(is_allowed("8.8.8.8", None))

    def test_private_ranges(self):
        for ip in ("192.168.1.5", "10.9.9.9", "172.16.0.1", "172.31.255.255"):
            with self.subTest(ip=ip):
                self.assertTrue(is_allowed(ip, self.private))
        for ip in ("172.32.0.1", "172.15.255.255", "8.8.8.8", "100.64.0.1"):
            with self.subTest(ip=ip):
                self.assertFalse(is_allowed(ip, self.private))

    def test_loopback_always_allowed(self):
        self.assertTrue(is_allowed("127.0.0.1", []))
        self.assertTrue(is_allowed("127.1.2.3", []))

    def test_single_host(self):
        nets = parse_networks("192.168.1.50")
        self.assertTrue(is_allowed("192.168.1.50", nets))
        self.assertFalse(is_allowed("192.168.1.51", nets))

    def test_garbage_client_address_is_denied(self):
        self.assertFalse(is_allowed("not-an-ip", self.private))
        self.assertFalse(is_allowed("::1", self.private))


class FileServerTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(os.path.join(self.dir, "channels.m3u"), "w") as f:
            f.write("#EXTM3U\n")
        os.mkdir(os.path.join(self.dir, "picon"))
        with open(os.path.join(self.dir, "picon", "a.png"), "wb") as f:
            f.write(b"png")
        self.server = FileServer(self.dir, port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.port = self.server._server.server_address[1]

    def tearDown(self):
        shutil.rmtree(self.dir)

    def get(self, path):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        try:
            with _opener.open(url, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_advertised_paths(self):
        self.assertEqual(self.get("/m3u/channels.m3u"), (200, b"#EXTM3U\n"))
        self.assertEqual(self.get("/m3u/picon/a.png"), (200, b"png"))

    def test_unprefixed_paths_still_work(self):
        self.assertEqual(self.get("/channels.m3u")[0], 200)

    def test_prefix_must_be_a_whole_segment(self):
        self.assertEqual(self.get("/m3uX/channels.m3u")[0], 404)

    def test_no_escape_from_output_dir(self):
        self.assertEqual(self.get("/m3u/../../etc/passwd")[0], 404)

    def test_is_running(self):
        self.assertTrue(self.server.is_running())
        self.server.stop()
        self.assertFalse(self.server.is_running())

    def test_allow_list_enforced_and_live_updatable(self):
        # Loopback is always allowed, so make "loopback" match nothing
        # to test the allow-list from 127.0.0.1.
        with mock.patch.object(httpserver, "_LOOPBACK",
                               (0xFFFFFFFF, 0xFFFFFFFF)):
            self.server.set_allowed_networks(parse_networks("10.0.0.0/8"))
            self.assertEqual(self.get("/m3u/channels.m3u")[0], 403)

            self.server.set_allowed_networks(
                parse_networks("10.0.0.0/8, 127.0.0.0/8"))
            self.assertEqual(self.get("/m3u/channels.m3u")[0], 200)

            self.server.set_allowed_networks(None)
            self.assertEqual(self.get("/m3u/channels.m3u")[0], 200)

    def test_allow_list_passed_to_constructor(self):
        server = FileServer(self.dir, port=0,
                            allowed_networks=parse_networks("10.0.0.0/8"))
        server.start()
        self.addCleanup(server.stop)
        port = server._server.server_address[1]
        with mock.patch.object(httpserver, "_LOOPBACK",
                               (0xFFFFFFFF, 0xFFFFFFFF)):
            url = "http://127.0.0.1:%d/m3u/channels.m3u" % port
            with self.assertRaises(urllib.error.HTTPError) as cm:
                _opener.open(url, timeout=5)
            self.assertEqual(cm.exception.code, 403)
            cm.exception.close()


if __name__ == "__main__":
    unittest.main()
