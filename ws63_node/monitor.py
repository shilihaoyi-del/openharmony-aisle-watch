#!/usr/bin/env python3
"""Print valid, timestamped WS63 contact reports received on a serial port."""
import argparse
import json
import time


PREFIX = b"WS63_CONTACT_V1 "


def parse_report(line):
    fields = json.loads(line.decode("ascii"))
    if not isinstance(fields, dict) or set(fields) != {"seq", "t_ms", "closed", "event"}:
        raise ValueError("unexpected report fields")
    if any(type(value) is not int for value in fields.values()):
        raise ValueError("report values must be integers")
    if not 0 <= fields["seq"] <= 0xFFFFFFFF or fields["t_ms"] < 0:
        raise ValueError("invalid sequence or timestamp")
    if fields["closed"] not in (0, 1) or fields["event"] not in (0, 1):
        raise ValueError("invalid contact state")
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="the WS63-specific /dev/serial/by-path entry")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not 0 < args.seconds <= 300:
        parser.error("--seconds must be in (0, 300]")
    import serial

    seen = 0
    pending = bytearray()
    deadline = time.monotonic() + args.seconds
    with serial.Serial(args.port, args.baud, timeout=0.2) as port:
        while time.monotonic() < deadline:
            pending.extend(port.read(256))
            while b"\n" in pending:
                line, _, pending = pending.partition(b"\n")
                if not line.startswith(PREFIX):
                    continue
                try:
                    fields = parse_report(bytes(line[len(PREFIX):]))
                except (UnicodeError, ValueError):
                    continue
                seen += 1
                print(json.dumps(fields, sort_keys=True), flush=True)
            if len(pending) > 1024:
                pending.clear()
    return 0 if seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
