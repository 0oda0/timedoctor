#!/usr/bin/env bash
# Smoke-тест на Astra Linux с установленным пакетом. Печатает таблицу PASS/FAIL.
# Опционально: SERVER=<ip локального NTP-стенда>.
fail=0
t() { if eval "$2" >/dev/null 2>&1; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }
t "--version"                     'time-doctor --version | grep -q time-doctor'
t "--help"                        'time-doctor --help'
t "status без root"               'time-doctor status | grep -q "Часовой пояс"'
t "json-отчёт содержит ключи"     'time-doctor --format json doctor | python3 -c "import json,sys; d=json.load(sys.stdin); assert {\"clock\",\"sync\",\"probes\"}<=set(d)"'
t "недоступный сервер виден"      'time-doctor --timeout 0.5 --server 127.0.0.1:9 check | grep -q FAIL'
t "ошибка конфигурации -> код 2"  'time-doctor --server "bad host" check; [ $? -eq 2 ]'
[ -n "${SERVER:-}" ] && t "локальный NTP-стенд $SERVER" 'time-doctor --server "$SERVER" check | grep -q "OK "'
exit $fail
