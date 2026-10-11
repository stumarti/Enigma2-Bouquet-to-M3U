# OpenEmbedded recipe for image/feed builders (OpenPLi, OpenATV, OE-Alliance...).
# Drop it into your enigma2 plugins layer, e.g.
#   meta-openpli/recipes-openpli/enigma2-plugins/
SUMMARY = "Export an Enigma2 bouquet as M3U playlist + XMLTV EPG over HTTP"
DESCRIPTION = "Exports a chosen bouquet as an M3U playlist and an XMLTV EPG, \
served over HTTP on the LAN for IPTV players (TiviMate, IPTV Smarters, \
Jellyfin, Kodi PVR IPTV Simple, ...)."
HOMEPAGE = "https://github.com/stumarti/Enigma2-Bouquet-to-M3U"
SECTION = "extra"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=64543bb2a6c643a957e7a57207ac65c4"

SRC_URI = "git://github.com/stumarti/Enigma2-Bouquet-to-M3U.git;protocol=https;branch=main"
SRCREV = "${AUTOREV}"
S = "${WORKDIR}/git"

inherit gitpkgv allarch

PV = "1.2.0+git"
PKGV = "1.2.0+git${GITPKGV}"

RDEPENDS:${PN} = "enigma2-plugin-extensions-openwebif python3-core python3-json \
    python3-html python3-compression python3-netclient python3-netserver"

PLUGINDIR = "${libdir}/enigma2/python/Plugins/Extensions/BouquetToM3U"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${PLUGINDIR}
    install -m 0644 ${S}/src/BouquetToM3U/*.py ${S}/src/BouquetToM3U/plugin.png ${D}${PLUGINDIR}/
    sed -i 's/^__version__ = .*/__version__ = "${PKGV}"/' ${D}${PLUGINDIR}/__init__.py
    install -d ${D}/var/www/m3u
}

FILES:${PN} = "${PLUGINDIR} /var/www/m3u"
