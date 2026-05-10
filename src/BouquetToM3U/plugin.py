# -*- coding: utf-8 -*-
"""
Bouquet to M3U / XMLTV — Enigma 2 plugin.

Provides:
  * an autostart hook that launches a tiny HTTP server on a chosen port
  * a scheduled refresh that rebuilds channels.m3u and epg.xml.gz
  * a configuration screen (bouquet + refresh interval)
  * an Extensions and Plugin Browser entry to open the screen / refresh
"""

import os
import threading
import traceback

from enigma import eTimer

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.config import (
    config, ConfigSubsection, ConfigSelection, ConfigText, ConfigInteger,
    getConfigListEntry,
)
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText

from . import generator
from .httpserver import FileServer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

config.plugins.BouquetToM3U = ConfigSubsection()
config.plugins.BouquetToM3U.bouquet = ConfigText(
    default="userbouquet.favourites.tv", fixed_size=False)
config.plugins.BouquetToM3U.refresh_minutes = ConfigSelection(
    default="60",
    choices=[
        ("15", _("Every 15 minutes")),
        ("30", _("Every 30 minutes")),
        ("60", _("Every hour")),
        ("180", _("Every 3 hours")),
        ("360", _("Every 6 hours")),
        ("720", _("Every 12 hours")),
        ("1440", _("Once a day")),
        ("0", _("Manual only")),
    ])
config.plugins.BouquetToM3U.port = ConfigInteger(
    default=8888, limits=(1024, 65535))
config.plugins.BouquetToM3U.picon_dir = ConfigText(
    default="/usr/share/enigma2/picon", fixed_size=False, visible_width=50)

# Sensible defaults that are NOT user-facing (per the design choice).
OUTPUT_DIR = "/var/www/m3u"
STREAM_PORT = 8001
OWIF_HOST = "localhost"
OWIF_PORT = 80
BOUQUETS_DIR = "/etc/enigma2"


# ---------------------------------------------------------------------------
# Singletons (HTTP server + refresh timer)
# ---------------------------------------------------------------------------

_file_server = FileServer(OUTPUT_DIR, port=config.plugins.BouquetToM3U.port.value)
_refresh_timer = None
_refresh_in_progress = False


def _restart_server_if_port_changed():
    """Recreate the FileServer if the configured port differs from the one
    it's currently bound to. Called after saving the config screen."""
    global _file_server
    desired = config.plugins.BouquetToM3U.port.value
    if _file_server.port == desired and _file_server.is_running():
        return
    try:
        _file_server.stop()
    except Exception:
        pass
    _file_server = FileServer(OUTPUT_DIR, port=desired)
    try:
        _file_server.start()
        print("[BouquetToM3U] HTTP server restarted on port %d" % desired)
    except Exception:
        print("[BouquetToM3U] HTTP server failed to start on port %d" % desired)


def _list_bouquets():
    """Return list of (filename, display_name) for all TV bouquets."""
    out = []
    try:
        for fn in sorted(os.listdir(BOUQUETS_DIR)):
            if not (fn.startswith("userbouquet.") and fn.endswith(".tv")):
                continue
            full = os.path.join(BOUQUETS_DIR, fn)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    first = f.readline().strip()
                if first.startswith("#NAME "):
                    name = first[6:]
                else:
                    name = fn
            except Exception:
                name = fn
            out.append((fn, name))
    except OSError:
        pass
    return out


def _do_refresh():
    """Run the generator. Safe to call from a thread."""
    global _refresh_in_progress
    if _refresh_in_progress:
        return None
    _refresh_in_progress = True
    try:
        bouquet_file = os.path.join(
            BOUQUETS_DIR, config.plugins.BouquetToM3U.bouquet.value)
        if not os.path.isfile(bouquet_file):
            print("[BouquetToM3U] bouquet file missing: %s" % bouquet_file)
            return None
        result = generator.refresh_all(
            bouquet_filename=bouquet_file,
            output_dir=OUTPUT_DIR,
            stream_port=STREAM_PORT,
            serve_port=config.plugins.BouquetToM3U.port.value,
            owif_host=OWIF_HOST,
            owif_port=OWIF_PORT,
            picon_dir=config.plugins.BouquetToM3U.picon_dir.value)
        print("[BouquetToM3U] refresh OK: %d channels, %d events" % (
            result["channels"], result["events"]))
        return result
    except Exception:
        print("[BouquetToM3U] refresh failed:\n" + traceback.format_exc())
        return None
    finally:
        _refresh_in_progress = False


