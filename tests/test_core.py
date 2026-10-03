import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from time_doctor import cli, core  # noqa: E402

TRACK_OK = "C0A80001,192.168.0.1,3,1700000000.0,0.000012,0.000010,0.000020,1.0,0.1,0.05,0.001,0.002,64.0,Normal"
TRACK_BAD = "00000000,,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,Not synchronised"
SOURCES = "^,*,192.168.0.1,2,6,377,10,0.000012,0.000100\n^,-,10.0.0.9,3,6,0,-,0.0,0.0"


class FakeSystem(core.System):
    """Подменяет команды/файлы: cmds — {tuple(argv): (rc, out, err)}."""

    def __init__(self, cmds=None, files=None, bins=()):
        self.cmds, self.files, self.bins = cmds or {}, files or {}, bins

    def run(self, argv, timeout=5):
        return self.cmds.get(tuple(argv), (127, "", f"{argv[0]}: команда не найдена"))

    def read(self, path):
        return self.files.get(path)

    def which(self, name):
        return name if name in self.bins else None


def chrony_sys(track):
    return FakeSystem({
        ("timedatectl", "show"): (0, "Timezone=Europe/Moscow\nLocalRTC=no\nNTP=yes\nNTPSynchronized=yes\n", ""),
        ("systemctl", "is-active", "chrony"): (0, "active\n", ""),
        ("chronyc", "-c", "tracking"): (0, track, ""),
        ("chronyc", "-c", "sources"): (0, SOURCES, ""),
    }, bins=("chronyc",))


def fake_ntp_server(stratum=2):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))

    def loop():
        data, addr = s.recvfrom(64)
        t = int((time.time() + core.NTP_EPOCH) * 2**32)
        pkt = bytearray(48)
        pkt[0], pkt[1] = 0x24, stratum
        pkt[32:40] = pkt[40:48] = t.to_bytes(8, "big")
        s.sendto(bytes(pkt), addr)
        s.close()

    threading.Thread(target=loop, daemon=True).start()
    return s.getsockname()[1]


class Parsers(unittest.TestCase):
    def test_tracking(self):
        t = core.parse_chrony_tracking(TRACK_OK)
        self.assertEqual((t["stratum"], t["synced"]), (3, True))
        self.assertFalse(core.parse_chrony_tracking(TRACK_BAD)["synced"])

    def test_garbage(self):
        self.assertIsNone(core.parse_chrony_tracking("что-то не то"))
        self.assertIsNone(core.parse_chrony_tracking("a,b,x," + ",".join("1" * 11)))
        self.assertEqual(core.parse_chrony_sources("мусор\n,,"), [])
        self.assertIsNone(core.parse_timesync_status(""))

    def test_sources_selected(self):
        s = core.parse_chrony_sources(SOURCES)
        self.assertEqual([x["name"] for x in s if x["selected"]], ["192.168.0.1"])

    def test_timesync(self):
        r = core.parse_timesync_status("Server: 10.0.0.1 (ntp)\nStratum: 2\nOffset: +1.5ms\n")
        self.assertEqual((r["server"], r["stratum"], r["offset_s"]), ("10.0.0.1 (ntp)", 2, 0.0015))

    def test_configured(self):
        txt = "pool ntp.lab iburst\n# server no\nserver 10.0.0.1\nNTP=a b\n"
        self.assertEqual(core.parse_configured_servers(txt), ["ntp.lab", "10.0.0.1", "a", "b"])


class Config(unittest.TestCase):
    def test_bad_server(self):
        for bad in ("bad host", "host:99999", "host:x", "", "a;rm -rf"):
            with self.assertRaises(core.ConfigError, msg=bad):
                core.load_config(None, FakeSystem(), [bad])

    def test_bad_values(self):
        for txt in ("[probe]\ntimeout=0\n", "[probe]\ntimeout=abc\n", "[thresholds]\nmax_offset_ms=-1\n", "[probe\n"):
            with self.assertRaises(core.ConfigError, msg=txt):
                core.load_config("x", FakeSystem(files={"x": txt}))

    def test_missing_explicit_file(self):
        with self.assertRaises(core.ConfigError):
            core.load_config("/nonexistent", FakeSystem())

    def test_ok(self):
        c = core.load_config("x", FakeSystem(files={"x": "[probe]\nservers=a.b, 127.0.0.1:1234\ntimeout=1\n"}))
        self.assertEqual((c["servers"], c["timeout"]), (["a.b", "127.0.0.1:1234"], 1.0))


