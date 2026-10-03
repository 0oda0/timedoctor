"""Сбор и анализ состояния синхронизации времени. Только чтение, ничего не меняет."""
import configparser
import datetime as dt
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

DEFAULT_CONFIG = "/etc/time-doctor/time-doctor.conf"
NTP_EPOCH = 2208988800
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]*[A-Za-z0-9])?$|^[0-9A-Fa-f:.]+$")


class ConfigError(Exception):
    pass


# ---------- доступ к системе (подменяется в тестах) ----------
class System:
    def run(self, argv, timeout=5):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr.strip()
        except FileNotFoundError:
            return 127, "", f"{argv[0]}: команда не найдена"
        except PermissionError:
            return 126, "", f"{argv[0]}: нет прав на запуск"
        except subprocess.TimeoutExpired:
            return 124, "", f"{argv[0]}: таймаут {timeout} с"

    def read(self, path):
        """Текст файла или None (нет файла / нет прав)."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def which(self, name):
        return shutil.which(name)


# ---------- конфигурация ----------
def parse_server(s):
    """'host' или 'host:port' -> (host, port). Иначе ConfigError."""
    s = s.strip()
    host, port = s, 123
    if s.count(":") == 1:
        host, p = s.split(":")
        if not p.isdigit() or not 0 < int(p) < 65536:
            raise ConfigError(f"некорректный порт в '{s}'")
        port = int(p)
    if not host or len(host) > 253 or not HOST_RE.match(host):
        raise ConfigError(f"некорректное имя сервера '{s}'")
    return host, port


def load_config(path=None, sysm=None, extra_servers=(), timeout=None):
    sysm = sysm or System()
    cfg = {"servers": [], "timeout": 2.0, "max_offset_ms": 100.0}
    text = sysm.read(path or DEFAULT_CONFIG)
    if text is None and path:
        raise ConfigError(f"не удалось прочитать конфигурацию {path}")
    if text is not None:
        cp = configparser.ConfigParser()
        try:
            cp.read_string(text)
            cfg["servers"] = cp.get("probe", "servers", fallback="").replace(",", " ").split()
            cfg["timeout"] = cp.getfloat("probe", "timeout", fallback=cfg["timeout"])
            cfg["max_offset_ms"] = cp.getfloat("thresholds", "max_offset_ms", fallback=cfg["max_offset_ms"])
        except (configparser.Error, ValueError) as e:
            raise ConfigError(f"ошибка в конфигурации: {e}")
    cfg["servers"] += list(extra_servers)
    if timeout is not None:
        cfg["timeout"] = timeout
    if not 0 < cfg["timeout"] <= 30:
        raise ConfigError("timeout должен быть в диапазоне (0, 30] секунд")
    if cfg["max_offset_ms"] <= 0:
        raise ConfigError("max_offset_ms должен быть > 0")
    for s in cfg["servers"]:
        parse_server(s)
    return cfg


# ---------- парсеры (чистые функции) ----------
def parse_kv(text):
    return dict(l.split("=", 1) for l in text.splitlines() if "=" in l)


def parse_chrony_tracking(csv):
    """`chronyc -c tracking` -> dict или None."""
    f = csv.strip().split(",")
    if len(f) < 14:
        return None
    try:
        stratum = int(f[2])
        return {"ref_id": f[0], "ref_name": f[1], "stratum": stratum,
                "offset_s": float(f[4]), "rms_s": float(f[6]),
                "root_delay_s": float(f[10]), "leap": f[13],
                "synced": f[13] != "Not synchronised" and stratum > 0}
    except ValueError:
        return None


def parse_chrony_sources(csv):
    out = []
    for line in csv.splitlines():
        f = line.split(",")
        if len(f) < 8:
            continue
        try:
            out.append({"name": f[2], "state": f[1], "stratum": int(f[3]),
                        "reach": int(f[5], 8), "offset_s": float(f[7]), "selected": f[1] == "*"})
        except ValueError:
            continue
    return out


def parse_timesync_status(text):
    kv = {}
    for l in text.splitlines():
        if ":" in l:
            k, v = l.split(":", 1)
            kv[k.strip()] = v.strip()
    if "Server" not in kv:
        return None
    m = re.match(r"([+-]?[\d.]+)\s*(us|ms|s)", kv.get("Offset", ""))
    off = float(m.group(1)) * {"us": 1e-6, "ms": 1e-3, "s": 1}[m.group(2)] if m else None
    st = int(kv["Stratum"]) if kv.get("Stratum", "").isdigit() else None
    return {"server": kv["Server"], "stratum": st, "offset_s": off}


def parse_configured_servers(text):
    """server/pool/peer из chrony.conf/ntp.conf либо NTP= из timesyncd.conf."""
    res = []
    for l in text.splitlines():
        l = l.split("#")[0].strip()
        m = re.match(r"(?:server|pool|peer)\s+(\S+)", l)
        if m:
            res.append(m.group(1))
        elif l.startswith("NTP="):
            res += l[4:].split()
    return res


# ---------- SNTP-проба ----------
def sntp_query(host, port=123, timeout=2.0):
    """Один SNTP-запрос. Возвращает dict(reachable=..., ...) — исключений не бросает."""
    res = {"server": host if port == 123 else f"{host}:{port}", "reachable": False}
    try:
        addr = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)[0]
    except socket.gaierror:
        res["error"] = "имя не разрешается (DNS)"
        return res
    try:
        with socket.socket(addr[0], socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            t1 = time.time()
            s.sendto(b"\x23" + 47 * b"\0", addr[4])  # LI=0 VN=4 mode=3
            data, _ = s.recvfrom(512)
            t4 = time.time()
    except socket.timeout:
        res["error"] = f"нет ответа за {timeout} с (недоступен/закрыт UDP {port})"
        return res
    except OSError as e:
        res["error"] = f"ошибка сети: {e.strerror or e}"
        return res
    if len(data) < 48 or data[0] & 7 != 4:
        res["error"] = "ответ не похож на NTP-сервер"
        return res
    if data[1] == 0:
        res["error"] = "kiss-of-death (stratum 0)"
        return res

    def ts(o):
        return int.from_bytes(data[o:o + 4], "big") + int.from_bytes(data[o + 4:o + 8], "big") / 2**32 - NTP_EPOCH

    t2, t3 = ts(32), ts(40)
    res.update(reachable=True, stratum=data[1], leap=data[0] >> 6,
               offset_s=((t2 - t1) + (t3 - t4)) / 2, delay_s=(t4 - t1) - (t3 - t2))
    return res


# ---------- сбор ----------
def collect_clock(sysm):
    rc, out, _ = sysm.run(["timedatectl", "show"])
    kv = parse_kv(out) if rc == 0 else {}
    now = dt.datetime.now().astimezone()
    tz = kv.get("Timezone")
    if not tz:
        t = sysm.read("/etc/timezone")
        tz = t.strip() if t else str(now.tzinfo)
    return {"timezone": tz, "utc_offset": now.strftime("%z"), "local_time": now.isoformat(timespec="seconds"),
            "rtc_local": kv.get("LocalRTC") == "yes", "ntp_enabled": kv.get("NTP"),
            "ntp_synchronized": {"yes": True, "no": False}.get(kv.get("NTPSynchronized")),
            "source": "timedatectl" if kv else "fallback (timedatectl недоступен)"}


def collect_mechanism(sysm):
    def active(svc):
        return sysm.run(["systemctl", "is-active", svc])[1].strip() == "active"

    cands = {"chrony": (["chronyc"], ["chrony", "chronyd"]),
             "systemd-timesyncd": (["systemd-timesyncd"], ["systemd-timesyncd"]),
             "ntpd": (["ntpd"], ["ntp", "ntpd"])}
    installed, running = [], []
    for name, (bins, svcs) in cands.items():
        if any(sysm.which(b) for b in bins) or (name == "systemd-timesyncd" and
                                                  Path("/lib/systemd/systemd-timesyncd").exists()):
            installed.append(name)
        if any(active(s) for s in svcs):
            running.append(name)
    return {"mechanism": running[0] if running else "none", "installed": installed, "running": running,
            "chrony_installed": "chrony" in installed}


def collect_sync(sysm, mech):
    """sources, selected, offset/stratum, synced (True/False/None)."""
    info = {"sources": [], "selected": None, "stratum": None, "offset_s": None, "synced": None, "notes": []}
    if mech["mechanism"] == "chrony":
        rc, out, err = sysm.run(["chronyc", "-c", "tracking"])
        tr = parse_chrony_tracking(out) if rc == 0 else None
        if tr:
            info.update(stratum=tr["stratum"], offset_s=tr["offset_s"], synced=tr["synced"], tracking=tr)
            info["sources"] = parse_chrony_sources(sysm.run(["chronyc", "-c", "sources"])[1])
            sel = [s for s in info["sources"] if s["selected"]]
            info["selected"] = sel[0]["name"] if sel else None
        else:
            hint = " (возможно, нужны права: sudo или группа _chrony)" if re.search("ermission|access", err) else ""
            info["notes"].append(f"chronyc tracking недоступен: {err or 'пустой ответ'}{hint}")
    elif mech["mechanism"] == "systemd-timesyncd":
        rc, out, _ = sysm.run(["timedatectl", "timesync-status"])
        ts = parse_timesync_status(out) if rc == 0 else None
        if ts:
            info.update(stratum=ts["stratum"], offset_s=ts["offset_s"], selected=ts["server"],
                        sources=[{"name": ts["server"], "selected": True, "stratum": ts["stratum"]}])
    if info["synced"] is None:
        rc, out, _ = sysm.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
        info["synced"] = out.strip() == "yes" if rc == 0 else None
    return info


def collect_configured(sysm):
    out = []
    for p in ("/etc/chrony/chrony.conf", "/etc/chrony.conf", "/etc/systemd/timesyncd.conf", "/etc/ntp.conf"):
        t = sysm.read(p)
        if t:
            out += parse_configured_servers(t)
    return list(dict.fromkeys(out))


def probe_servers(servers, timeout):
    return [sntp_query(*parse_server(s), timeout=timeout) for s in servers]


def analyze(clock, mech, sync, probes, max_offset_ms):
    F = []

    def add(lvl, code, msg):
        F.append({"level": lvl, "code": code, "message": msg})

    if mech["mechanism"] == "none":
        add("WARN", "NO_MECHANISM", "Служба синхронизации не запущена (chrony/timesyncd/ntpd).")
    if not mech["chrony_installed"]:
        add("INFO", "CHRONY_MISSING", f"chrony не установлен; используется: {mech['mechanism']}.")
    if sync["synced"] is False:
        add("FAIL", "UNSYNCHRONIZED", "Часы не синхронизированы.")
    elif sync["synced"] is None:
        add("WARN", "SYNC_UNKNOWN", "Состояние синхронизации определить не удалось.")
    for n in sync["notes"]:
        add("WARN", "NO_DATA", n)
    if sync["offset_s"] is not None and abs(sync["offset_s"]) * 1000 > max_offset_ms:
        add("WARN", "OFFSET_HIGH", f"Смещение {sync['offset_s'] * 1000:.1f} мс превышает порог {max_offset_ms:g} мс.")
    if clock["rtc_local"]:
        add("WARN", "RTC_LOCAL", "RTC хранит локальное время (рекомендуется UTC).")
    bad = [p for p in probes if not p["reachable"]]
    for p in bad:
        add("FAIL" if len(bad) == len(probes) else "WARN", "SERVER_UNREACHABLE",
            f"Сервер {p['server']} недоступен: {p['error']}.")
    for p in probes:
        if p["reachable"] and abs(p["offset_s"]) * 1000 > max_offset_ms:
            add("WARN", "SERVER_OFFSET", f"Сервер {p['server']}: смещение {p['offset_s'] * 1000:.1f} мс.")
    return F


def collect_all(cfg, sysm=None):
    sysm = sysm or System()
    clock, mech = collect_clock(sysm), collect_mechanism(sysm)
    sync = collect_sync(sysm, mech)
    configured = collect_configured(sysm)
    targets = list(dict.fromkeys(cfg["servers"] + configured))
    probes = probe_servers(targets, cfg["timeout"])
    findings = analyze(clock, mech, sync, probes, cfg["max_offset_ms"])
    status = "FAIL" if any(f["level"] == "FAIL" for f in findings) else \
        "WARN" if any(f["level"] == "WARN" for f in findings) else "OK"
    return {"generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "clock": clock, "mechanism": mech, "sync": sync, "configured_servers": configured,
            "probes": probes, "findings": findings, "status": status}