def _schedule_next():
    """(Re)arm the refresh timer based on current config."""
    global _refresh_timer
    if _refresh_timer is None:
        _refresh_timer = eTimer()
        try:
            _refresh_timer.callback.append(_on_timer)
        except AttributeError:
            _refresh_timer.timeout.get().append(_on_timer)
    _refresh_timer.stop()
    minutes = int(config.plugins.BouquetToM3U.refresh_minutes.value)
    if minutes > 0:
        _refresh_timer.start(minutes * 60 * 1000, True)  # single-shot


def _on_timer():
    # Run refresh in a thread so we never block enigma2's main loop.
    t = threading.Thread(target=_refresh_then_reschedule,
                         name="BouquetToM3U-refresh", daemon=True)
    t.start()


def _refresh_then_reschedule():
    _do_refresh()
    _schedule_next()


# ---------------------------------------------------------------------------
# Configuration screen
# ---------------------------------------------------------------------------

class BouquetToM3USetup(ConfigListScreen, Screen):
    skin = """
    <screen name="BouquetToM3USetup" position="center,center" size="600,400" title="Bouquet to M3U">
        <widget name="config" position="10,10" size="580,260" scrollbarMode="showOnDemand" />
        <widget source="status" render="Label" position="10,280" size="580,60" font="Regular;20" />
        <widget source="key_red"    render="Label" position="10,360"  size="140,30" font="Regular;18" halign="center" backgroundColor="#9f1313" foregroundColor="#ffffff" />
        <widget source="key_green"  render="Label" position="160,360" size="140,30" font="Regular;18" halign="center" backgroundColor="#1f771f" foregroundColor="#ffffff" />
        <widget source="key_yellow" render="Label" position="310,360" size="140,30" font="Regular;18" halign="center" backgroundColor="#a08500" foregroundColor="#ffffff" />
        <widget source="key_blue"   render="Label" position="460,360" size="140,30" font="Regular;18" halign="center" backgroundColor="#18188b" foregroundColor="#ffffff" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Bouquet to M3U"))

        self["status"] = StaticText("")
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Refresh now"))
        self["key_blue"] = StaticText(_("Show URLs"))

        self._bouquets = _list_bouquets()
        choices = [(fn, name) for fn, name in self._bouquets]
        if not choices:
            choices = [(config.plugins.BouquetToM3U.bouquet.value,
                        config.plugins.BouquetToM3U.bouquet.value)]

        # Dynamic ConfigSelection over the actual bouquets on disk
        self.bouquet_cfg = ConfigSelection(
            default=config.plugins.BouquetToM3U.bouquet.value,
            choices=choices)

        config_list = [
            getConfigListEntry(_("Bouquet"), self.bouquet_cfg),
            getConfigListEntry(_("Refresh interval"),
                               config.plugins.BouquetToM3U.refresh_minutes),
            getConfigListEntry(_("HTTP server port"),
                               config.plugins.BouquetToM3U.port),
            getConfigListEntry(_("Picon directory"),
                               config.plugins.BouquetToM3U.picon_dir),
        ]
        ConfigListScreen.__init__(self, config_list)

        self["actions"] = ActionMap(
            ["ColorActions", "SetupActions"],
            {
                "red": self.cancel,
                "cancel": self.cancel,
                "green": self.save,
                "ok": self.save,
                "yellow": self.refresh_now,
                "blue": self.show_urls,
            }, -2)

        self._update_status()

    def _update_status(self):
        running = _file_server.is_running()
        server = _("running") if running else _("stopped")
        ip = generator._get_lan_ip()
        port = config.plugins.BouquetToM3U.port.value
        self["status"].setText(
            _("HTTP server: %s on port %d\nM3U: http://%s:%d/m3u/channels.m3u")
            % (server, port, ip, port))

    def cancel(self):
        for x in self["config"].list:
            x[1].cancel()
        self.close(False)

    def save(self):
        config.plugins.BouquetToM3U.bouquet.value = self.bouquet_cfg.value
        config.plugins.BouquetToM3U.bouquet.save()
        config.plugins.BouquetToM3U.refresh_minutes.save()
        config.plugins.BouquetToM3U.port.save()
        config.plugins.BouquetToM3U.picon_dir.save()
        config.plugins.BouquetToM3U.save()
        _restart_server_if_port_changed()
        _schedule_next()
        self.close(True)

    def refresh_now(self):
        # Save first so the in-progress refresh uses current selection.
        config.plugins.BouquetToM3U.bouquet.value = self.bouquet_cfg.value
        config.plugins.BouquetToM3U.bouquet.save()
        self.session.openWithCallback(
            self._refresh_done, _ProgressRefresh)

    def _refresh_done(self, result):
        if result is None:
            self.session.open(
                MessageBox,
                _("Refresh failed. See enigma2 log for details."),
                MessageBox.TYPE_ERROR, timeout=5)
        else:
            self.session.open(
                MessageBox,
                _("Refresh complete:\n%d channels, %d events\n\n%s\n%s") % (
                    result["channels"], result["events"],
                    result["m3u_url"], result["epg_url"]),
                MessageBox.TYPE_INFO, timeout=10)
        self._update_status()

    def show_urls(self):
        ip = generator._get_lan_ip()
        port = config.plugins.BouquetToM3U.port.value
        msg = _(
            "M3U playlist:\nhttp://%s:%d/m3u/channels.m3u\n\n"
            "EPG (XMLTV, gzipped):\nhttp://%s:%d/m3u/epg.xml.gz\n\n"
            "Point any IPTV player at the M3U URL — the EPG is\n"
            "loaded automatically via the url-tvg header."
        ) % (ip, port, ip, port)
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=15)


# ---------------------------------------------------------------------------
# Modal "refresh in progress" screen
# ---------------------------------------------------------------------------

class _ProgressRefresh(Screen):
    skin = """
    <screen name="BouquetToM3UProgress" position="center,center" size="500,140" title="Bouquet to M3U">
        <widget source="text" render="Label" position="10,10" size="480,120" font="Regular;20" halign="center" valign="center" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Bouquet to M3U"))
        self["text"] = StaticText(_("Generating playlist and EPG...\nPlease wait."))
        self._result = None
        self._poll = eTimer()
        try:
            self._poll.callback.append(self._check)
        except AttributeError:
            self._poll.timeout.get().append(self._check)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._poll.start(500, False)

    def _run(self):
        self._result = _do_refresh()

    def _check(self):
        if self._thread.is_alive():
            return
        self._poll.stop()
        self.close(self._result)


