import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "generate_fixtures.py"
SPEC = importlib.util.spec_from_file_location("fixture_generator", SOURCE)
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "fixtures"
        GENERATOR.generate(cls.root, list(GENERATOR.SCENARIOS))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_isolated_materials_and_deterministic_hashes(self):
        second = Path(self.temp.name) / "repeat"
        GENERATOR.generate(second, list(GENERATOR.SCENARIOS))
        for name in GENERATOR.SCENARIOS:
            manifest = json.loads((self.root / name / "fixture-manifest.json").read_text())
            self.assertTrue(manifest["synthetic"])
            for item in manifest["files"]:
                content = (self.root / name / item["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), item["sha256"])
                self.assertEqual(content, (second / name / item["path"]).read_bytes())
                self.assertNotIn("maintainer", item["path"])
                self.assertNotIn("rubric", item["path"])
        with self.assertRaises(ValueError):
            GENERATOR.generate(self.root, ["existing-labels"])

    def test_existing_checker_runs_from_unrelated_directory(self):
        script = self.root / "existing-labels/materials/existing_project/check_data.py"
        result = subprocess.run([sys.executable, str(script)], cwd=self.temp.name, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["images"], 12)
        self.assertEqual(json.loads(result.stdout)["missing"], [])

    def test_coverage_contains_class_balance_but_small_object_gap(self):
        entries = json.loads((self.root / "coverage-gap/materials/object-index.json").read_text())
        self.assertEqual(len(entries), 80)
        counts = {label: sum(x["class"] == label for x in entries) for label in (0, 1)}
        self.assertEqual(counts, {0: 40, 1: 40})
        small = [x for x in entries if x["box_xyxy"][2] - x["box_xyxy"][0] < 12]
        self.assertEqual(len(small), 4)
        self.assertEqual(sum(x["class"] == 1 for x in small), 2)

    def test_frozen_predictions_change_comparison_under_shared_policy(self):
        root = self.root / "metric-regression"
        results = {}
        for model in ("old", "new"):
            for labels in ("a", "b"):
                target = root / f"work/{model}-{labels}.json"
                subprocess.run([
                    sys.executable, str(root / "materials/tools/score.py"),
                    "--predictions", str(root / f"materials/predictions/model-{model}.json"),
                    "--labels", str(root / f"materials/labels/labels-{labels}.json"),
                    "--output", str(target),
                ], check=True, capture_output=True)
                results[(model, labels)] = json.loads(target.read_text())["tp"]
        self.assertEqual(results, {("old", "a"): 4, ("old", "b"): 2, ("new", "a"): 3, ("new", "b"): 3})

    def test_restore_materials_have_one_job_and_later_completion(self):
        root = self.root / "resume-rule-change/materials"
        stale = json.loads((root / "task-state.json").read_text())
        completion = json.loads((root / "jobs/synthetic-train-0042/completion.json").read_text())
        self.assertEqual(stale["job_id"], completion["job_id"])
        self.assertGreater(completion["finished_at"], stale["last_checked"])
        self.assertEqual(completion["status"], "completed")

    def test_adapter_failure_is_local_argument_issue_and_repair_runs(self):
        root = self.root / "tool-adaptation"
        script = root / "materials/proposal_export.py"
        broken = subprocess.run([
            sys.executable, str(script), "--input", str(root / "materials/proposals.json"),
            "--output-format", "yolo", "--output", str(root / "work/labels"),
        ], capture_output=True, text=True)
        self.assertNotEqual(broken.returncode, 0)
        mapping = root / "work/class-map.json"
        mapping.write_text(json.dumps({"helmet": 0, "no_helmet": 1}))
        subprocess.run([
            sys.executable, str(script), "--input", str(root / "materials/proposals.json"),
            "--format", "yolo", "--output-dir", str(root / "work/labels"),
            "--class-map", str(mapping),
        ], capture_output=True, check=True)
        labels = sorted((root / "work/labels").glob("*.txt"))
        self.assertEqual(len(labels), 3)
        for label in labels:
            tokens = label.read_text().split()
            self.assertEqual(len(tokens), 5)
            self.assertIn(int(tokens[0]), (0, 1))
            self.assertTrue(all(0 <= float(x) <= 1 for x in tokens[1:]))

    def test_annotation_start_is_sparse_and_inventory_tool_runs(self):
        root = self.root / "annotation-start/materials"
        self.assertEqual(len(list((root / "images").glob("*.png"))), 8)
        self.assertEqual(len(list((root / "example-labels").glob("*.txt"))), 2)
        result = subprocess.run([
            sys.executable, str(root / "tools/inspect_saved_proposals.py"),
            "--input", str(root / "saved-proposals.json"),
        ], capture_output=True, text=True, check=True)
        inventory = json.loads(result.stdout)
        self.assertEqual(inventory["proposal_count"], 9)
        self.assertFalse(inventory["actual_model_inference"])
        self.assertIn("frame_99", inventory["images_referenced"])

    def test_annotation_start_contains_separate_geometry_and_business_questions(self):
        root = self.root / "annotation-start/materials"
        saved = json.loads((root / "saved-proposals.json").read_text())
        proposals = {item["proposal_id"]: item for item in saved["proposals"]}
        self.assertEqual(proposals["p02"]["box"], proposals["p03"]["box"])
        self.assertEqual(proposals["p04"]["box"][0], proposals["p04"]["box"][2])
        self.assertLess(proposals["p05"]["box"][0], 0)
        self.assertGreater(proposals["p05"]["box"][2], GENERATOR.WIDTH)
        self.assertNotIn(str(proposals["p08"]["class"]), saved["class_names"])
        self.assertEqual(proposals["p06"]["image_id"], "frame_05")
        self.assertGreater(proposals["p06"]["score"], 0.9)
        self.assertIn("没有记录这种帽子在本现场是否允许", (root / "label-notes.md").read_text())


if __name__ == "__main__":
    unittest.main()
