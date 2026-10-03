# Примеры
- `time-doctor.conf` — образец конфигурации (`--config FILE`).
- Локальный NTP-стенд без Интернета: `chronyd` на второй ВМ (`allow`, `local stratum 10`) и
  `time-doctor --server <ip-стенда> check`.
