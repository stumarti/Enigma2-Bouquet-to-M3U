import os
import shutil
import tempfile
import unittest
from unittest import mock

from BouquetToM3U import __version__, plugin
from BouquetToM3U.httpserver import DEFAULT_ALLOWED_NETWORKS, parse_networks

cfg = plugin.config.plugins.BouquetToM3U


class FakeSession(object):
    def __init__(self):
        self.opened = []

    def open(self, screen, *args, **kwargs):
        self.opened.append((screen, args, kwargs))

    def openWithCallback(self, callback, screen, *args, **kwargs):
        self.opened.append((screen, args, kwargs))


class FakeServer(object):
    """Stands in for the module-level FileServer so no port is bound."""

    def __init__(self, port):
        self.port = port
        self.allowed_networks = "unset"

    def is_running(self):
        return True

    def set_allowed_networks(self, networks):
        self.allowed_networks = networks


class PluginTestCase(unittest.TestCase):

    def setUp(self):
        # Snapshot config so tests can't leak settings into each other.
        names = ("bouquet", "refresh_minutes", "port", "picon_dir",
                 "lan_only", "allowed_networks")
        saved = {n: getattr(cfg, n).value for n in names}

        def restore():
            for n, v in saved.items():
                getattr(cfg, n).value = v
                getattr(cfg, n).save()
        self.addCleanup(restore)


class DefaultsTest(PluginTestCase):

    def test_anyone_allowed_by_default(self):
        self.assertFalse(cfg.lan_only.default)
        self.assertIsNone(plugin._allowed_networks())

    def test_allowed_networks_default(self):
        self.assertEqual(cfg.allowed_networks.default, DEFAULT_ALLOWED_NETWORKS)

    def test_other_defaults(self):
        self.assertEqual(cfg.port.default, 8888)
        self.assertEqual(cfg.refresh_minutes.default, "60")
        self.assertEqual(cfg.bouquet.default, "userbouquet.favourites.tv")


class AllowedNetworksTest(PluginTestCase):

    def test_lan_only_uses_configured_networks(self):
        cfg.lan_only.value = True
        cfg.allowed_networks.value = "192.168.1.0/24, 10.8.0.0/24"
        self.assertEqual(plugin._allowed_networks(),
                         parse_networks("192.168.1.0/24, 10.8.0.0/24"))

    def test_invalid_saved_value_falls_back_to_private_ranges(self):
        cfg.lan_only.value = True
        cfg.allowed_networks.value = "192.168.1.0/24, oops"
        self.assertEqual(plugin._allowed_networks(),
                         parse_networks(DEFAULT_ALLOWED_NETWORKS))


