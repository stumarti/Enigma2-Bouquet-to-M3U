PKG     := enigma2-plugin-extensions-bouquettom3u
# Version comes from CONTROL/control unless overridden, e.g. `make ipk VERSION=1.2.0`
# (CI passes the git tag this way).
VERSION ?= $(shell awk '/^Version:/ {print $$2}' CONTROL/control)
IPK     := dist/$(PKG)_$(VERSION)_all.ipk

PLUGIN_DST := build/usr/lib/enigma2/python/Plugins/Extensions/BouquetToM3U

.PHONY: all clean ipk version FORCE

all: ipk

ipk: $(IPK)

$(IPK): src/BouquetToM3U/*.py src/BouquetToM3U/plugin.png CONTROL/control CONTROL/postinst CONTROL/prerm CONTROL/postrm FORCE
	@echo "==> Building $(IPK)"
	@rm -rf build
	@mkdir -p $(PLUGIN_DST)
	@mkdir -p build/var/www/m3u
	@cp src/BouquetToM3U/*.py src/BouquetToM3U/plugin.png $(PLUGIN_DST)/
	@sed -i 's/^__version__ = .*/__version__ = "$(VERSION)"/' $(PLUGIN_DST)/__init__.py
	@mkdir -p build/CONTROL dist
	@cp CONTROL/postinst CONTROL/prerm CONTROL/postrm build/CONTROL/
	@chmod 755 build/CONTROL/postinst build/CONTROL/prerm build/CONTROL/postrm
	@sed 's/^Version:.*/Version: $(VERSION)/' CONTROL/control > build/CONTROL/control
	@tar --owner=0 --group=0 -C build/CONTROL -czf build/control.tar.gz ./control ./postinst ./prerm ./postrm
	@tar --owner=0 --group=0 -C build --exclude='./control.tar.gz' --exclude='./data.tar.gz' --exclude='./debian-binary' -czf build/data.tar.gz ./usr ./var
	@echo '2.0' > build/debian-binary
	@rm -f $(IPK)
	@(cd build && ar -r ../$(IPK) debian-binary control.tar.gz data.tar.gz) 2>/dev/null
	@echo "==> $(IPK) built ($$(stat -c%s $(IPK)) bytes)"

version:
	@echo $(VERSION)

FORCE:

clean:
	rm -rf build dist
