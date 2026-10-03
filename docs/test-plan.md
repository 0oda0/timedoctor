# Test plan

## Среда (фактически выполнено)
- Windows 11 / Python 3.14 и Docker `debian:bookworm` / Python 3.11: lint, 21 unit/CLI-тест, сборка .deb, `apt install`, `scripts/smoke.sh`, `apt remove` / `purge`.
- version: 0.1.0, commit/tag: _указать при релизе_
- **Не выполнено:** прогон на чистой Astra Linux SE 1.8, реальный chrony, обновление с предыдущей версии, GitFlic pipeline.

## Acceptance
| ID | Сценарий | Проверка | Debian-контейнер | Astra ВМ |
|---|---|---|---|---|
| A1 | sync/unsync различаются | `Analysis.test_A1_sync_vs_unsync` | PASS | TODO |
| A2 | недоступный сервер виден | `Network.test_A2_unreachable_visible`, `Cli.test_unreachable_exit1`, smoke | PASS | TODO |
| A3 | нет chrony | `Analysis.test_A3_no_chrony` | PASS | TODO |
| A4 | отчёт с ключевыми показателями | `Cli.test_A4_report_json` | PASS | TODO |
| A5 | локальный NTP-стенд без Интернета | `Network.test_local_stand` (фейковый NTP на 127.0.0.1); реальный: `SERVER=<ip> scripts/smoke.sh` | PASS (фейк) | TODO |

## Тесты (`./scripts/test.sh`)
- Unit: парсеры chrony/timesyncd/конфигов, `analyze`.
- Валидация: `Config.*` (плохой хост/порт/timeout/секция, отсутствующий файл).
- Нештатные данные: `Parsers.test_garbage`, `test_chronyc_permission_denied`, `test_dns_failure`.
- Отказные: код 2 (конфиг), 3 (запись отчёта), 1 (сервер недоступен).
- Smoke на установленном пакете: `scripts/smoke.sh` (6/6 PASS в контейнере).
