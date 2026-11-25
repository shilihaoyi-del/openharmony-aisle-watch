#!/usr/bin/env python3
"""Print the measured WS63 link events already exposed by the Jetson dashboard."""

import argparse
from collections import OrderedDict
from datetime import datetime
import json
import time
from urllib.request import urlopen


def fetch(source):
    with urlopen("http://127.0.0.1:8787/api/" + source, timeout=1) as response:
        snapshot = json.load(response)
    return snapshot.get("link") if snapshot else None


def timestamp(epoch_ms):
    return datetime.fromtimestamp(epoch_ms / 1000).strftime("%H:%M:%S.%f")[:-3]


class TerminalTrace:
    def __init__(self):
        self.printed = OrderedDict()

    def update(self, link):
        rows = []
        for frame in link["recent"] + link["pending"]:
            capture = frame["capture_ms"]
            label = "帧 " + timestamp(capture)
            parts = frame["segments"]
            events = [(capture, "scan", "采集", "{} 点 → {} 桶，{} 段".format(frame["raw_points"], frame["bins"], parts))]
            for item in frame["tx"]:
                part = item["part"]
                events.append((item["at_ms"], "tx" + str(part), "USB TX",
                               "第 {}/{} 段 · {} B → 感知端 WS63".format(part, parts, item["bytes"])))
            for item in frame["rx"]:
                part = item["part"]
                events.append((item["at_ms"], "rx" + str(part), "SLE RX",
                               "第 {}/{} 段 · {} B · 序号 {} · CRC {} OK · 节点时间 {} ms".format(
                                   part, parts, item["bytes"], item["seq"], item["crc16"], item["sender_uptime_ms"])))
            if frame["status"] == "published":
                at = frame["published_ms"]
                events.append((at, "done", "ROS", "发布 /scan_sle · {} 个有效测距 · 采集后 {} ms".format(
                    frame["valid_bins"], at - capture)))
            elif frame["status"] == "expired":
                events.append((link["updated_ms"], "expired", "超时", "整帧未完成，仅收到 {}/{} 段".format(len(frame["rx"]), parts)))

            printed = self.printed.setdefault(capture, set())
            for at, key, stage, text in events:
                if key not in printed:
                    printed.add(key)
                    prefix = "帧 " + timestamp(capture) if key == "expired" else timestamp(at) + " | " + label
                    rows.append((at, "{} | [{}] {}".format(prefix, stage, text)))

        for _, text in sorted(rows, key=lambda row: row[0]):
            print(text, flush=True)
        while len(self.printed) > 64:
            self.printed.popitem(last=False)


def print_counts(link):
    counts = link["counts"]
    print("已提交 {} 帧 · 已发布 {} 帧 · 超时 {} 帧 · 已核验回传 {} 段 / {} B".format(
        counts["submitted"], counts["completed"], counts["expired"], counts["rx_parts"], counts["rx_bytes"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="print the last recorded trace once")
    args = parser.parse_args()
    print("星闪传输日志  |  SLE SSAP Notification", flush=True)
    try:
        recorded = fetch("recorded")
    except (OSError, ValueError):
        recorded = None
    if recorded:
        print("\n最近一次实测回放 · " + timestamp(recorded["updated_ms"]), flush=True)
        print_counts(recorded)
        TerminalTrace().update(recorded)
    if args.once:
        return 0 if recorded else 1

    print("\n等待实时采集，Ctrl+C 关闭日志窗口。", flush=True)
    trace = None
    seen_update = None
    try:
        while True:
            try:
                live = fetch("live")
            except (OSError, ValueError):
                live = None
            if live is None:
                if trace is not None:
                    print("\n本次实时采集已结束，等待下一次采集。", flush=True)
                trace = None
                seen_update = None
            else:
                update = live["update"]
                if trace is None or (seen_update is not None and update < seen_update):
                    print("\n实时采集已接入", flush=True)
                    trace = TerminalTrace()
                if update != seen_update:
                    trace.update(live)
                    seen_update = update
            time.sleep(0.4)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
