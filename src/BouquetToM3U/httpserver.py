# -*- coding: utf-8 -*-
"""
Tiny background HTTP server for serving the generated playlist files.

Uses a daemon thread so it dies with enigma2. SimpleHTTPServer-style
file serving, no authentication, intended for LAN use only.
"""

import os
import threading
import functools
from http.server import HTTPServer, SimpleHTTPRequestHandler


URL_PREFIX = "/m3u"


class _QuietHandler(SimpleHTTPRequestHandler):
    """Same as SimpleHTTPRequestHandler but doesn't spam the enigma2 log.

    Published URLs look like /m3u/channels.m3u, while the served directory
    is the output dir itself, so the /m3u prefix is stripped here.
    """

    def translate_path(self, path):
        if path == URL_PREFIX or path.startswith(URL_PREFIX + "/") \
                or path.startswith(URL_PREFIX + "?"):
            path = path[len(URL_PREFIX):] or "/"
        return SimpleHTTPRequestHandler.translate_path(self, path)

    def log_message(self, format, *args):
        return


class FileServer(object):
    def __init__(self, directory, port=8888):
        self.directory = directory
        self.port = port
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
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="BouquetToM3U-httpd",
            daemon=True)
        self._thread.start()

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