class Analysis(unittest.TestCase):
    cfg = {"servers": [], "timeout": 0.3, "max_offset_ms": 100.0}

    def test_A1_sync_vs_unsync(self):  # sync и unsync различаются
        ok = core.collect_all(self.cfg, chrony_sys(TRACK_OK))
        bad = core.collect_all(self.cfg, chrony_sys(TRACK_BAD))
        self.assertTrue(ok["sync"]["synced"])
        self.assertEqual(ok["sync"]["selected"], "192.168.0.1")
        self.assertFalse(bad["sync"]["synced"])
        self.assertEqual((ok["status"], bad["status"]), ("OK", "FAIL"))

    def test_A3_no_chrony(self):  # chrony отсутствует — не падаем, объясняем
        r = core.collect_all(self.cfg, FakeSystem())
        self.assertEqual(r["mechanism"]["mechanism"], "none")
        codes = {f["code"] for f in r["findings"]}
        self.assertLessEqual({"CHRONY_MISSING", "NO_MECHANISM", "SYNC_UNKNOWN"}, codes)

    def test_chronyc_permission_denied(self):
        s = chrony_sys(TRACK_OK)
        s.cmds[("chronyc", "-c", "tracking")] = (1, "", "501 Not authorised: Permission denied")
        r = core.collect_all(self.cfg, s)
        self.assertTrue(any("права" in f["message"] for f in r["findings"]))

    def test_offset_high(self):
        s = chrony_sys(TRACK_OK.replace("0.000012,0.000010", "0.5,0.5", 1))
        self.assertIn("OFFSET_HIGH", {f["code"] for f in core.collect_all(self.cfg, s)["findings"]})


class Network(unittest.TestCase):
    def test_local_stand(self):  # A5: локальный NTP без Интернета
        p = core.sntp_query("127.0.0.1", fake_ntp_server(2), 2)
        self.assertTrue(p["reachable"])
        self.assertEqual(p["stratum"], 2)
        self.assertLess(abs(p["offset_s"]), 0.5)

    def test_A2_unreachable_visible(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))  # порт занят, но никто не отвечает
        p = core.sntp_query("127.0.0.1", s.getsockname()[1], 0.3)
        s.close()
        self.assertFalse(p["reachable"])
        self.assertIn("error", p)

    def test_dns_failure(self):
        self.assertFalse(core.sntp_query("no-such-host.invalid", 123, 0.3)["reachable"])


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "time_doctor", *args], capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": os.path.join(ROOT, "src")})

    def test_version_help(self):  # smoke
        self.assertIn("time-doctor 0.1.0", self.run_cli("--version").stdout)
        self.assertEqual(self.run_cli("--help").returncode, 0)

    def test_A4_report_json(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            port = fake_ntp_server()
            r = self.run_cli("--format", "json", "--server", f"127.0.0.1:{port}", "report", "-o", out)
            self.assertIn(r.returncode, (0, 1), r.stderr)
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
            for k in ("clock", "mechanism", "sync", "probes", "findings", "status"):
                self.assertIn(k, data)
            self.assertTrue(data["probes"][0]["reachable"])
            self.assertIn("timezone", data["clock"])

    def test_bad_server_exit2(self):
        r = self.run_cli("--server", "bad host", "check")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_unwritable_report_exit3(self):
        r = self.run_cli("report", "-o", "/nonexistent-dir/x.txt")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("Traceback", r.stderr)

    def test_unreachable_exit1(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        r = self.run_cli("--timeout", "0.3", "--server", f"127.0.0.1:{s.getsockname()[1]}", "check")
        s.close()
        self.assertIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
