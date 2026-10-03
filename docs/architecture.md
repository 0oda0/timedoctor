# Architecture

## Контекст
Администратор Astra Linux выясняет, почему часы неверны. Приложение **только читает** состояние и опрашивает
NTP-серверы; ничего в системе не меняет (dry-run/rollback не нужны — откатывать нечего).

## Компоненты (`src/time_doctor/`)
| Модуль | Роль |
|---|---|
| `cli.py` | аргументы, команды, рендер text/json/md, коды возврата |
| `core.py` | `System` (единственная точка доступа к командам/файлам, подменяется в тестах), парсеры, сбор, `analyze` |
| `core.sntp_query` | SNTP-клиент на `socket` (UDP 123): offset/delay/stratum |

Внешние команды (все read-only): `timedatectl show|timesync-status`, `systemctl is-active`, `chronyc -c tracking|sources`.
Читаемые файлы: `/etc/timezone`, `/etc/chrony/chrony.conf`, `/etc/systemd/timesyncd.conf`, `/etc/ntp.conf`, `/etc/time-doctor/time-doctor.conf`.

## Поток данных
args → `load_config` (валидация) → `collect_clock` / `collect_mechanism` → `collect_sync` (chrony или timesyncd) →
`probe_servers` (серверы из `--server`/конфига + настроенные в демоне) → `analyze` → единый dict-отчёт → text|json|md.
Формат выводится из одной модели детерминированно (JSON: `sort_keys`), без сети и CDN.

## Права
Всё работает от обычного пользователя. Если `chronyc` без прав недоступен — `NO_DATA` с подсказкой (sudo / группа `_chrony`), а не «неизвестная ошибка».

## Ошибки
Нет утилиты (rc 127) → пустые данные + findings `NO_MECHANISM`, `CHRONY_MISSING`, `SYNC_UNKNOWN`; нет DNS/ответа → `SERVER_UNREACHABLE`;
плохая конфигурация → код 2; traceback пользователю не показывается.
`FAIL` (`UNSYNCHRONIZED`, все серверы недоступны) → код 1; `WARN` (часть серверов, большой offset, RTC local, нет данных); `INFO`.

## Ограничения
ntpd: механизм определяется, но offset/stratum не разбираются (`ntpq` не поддержан). SNTP-проба — одиночный запрос, не замена `chronyc`.

## Packaging
`/usr/bin/time-doctor` (sh-обёртка), `/usr/lib/time-doctor/time_doctor/`, `/etc/time-doctor/time-doctor.conf` (conffile).
`/var/lib` и systemd unit/timer не нужны: состояния нет, запуск по требованию.
