#!/usr/bin/env bash
# Собирает dist/time-doctor_<версия>_amd64.deb (нужен dpkg-deb).
set -euo pipefail
cd "$(dirname "$0")/.."
V=$(python3 -c 'import sys; sys.path.insert(0,"src"); import time_doctor; print(time_doctor.__version__)')
CV=$(head -1 debian/changelog | sed 's/.*(\(.*\)).*/\1/')
[ "$V" = "$CV" ] || { echo "Версия в коде ($V) != debian/changelog ($CV)"; exit 1; }
S=$(mktemp -d); trap 'rm -rf "$S"' EXIT
install -d "$S/DEBIAN" "$S/usr/bin" "$S/usr/lib/time-doctor" "$S/etc/time-doctor" "$S/usr/share/doc/time-doctor"
sed "s/@VERSION@/$V/" debian/control > "$S/DEBIAN/control"
cp debian/conffiles "$S/DEBIAN/conffiles"
install -m 755 debian/time-doctor "$S/usr/bin/time-doctor"
cp -r src/time_doctor "$S/usr/lib/time-doctor/"
find "$S" -name __pycache__ -prune -exec rm -rf {} +
install -m 644 debian/time-doctor.conf "$S/etc/time-doctor/time-doctor.conf"
install -m 644 README.md CHANGELOG.md "$S/usr/share/doc/time-doctor/"
find "$S" -type d -exec chmod 755 {} +
find "$S/usr/lib" -type f -exec chmod 644 {} +
mkdir -p dist
dpkg-deb --build --root-owner-group "$S" "dist/time-doctor_${V}_amd64.deb"