# ---------------------------------------------------------------------------
# Plugin entry points
# ---------------------------------------------------------------------------

def _open_setup(session, **kwargs):
    session.open(BouquetToM3USetup)


def _autostart(reason, **kwargs):
    """Called by Enigma 2 at startup (reason=0) and shutdown (reason=1)."""
    global _file_server
    if reason == 0:
        try:
            _file_server.start()
            print("[BouquetToM3U] HTTP server started on port %d"
                  % config.plugins.BouquetToM3U.port.value)
        except Exception:
            print("[BouquetToM3U] HTTP server failed to start:\n"
                  + traceback.format_exc())
        # Kick off first refresh shortly after boot (don't block startup).
        first = eTimer()
        # Keep a reference so it's not GC'd
        globals()["_first_refresh_timer"] = first
        try:
            first.callback.append(_on_timer)
        except AttributeError:
            first.timeout.get().append(_on_timer)
        first.start(30 * 1000, True)  # 30s after boot
    elif reason == 1:
        try:
            _file_server.stop()
        except Exception:
            pass


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=_autostart),
        PluginDescriptor(
            name=_("Bouquet to M3U"),
            description=_("Generate M3U playlist and XMLTV EPG from a bouquet"),
            where=[
                PluginDescriptor.WHERE_PLUGINMENU,
                PluginDescriptor.WHERE_EXTENSIONSMENU,
            ],
            icon="plugin.png",
            fnc=_open_setup),
    ]
