# Руководство пользователя
Команды и коды возврата — в [README](../README.md).
- **Синхронизировано: да/нет/н/д** — по chrony `tracking` (Leap status, stratum), иначе по `timedatectl`.
- **Выбранный источник** — строка `*` в `chronyc sources`.
- **Заключение** — список `[FAIL|WARN|INFO] КОД: пояснение` и `ИТОГ: OK|WARN|FAIL`.
- Отчёт: `time-doctor --format md report -o report.md` (пишется только файл отчёта; время не меняется).

Если видите `NO_DATA` про права — запустите `sudo time-doctor ...` или добавьте пользователя в группу `_chrony`.
