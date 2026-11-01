"""Run logs: a half-written or broken line never breaks reading a run."""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.runs import events, parse_event


class Log(unittest.TestCase):
    def test_bad_lines_are_skipped(self):
        self.assertIsNone(parse_event(""))
        self.assertIsNone(parse_event('{"kind": "draft", "attempt"'))   # cut off mid-write
        self.assertIsNone(parse_event("[1, 2]"))
        self.assertIsNone(parse_event('{"no": "kind"}'))
        self.assertEqual(parse_event('{"t": 1, "kind": "draft"}'), {"t": 1, "kind": "draft"})

    def test_a_run_with_a_broken_line_still_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            lines = [json.dumps({"t": 0, "kind": "brief"}), '{"t": 1, "kind": "pro', json.dumps({"t": 2, "kind": "finished"})]
            Path(folder, "log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertEqual([e["kind"] for e in events(folder)], ["brief", "finished"])


if __name__ == "__main__":
    unittest.main()
