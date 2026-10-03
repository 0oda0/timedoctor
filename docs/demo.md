# Demo (7–10 мин)
1. **Проблема (45 с):** время уехало — один инструмент вместо россыпи `timedatectl`/`chronyc`/`ntpdate`.
2. **Архитектура (60 с):** `cli` → `core` (System-абстракция, парсеры, SNTP) → единый отчёт → text/json/md; только чтение.
3. **Установка (60 с):** `sudo apt install ./dist/time-doctor_0.1.0_amd64.deb`; `time-doctor --version`; `dpkg -L time-doctor`.
4. **Основной сценарий (2–3 мин):** `time-doctor`; `time-doctor --server <ip-стенда> check`; `time-doctor --format json report -o /tmp/r.json`.
5. **Отказ (60 с):** `time-doctor --server 10.255.255.1 check` → FAIL, код 1; `--server "bad host"` → код 2; `sudo systemctl stop chrony` → UNSYNCHRONIZED/NO_MECHANISM.
6. **CI/тесты (60 с):** pipeline lint → test → package, `./scripts/test.sh`, таблица в test-plan.md.
7. **Вклад (60 с):** _заполнить: участник 1 — cli/core; 2 — debian/CI; 3 — тесты/docs_.
8. **Ограничения (30 с):** ntpd без offset; SNTP — разовый замер.
