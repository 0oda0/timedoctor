import argparse
import json
import sys

from . import __version__
from .core import ConfigError, collect_all, load_config

# коды возврата: 0 — ок/предупреждения, 1 — найдена проблема, 2 — ошибка аргументов/конфигурации, 3 — ошибка записи отчёта
SECTIONS = {
    "status": ("clock", "mechanism"),
    "sources": ("sources",),
    "check": ("probes",),
    "doctor": ("clock", "mechanism", "sources", "probes", "findings"),
    "report": ("clock", "mechanism", "sources", "probes", "findings"),
}


def _ms(v):
    return "н/д" if v is None else f"{v * 1000:+.3f} мс"


def render_text(r, sections):
    L = []
    if "clock" in sections:
        c = r["clock"]
        L += ["== Часы ==", f"Часовой пояс : {c['timezone']} (UTC{c['utc_offset']})",
              f"Локальное время: {c['local_time']}", f"RTC в локальном времени: {'да' if c['rtc_local'] else 'нет'}",
              f"NTP включён  : {c['ntp_enabled'] or 'н/д'}",
              f"Синхронизировано: {_yn(r['sync']['synced'])}", f"(источник данных: {c['source']})", ""]
    if "mechanism" in sections:
        m = r["mechanism"]
        L += ["== Механизм синхронизации ==", f"Активный   : {m['mechanism']}",
              f"Установлены: {', '.join(m['installed']) or 'нет'}",
              f"chrony     : {'установлен' if m['chrony_installed'] else 'не установлен'}", ""]
    if "sources" in sections:
        s = r["sync"]
        L += ["== Источники ==", f"Выбранный: {s['selected'] or 'нет'}",
              f"Stratum: {s['stratum'] if s['stratum'] is not None else 'н/д'}   Offset: {_ms(s['offset_s'])}"]
        L += [f"  {'*' if x['selected'] else ' '} {x['name']}  stratum={x.get('stratum', '?')}" for x in s["sources"]]
        L += [""]
    if "probes" in sections:
        L.append("== Доступность серверов ==")
        if not r["probes"]:
            L.append("Серверов для проверки нет (задайте --server или [probe] servers в конфигурации).")
        for p in r["probes"]:
            L.append(f"  OK   {p['server']}  stratum={p['stratum']} offset={_ms(p['offset_s'])} delay={_ms(p['delay_s'])}"
                     if p["reachable"] else f"  FAIL {p['server']}  {p['error']}")
        L.append("")
    if "findings" in sections:
        L.append("== Заключение ==")
        L += [f"  [{f['level']}] {f['code']}: {f['message']}" for f in r["findings"]]
        L.append(f"ИТОГ: {r['status']}")
    return "\n".join(L).rstrip() + "\n"


def _yn(v):
    return "н/д" if v is None else "да" if v else "нет"


def render_md(r):
    t = render_text(r, SECTIONS["report"]).splitlines()
    out = ["# Time Doctor — отчёт", f"Сформирован: {r['generated_at']}", ""]
    for l in t:
        out.append(f"## {l[3:-3]}" if l.startswith("== ") else l)
    return "\n".join(out) + "\n"


def build_parser():
    p = argparse.ArgumentParser(
        prog="time-doctor", description="Диагностика синхронизации времени (только чтение).",
        epilog="команды: doctor (по умолчанию) — полная диагностика; status — timezone, часы, механизм; "
               "sources — источники, offset/stratum; check — доступность серверов; report — экспорт (-o FILE)")
    p.add_argument("cmd", nargs="?", default="doctor", choices=list(SECTIONS), metavar="КОМАНДА")
    p.add_argument("--version", action="version", version=f"time-doctor {__version__}")
    p.add_argument("--config", help="файл конфигурации (по умолчанию /etc/time-doctor/time-doctor.conf)")
    p.add_argument("--server", action="append", default=[], metavar="HOST[:PORT]",
                   help="дополнительный NTP-сервер для проверки (можно повторять)")
    p.add_argument("--timeout", type=float, help="таймаут проверки сервера, с")
    p.add_argument("--format", choices=["text", "json", "md"], default="text", help="формат вывода")
    p.add_argument("-o", "--output", help="записать отчёт в файл вместо stdout")
    return p


def main(argv=None, sysm=None):
    args = build_parser().parse_args(argv)
    cmd = args.cmd
    try:
        cfg = load_config(args.config, sysm, args.server, args.timeout)
    except ConfigError as e:
        print(f"time-doctor: ошибка конфигурации: {e}", file=sys.stderr)
        return 2
    r = collect_all(cfg, sysm)
    if args.format == "json":
        out = json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    elif args.format == "md":
        out = render_md(r)
    else:
        out = render_text(r, SECTIONS[cmd])
    target = args.output
    if target:
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(out)
        except OSError as e:
            print(f"time-doctor: не удалось записать {target}: {e.strerror}", file=sys.stderr)
            return 3
        print(f"Отчёт записан: {target}")
    else:
        sys.stdout.write(out)
    return 1 if r["status"] == "FAIL" else 0
