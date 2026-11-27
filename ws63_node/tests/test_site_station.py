import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from site_station import SiteStation


class StationTests(unittest.TestCase):
    def test_acknowledgement_matches_event_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            watch = Path(directory) / "watch.json"
            log = Path(directory) / "confirmed.json"
            events = [dict(kind="restored", session=23, event_id=7),
                      dict(kind="intrusion", session=23, event_id=6)]
            snapshot = dict(running=True, latest=dict(session=23, state="clear"),
                            latest_at=time.time(), events=events)
            watch.write_text(json.dumps(snapshot), encoding="utf-8")
            station = SiteStation(watch, log)
            self.assertEqual(station.state_frame(), b"AW1 STATE 23 6 pending\n")
            self.assertTrue(station.decorate(station.read_watch())["events"][1]["site_pending"])
            station.handle_line(b"AW1 READY\r")
            station.handle_line(b"AW1 ACK 23 7")
            self.assertFalse(log.exists())
            self.assertFalse(station.reception()["last_ack"]["accepted"])
            station.handle_line(b"AW1 ACK 23 6")
            station.handle_line(b"AW1 ACK 23 6")
            self.assertEqual(json.loads(log.read_text(encoding="utf-8")), [[23, 6]])
            reception = station.reception()
            self.assertTrue(reception["online"])
            self.assertEqual(reception["received"], 4)
            self.assertEqual(reception["frames"][0], dict(number=4, line="AW1 ACK 23 6"))
            self.assertEqual(reception["last_ack"], dict(session=23, event_id=6, accepted=True))
            restored = SiteStation(watch, log)
            self.assertEqual(restored.state_frame(), b"AW1 STATE 23 6 confirmed\n")
            event = restored.decorate(restored.read_watch())["events"][1]
            self.assertTrue(event["site_confirmed"])
            self.assertFalse(event["site_pending"])

    def test_previous_session_and_stale_snapshot_cannot_receive_acknowledgements(self):
        with tempfile.TemporaryDirectory() as directory:
            watch = Path(directory) / "watch.json"
            log = Path(directory) / "confirmed.json"
            station = SiteStation(watch, log)
            snapshot = dict(running=True, latest=dict(session=25, state="occupied"),
                            latest_at=time.time(), events=[dict(kind="intrusion", session=24, event_id=2)])
            watch.write_text(json.dumps(snapshot), encoding="utf-8")
            station.handle_line(b"AW1 ACK 24 2")
            self.assertFalse(log.exists())
            snapshot["events"][0]["session"] = 25
            snapshot["latest_at"] -= 10
            watch.write_text(json.dumps(snapshot), encoding="utf-8")
            station.handle_line(b"AW1 ACK 25 2")
            self.assertFalse(log.exists())
            self.assertEqual(station.state_frame(), b"AW1 STATE 0 0 offline\n")
            self.assertFalse(station.decorate(station.read_watch())["events"][0]["site_pending"])
