"""Offline checks of the evidence shipped with this portfolio entry."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class RecordedEvidenceTests(unittest.TestCase):
    def test_boundary_catalog_matches_the_documented_rows(self):
        rows = read_json("matrices/boundaries.json")["rows"]
        self.assertEqual([row["id"] for row in rows], [f"B{i:02}" for i in range(1, 23)])
        matrix = (ROOT / "MATRIX.md").read_text(encoding="utf-8")
        for row in rows:
            with self.subTest(boundary=row["id"]):
                self.assertIn(f"| {row['id']} | {row['boundary']} | {row['invariant']} |", matrix)

    def test_recorded_full_and_repeat_counts(self):
        full, repeat = read_json("evidence/results.json")["runs"]
        for result in (full, repeat):
            self.assertEqual(
                result["total"],
                sum(result[key] for key in ("passed", "failed", "errors", "skipped")),
            )
        self.assertEqual((full["passed"], full["failed"]), (70, 3))
        self.assertEqual((repeat["passed"], repeat["failed"]), (6, 3))
        failed = lambda result: {
            case["name"] for case in result["selected_cases"] if case["status"] == "failed"
        }
        self.assertEqual(failed(full), failed(repeat))
