"""Outages: downloads wait a dropped connection out, a run can be made again
from what it was given."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from pipeline.catalog import common
from pipeline.runs import inputs


class Downloads(unittest.TestCase):
    @mock.patch.object(common.time, "sleep", lambda s: None)
    def test_an_outage_is_waited_out(self):
        tries = iter([requests.ConnectionError("down"), requests.Timeout("slow"), "ok"])

        def attempt():
            got = next(tries)
            if isinstance(got, Exception):
                raise got
            return got
        self.assertEqual(common._patiently(attempt), "ok")

    @mock.patch.object(common.time, "sleep", lambda s: None)
    def test_a_long_outage_fails_as_a_catalog_error(self):
        def attempt():
            raise requests.ConnectionError("down")
        with self.assertRaises(common.CatalogError):
            common._patiently(attempt)

    def test_a_refusal_is_not_waited_on(self):
        calls = []

        def attempt():
            calls.append(1)
            raise common.CatalogError("HTTP 404")
        with self.assertRaises(common.CatalogError):
            common._patiently(attempt)
        self.assertEqual(len(calls), 1)


class Again(unittest.TestCase):
    def test_a_runs_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "inputs").mkdir()
            (root / "inputs" / "jar.png").write_bytes(b"png")
            brief = {"t": 0, "kind": "brief", "text": "Face cream, calm, 10 seconds.", "photo": "jar.png",
                     "category": "cream jar", "format": "vertical", "model": None, "director": "storyboard"}
            (root / "log.jsonl").write_text(json.dumps(brief) + "\n", encoding="utf-8")
            given = inputs(root)
            self.assertEqual(given["photo"], root / "inputs" / "jar.png")
            self.assertEqual((given["format"], given["critic"], given["video"], given["short"]),
                             ("vertical", False, True, 1080))   # an older run: the defaults then

    def test_a_run_without_a_brief(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "log.jsonl").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                inputs(folder)


if __name__ == "__main__":
    unittest.main()
