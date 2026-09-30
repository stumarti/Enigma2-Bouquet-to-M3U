"""Unit tests for the BouquetToM3U plugin.

Run with `make test` (or `python3 -m unittest discover -s tests -t .`).

enigma2's own modules only exist on a receiver, so importing this package
installs minimal stand-ins for the handful of enigma2 APIs the plugin
touches, and puts src/ on sys.path.
"""

import builtins
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# enigma2 installs gettext's _() as a builtin.
builtins._ = lambda s: s


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class eTimer(object):
    def __init__(self):
        self.callback = []
        self.running = False

    def start(self, msec, single_shot=False):
        self.running = True
        self.interval = msec
        self.single_shot = single_shot

    def stop(self):
        self.running = False


class PluginDescriptor(object):
    WHERE_AUTOSTART = "autostart"
    WHERE_PLUGINMENU = "pluginmenu"
    WHERE_EXTENSIONSMENU = "extensionsmenu"

    def __init__(self, name="", description="", where=None, icon=None,
                 fnc=None):
        self.name = name
        self.description = description
        self.where = where if isinstance(where, list) else [where]
        self.icon = icon
        self.fnc = fnc


class Screen(dict):
    def __init__(self, session):
        dict.__init__(self)
        self.session = session
        self.closed_with = None

    def setTitle(self, title):
        self.title = title

    def close(self, *result):
        self.closed_with = result


class MessageBox(object):
    TYPE_INFO = 1
    TYPE_ERROR = 3


class ChoiceBox(object):
    pass


class ActionMap(object):
    def __init__(self, contexts, actions, prio=0):
        self.contexts = contexts
        self.actions = actions


class StaticText(object):
    def __init__(self, text=""):
        self.text = text

    def setText(self, text):
        self.text = text


class _ConfigElement(object):
    def __init__(self, default=None, choices=None, **kwargs):
        self.default = default
        self.value = default
        self.choices = choices
        self.saved_value = default

    def save(self):
        self.saved_value = self.value

    def cancel(self):
        self.value = self.saved_value


class ConfigSubsection(object):
    def save(self):
        pass


class ConfigList(object):
    def __init__(self, entries):
        self.list = entries


class ConfigListScreen(object):
    def __init__(self, entries):
        self["config"] = ConfigList(entries)


config = ConfigSubsection()
config.plugins = ConfigSubsection()

_module("enigma", eTimer=eTimer)
_module("Plugins")
_module("Plugins.Plugin", PluginDescriptor=PluginDescriptor)
_module("Screens")
_module("Screens.Screen", Screen=Screen)
_module("Screens.MessageBox", MessageBox=MessageBox)
_module("Screens.ChoiceBox", ChoiceBox=ChoiceBox)
_module("Components")
_module("Components.ActionMap", ActionMap=ActionMap)
_module("Components.config",
        config=config,
        ConfigSubsection=ConfigSubsection,
        ConfigSelection=_ConfigElement,
        ConfigText=_ConfigElement,
        ConfigInteger=_ConfigElement,
        ConfigYesNo=_ConfigElement,
        getConfigListEntry=lambda label, element: (label, element))
_module("Components.ConfigList", ConfigListScreen=ConfigListScreen)
_module("Components.Sources")
_module("Components.Sources.StaticText", StaticText=StaticText)
