# Руководство администратора
- Установка/обновление: `sudo apt install ./time-doctor_<версия>_amd64.deb` (новая версия ставится поверх; правки `/etc/time-doctor/time-doctor.conf` сохраняются как conffile).
- Удаление: `apt remove` (конфиг остаётся), `apt purge` (удаляет конфиг). Чужие файлы не затрагиваются.
- `[probe] servers` в конфиге — явный список разрешённых серверов; если пуст, опрашиваются серверы из конфигурации chrony/timesyncd/ntpd этой машины. Прочие адреса — только через `--server`.
- Локальный стенд без Интернета: на второй ВМ `chrony` с `allow <подсеть>` и `local stratum 10`; на проверяемой — `time-doctor --server <ip> check`.
- Сборка: `./scripts/package.sh` (dpkg-deb); CI — `gitflic-ci.yaml` (lint → test → package, артефакт `dist/*.deb`).
- Версия хранится в `src/time_doctor/__init__.py` и `debian/changelog` (package.sh падает при расхождении); релиз — тег `v<версия>`.