class ListBouquetsTest(PluginTestCase):

    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        patcher = mock.patch.object(plugin, "BOUQUETS_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, content):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            f.write(content)

    def test_lists_tv_bouquets_by_display_name(self):
        self.write("userbouquet.b.tv", "#NAME Sports\n#SERVICE 1:0:1\n")
        self.write("userbouquet.a.tv", "#NAME Favourites\n")
        self.write("userbouquet.noname.tv", "#SERVICE 1:0:1\n")
        self.write("userbouquet.radio.radio", "#NAME Radio\n")
        self.write("bouquets.tv", "#NAME Bouquets (TV)\n")
        self.assertEqual(plugin._list_bouquets(), [
            ("userbouquet.a.tv", "Favourites"),
            ("userbouquet.b.tv", "Sports"),
            ("userbouquet.noname.tv", "userbouquet.noname.tv"),
        ])

    def test_missing_directory(self):
        with mock.patch.object(plugin, "BOUQUETS_DIR",
                               os.path.join(self.dir, "missing")):
            self.assertEqual(plugin._list_bouquets(), [])

    def test_refresh_with_missing_bouquet_returns_none(self):
        cfg.bouquet.value = "userbouquet.gone.tv"
        with mock.patch.object(plugin.generator, "refresh_all") as refresh:
            self.assertIsNone(plugin._do_refresh())
        refresh.assert_not_called()

    def test_refresh_passes_config_to_generator(self):
        self.write("userbouquet.a.tv", "#NAME Favourites\n")
        cfg.bouquet.value = "userbouquet.a.tv"
        cfg.port.value = 9000
        result = {"channels": 1, "events": 2}
        with mock.patch.object(plugin.generator, "refresh_all",
                               return_value=result) as refresh:
            self.assertEqual(plugin._do_refresh(), result)
        kwargs = refresh.call_args.kwargs
        self.assertEqual(kwargs["bouquet_filename"],
                         os.path.join(self.dir, "userbouquet.a.tv"))
        self.assertEqual(kwargs["serve_port"], 9000)
        self.assertEqual(kwargs["output_dir"], plugin.OUTPUT_DIR)

    def test_refresh_swallows_generator_errors(self):
        self.write("userbouquet.a.tv", "#NAME Favourites\n")
        cfg.bouquet.value = "userbouquet.a.tv"
        with mock.patch.object(plugin.generator, "refresh_all",
                               side_effect=OSError("OpenWebif down")):
            self.assertIsNone(plugin._do_refresh())
        self.assertFalse(plugin._refresh_in_progress)


class SetupScreenTest(PluginTestCase):

    def setUp(self):
        super().setUp()
        self.server = FakeServer(cfg.port.value)
        patcher = mock.patch.object(plugin, "_file_server", self.server)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = FakeSession()
        self.screen = plugin.BouquetToM3USetup(self.session)

    def test_title_shows_version(self):
        self.assertEqual(self.screen.title, "Bouquet to M3U v" + __version__)

    def test_lists_access_settings(self):
        labels = [label for label, _ in self.screen["config"].list]
        self.assertIn("LAN access only", labels)
        self.assertIn("Allowed networks (comma separated)", labels)

    def test_save_rejects_invalid_network(self):
        cfg.allowed_networks.value = "192.168.1.0/24, 10.0.0.0/33"
        self.screen.save()
        self.assertIsNone(self.screen.closed_with)
        screen, args, _ = self.session.opened[-1]
        self.assertIs(screen, plugin.MessageBox)
        self.assertIn("10.0.0.0/33", args[0])
        self.assertEqual(self.server.allowed_networks, "unset")

    def test_save_applies_access_settings_live(self):
        cfg.lan_only.value = True
        cfg.allowed_networks.value = "192.168.1.0/24, 192.168.20.0/24"
        self.screen.save()
        self.assertEqual(self.screen.closed_with, (True,))
        self.assertTrue(cfg.lan_only.saved_value)
        self.assertEqual(cfg.allowed_networks.saved_value,
                         "192.168.1.0/24, 192.168.20.0/24")
        self.assertEqual(self.server.allowed_networks,
                         parse_networks("192.168.1.0/24, 192.168.20.0/24"))

    def test_save_with_lan_only_off_allows_everyone(self):
        cfg.lan_only.value = False
        self.screen.save()
        self.assertIsNone(self.server.allowed_networks)

    def test_cancel_reverts_changes(self):
        cfg.lan_only.save()
        before = cfg.lan_only.value
        cfg.lan_only.value = not before
        self.screen.cancel()
        self.assertEqual(cfg.lan_only.value, before)
        self.assertEqual(self.screen.closed_with, (False,))


class ScheduleTest(PluginTestCase):

    def test_interval(self):
        cfg.refresh_minutes.value = "15"
        plugin._schedule_next()
        self.assertTrue(plugin._refresh_timer.running)
        self.assertEqual(plugin._refresh_timer.interval, 15 * 60 * 1000)
        self.assertTrue(plugin._refresh_timer.single_shot)

    def test_manual_only(self):
        cfg.refresh_minutes.value = "0"
        plugin._schedule_next()
        self.assertFalse(plugin._refresh_timer.running)


class PluginsTest(unittest.TestCase):

    def test_descriptors(self):
        autostart, menu = plugin.Plugins()
        self.assertEqual(autostart.where, ["autostart"])
        self.assertEqual(menu.name, "Bouquet to M3U")
        self.assertEqual(menu.where, ["pluginmenu", "extensionsmenu"])
        self.assertEqual(menu.icon, "plugin.png")


if __name__ == "__main__":
    unittest.main()
