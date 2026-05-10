PKG     := enigma2-plugin-extensions-bouquettom3u
VERSION := $(shell awk '/^Version:/ {print $$2}' CONTROL/control)
IPK     := dist/$(PKG)_$(VERSION)_all.ipk

PLUGIN_DST := build/usr/lib/enigma2/python/Plugins/Extensions/BouquetToM3U

.PHONY: all clean ipk

all: ipk

ipk: $(IPK)

$(IPK): src/BouquetToM3U/*.py src/BouquetToM3U/plugin.png CONTROL/control CONTROL/postinst CONTROL/prerm
	@echo "==> Building $(IPK)"
	@rm -rf build
	@mkdir -p $(PLUGIN_DST)
	@mkdir -p build/var/www/m3u
	@cp src/BouquetToM3U/*.py src/BouquetToM3U/plugin.png $(PLUGIN_DST)/
	@mkdir -p dist
	@tar --owner=0 --group=0 -C CONTROL -czf build/control.tar.gz ./control ./postinst ./prerm
	@tar --owner=0 --group=0 -C build --exclude='./control.tar.gz' --exclude='./data.tar.gz' --exclude='./debian-binary' -czf build/data.tar.gz ./usr ./var
	@echo '2.0' > build/debian-binary
	@(cd build && ar -r ../$(IPK) debian-binary control.tar.gz data.tar.gz) 2>/dev/null
	@echo "==> $(IPK) built ($$(stat -c%s $(IPK)) bytes)"

clean:
	rm -rf build dist
