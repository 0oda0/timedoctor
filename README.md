# time-doctor — диагностика синхронизации времени

Только читает: timezone и состояние часов, механизм синхронизации (chrony / systemd-timesyncd / ntpd / нет),
источники и выбранный источник, offset/stratum, доступность NTP-серверов (SNTP-проба). Время **не меняет**.
Целевая ОС: Astra Linux SE 1.8 x86-64. Зависимости: `python3 (>= 3.9)`, `systemd`; рекомендуется `chrony`.
Постановка задачи: [docs/task.md](docs/task.md).

## Установка / удаление
```
sudo apt install ./dist/time-doctor_0.1.0_amd64.deb
sudo apt remove time-doctor      # конфиг сохраняется
sudo apt purge time-doctor       # + удаляет /etc/time-doctor
```

## Использование (root не нужен)
```
time-doctor --version | --help
time-doctor [doctor]                  # полная диагностика
time-doctor status | sources | check  # части диагностики
time-doctor --server 192.168.56.10 check          # проверить сервер стенда (HOST[:PORT])
time-doctor --format json report -o /tmp/td.json  # отчёт (text|json|md)
```
Коды возврата: `0` — OK/предупреждения, `1` — найдена проблема (не синхронизировано / все серверы недоступны),
`2` — ошибка аргументов или конфигурации, `3` — не удалось записать отчёт.
Конфигурация: `/etc/time-doctor/time-doctor.conf` (пример — `examples/`).

## Разработка
```
./scripts/lint.sh && ./scripts/test.sh && ./scripts/package.sh    # package требует dpkg-deb
./scripts/smoke.sh                                                # на ВМ с установленным пакетом (SERVER=<ip стенда>)
```
Документация: [architecture](docs/architecture.md), [user-guide](docs/user-guide.md), [admin-guide](docs/admin-guide.md),
[test-plan](docs/test-plan.md), [demo](docs/demo.md).
