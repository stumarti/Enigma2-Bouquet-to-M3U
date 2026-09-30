# -*- coding: utf-8 -*-
"""
Tiny background HTTP server for serving the generated playlist files.

Uses a daemon thread so it dies with enigma2. SimpleHTTPServer-style
file serving, no authentication, intended for LAN use only.
"""

import os
import socket
import struct
import threading
import functools
from http.server import HTTPServer, SimpleHTTPRequestHandler


URL_PREFIX = "/m3u"

# Private (RFC 1918) IPv4 ranges: the default "LAN only" allow-list.
DEFAULT_ALLOWED_NETWORKS = "192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12"

# The box itself is always allowed.
_LOOPBACK = (0x7F000000, 0xFF000000)


def _ip_to_int(ip):
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def parse_networks(text):
    """Parse "192.168.1.0/24, 10.8.0.0/16, 192.168.2.50" into a list of
    (network, mask) integer pairs. A bare address means a single host.
    Raises ValueError naming the first bad entry."""
    networks = []
    for entry in text.replace(";", ",").replace(" ", ",").split(","):
        entry = entry.strip()
        if not entry:
            continue
        addr, _sep, bits = entry.partition("/")
        try:
            if addr.count(".") != 3:
                raise ValueError
            ip = _ip_to_int(addr)
            prefix = int(bits) if bits else 32
            if not 0 <= prefix <= 32:
                raise ValueError
        except (ValueError, OSError):
            raise ValueError(entry)
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        networks.append((ip & mask, mask))
    return networks


def is_allowed(client_ip, networks):
    """networks=None means no restriction."""
    if networks is None:
        return True
    try:
        ip = _ip_to_int(client_ip)
    except (ValueError, OSError):
        return False
    for net, mask in [_LOOPBACK] + list(networks):
        if ip & mask == net:
            return True
    return False


class _QuietHandler(SimpleHTTPRequestHandler):
    """Same as SimpleHTTPRequestHandler but doesn't spam the enigma2 log.

    Published URLs look like /m3u/channels.m3u, while the served directory
    is the output dir itself, so the /m3u prefix is stripped here.
    """

    def parse_request(self):
        if not SimpleHTTPRequestHandler.parse_request(self):
            return False
        if not is_allowed(self.client_address[0],
                          self.server.allowed_networks):
            self.send_error(403, "Access restricted to the local network")
            return False
        return True

    def translate_path(self, path):
        if path == URL_PREFIX or path.startswith(URL_PREFIX + "/") \
                or path.startswith(URL_PREFIX + "?"):
            path = path[len(URL_PREFIX):] or "/"
        return SimpleHTTPRequestHandler.translate_path(self, path)

    def log_message(self, format, *args):
        return


class FileServer(object):
    def __init__(self, directory, port=8888, allowed_networks=None):
        self.directory = directory
        self.port = port
        # List of (network, mask) pairs from parse_networks(), or None
        # to allow every client.
        self.allowed_networks = allowed_networks
        self._server = None
        self._thread = None

    def start(self):
        if self._server is not None:
            return  # already running
        os.makedirs(self.directory, exist_ok=True)

        # SimpleHTTPRequestHandler picked up a `directory` kwarg in
        # python 3.7+; functools.partial is the supported way to bind it.
        handler = functools.partial(_QuietHandler, directory=self.directory)
        self._server = HTTPServer(("0.0.0.0", self.port), handler)
        self._server.allowed_networks = self.allowed_networks
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="BouquetToM3U-httpd",
            daemon=True)
        self._thread.start()

    def set_allowed_networks(self, networks):
        """Change the allow-list; takes effect on the next request."""
        self.allowed_networks = networks
        if self._server is not None:
            self._server.allowed_networks = networks

    def stop(self):
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass
        self._server = None
        self._thread = None

    def is_running(self):
        return self._server is not None
