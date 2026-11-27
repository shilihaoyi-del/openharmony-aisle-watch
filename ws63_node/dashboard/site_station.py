"""Bind confirmations from the ESP32 USB station to WS63 intrusion reports."""

from collections import deque
import json
import os
import tempfile
from threading import Event, Lock, Thread
import time


def fresh_state(watch, now):
    if not isinstance(watch, dict) or not watch.get("running"):
        return None
    latest = watch.get("latest") or {}
    updated = watch.get("latest_at")
    if not isinstance(updated, (int, float)) or not 0 <= now - updated < 3.5:
        return None
    return latest


def active_event(watch, latest):
    if not latest or latest.get("state") not in ("clear", "occupied", "unknown"):
        return None
    for event in watch.get("events", ()):
        if event.get("session") != latest.get("session"):
            continue
        if event.get("kind") == "baseline":
            break
        if event.get("kind") == "intrusion":
            return event["session"], event["event_id"]
    return None


class SiteStation:
    def __init__(self, watch_path, confirmations_path, port="auto"):
        self.watch_path = watch_path
        self.path = confirmations_path
        self.port = port
        self.lock = Lock()
        self.stop = Event()
        self.last_seen = None
        self.connected_port = None
        self.received = 0
        self.frames = deque(maxlen=5)
        self.last_ack = None
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            self.confirmations = [tuple(item) for item in stored if len(item) == 2]
        except (OSError, ValueError, TypeError):
            self.confirmations = []

    def read_watch(self):
        try:
            return json.loads(self.watch_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def confirm(self, key):
        watch = self.read_watch()
        if key != active_event(watch, fresh_state(watch, time.time())):
            return False
        with self.lock:
            if key in self.confirmations:
                return True
            records = (self.confirmations + [key])[-512:]
            with tempfile.NamedTemporaryFile(mode="w", dir=str(self.path.parent), delete=False) as output:
                temp = output.name
                try:
                    json.dump(records, output)
                    output.flush()
                    os.fsync(output.fileno())
                except BaseException:
                    output.close()
                    os.unlink(temp)
                    raise
            try:
                os.replace(temp, str(self.path))
                self.confirmations = records
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return True

    def decorate(self, watch):
        if not isinstance(watch, dict):
            return watch
        target = active_event(watch, fresh_state(watch, time.time()))
        with self.lock:
            confirmed = set(self.confirmations)
            online = self.last_seen is not None and time.monotonic() - self.last_seen < 2.0
        watch["site_station_online"] = online
        for event in watch.get("events", ()):
            if event.get("kind") == "intrusion":
                key = (event.get("session"), event.get("event_id"))
                event["site_confirmed"] = key in confirmed
                event["site_pending"] = key == target and key not in confirmed
        return watch

    def state_frame(self):
        watch = self.read_watch()
        latest = fresh_state(watch, time.time())
        target = active_event(watch, latest)
        if target is None:
            return (b"AW1 STATE 0 0 idle\n" if latest and latest.get("state") == "clear"
                    else b"AW1 STATE 0 0 offline\n")
        with self.lock:
            mode = "confirmed" if target in self.confirmations else "pending"
        return ("AW1 STATE %d %d %s\n" % (target[0], target[1], mode)).encode("ascii")

    def reception(self):
        with self.lock:
            return dict(online=self.last_seen is not None and time.monotonic() - self.last_seen < 2.0,
                        port=self.connected_port, received=self.received,
                        frames=list(reversed(self.frames)), last_ack=self.last_ack)

    def handle_line(self, line):
        line = line.rstrip(b"\r")
        acknowledgement = None
        if line != b"AW1 READY":
            words = line.split()
            if len(words) != 4 or words[:2] != [b"AW1", b"ACK"] or not all(word.isdigit() for word in words[2:]):
                return
            session, event_id = map(int, words[2:])
            acknowledgement = dict(session=session, event_id=event_id, accepted=self.confirm((session, event_id)))
        with self.lock:
            self.last_seen = time.monotonic()
            self.received += 1
            self.frames.append(dict(number=self.received, line=line.decode("ascii")))
            if acknowledgement is not None:
                self.last_ack = acknowledgement

    def start(self):
        worker = Thread(target=self.run, name="site-confirmation", daemon=True)
        worker.start()

    def run(self):
        try:
            import serial
            from serial.tools.list_ports import comports
        except ImportError:
            print("Site station unavailable: pyserial is missing", flush=True)
            return
        while not self.stop.is_set():
            port_name = self.port
            if port_name == "auto":
                ports = [p.device for p in comports() if (p.vid, p.pid) == (0x303a, 0x1001)]
                port_name = ports[0] if len(ports) == 1 else None
            if port_name:
                try:
                    serial_port = serial.Serial(baudrate=115200, timeout=.1, write_timeout=.3, exclusive=True)
                    serial_port.dtr = serial_port.rts = False
                    serial_port.port = port_name
                    with serial_port:
                        with self.lock:
                            self.connected_port = port_name
                        self.exchange(serial_port)
                except (OSError, ValueError) as error:
                    print("Site station USB: %s" % error, flush=True)
                finally:
                    with self.lock:
                        self.connected_port = None
                        self.last_seen = None
            self.stop.wait(1)

    def exchange(self, port):
        buffer = b""
        next_status = 0
        while not self.stop.is_set():
            now = time.monotonic()
            if now >= next_status:
                port.write(self.state_frame())
                next_status = now + .35
            buffer += port.read(port.in_waiting or 1)
            lines = buffer.split(b"\n")
            buffer = lines.pop()
            if len(buffer) > 128:
                buffer = b""
            for line in lines:
                if len(line) <= 96:
                    self.handle_line(line)
