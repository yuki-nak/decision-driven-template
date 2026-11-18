"""道具のテスト。python3 -m unittest discover -s tests"""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build_index  # noqa: E402
import gate  # noqa: E402
import report  # noqa: E402
import validate  # noqa: E402
from common import frontmatter  # noqa: E402

SAMPLE = REPO / "examples" / "sample-project"


class Sandbox(unittest.TestCase):
    """例のプロジェクトを一時ディレクトリに写して、壊して確かめる。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "p"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel, old, new):
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def errors(self):
        return validate.validate(self.root)


class TestCommitted(unittest.TestCase):
    """コミット済みの生成物が、入力と一致する。"""

    def test_index_and_report_match(self):
        for root in (REPO / "project", SAMPLE):
            with self.subTest(root=root.name):
                self.assertEqual(build_index.main(["--root", str(root), "--check"]), 0)
                self.assertEqual(validate.main(["--root", str(root)]), 0)
                self.assertEqual(report.main(["--root", str(root), "--check"]), 0)


class TestFrontmatter(unittest.TestCase):
    def test_template_comments_are_removed(self):
        fm = frontmatter(REPO / "project" / "decisions" / "_template.md")
        self.assertEqual(fm["status"], "open")
        self.assertEqual(fm["evidence"], "")
        self.assertEqual(fm["affects"], "[]")
        self.assertEqual(fm["title"], "問いを一文で（決定後は結論を一文で）")


class TestValidate(Sandbox):
    def test_sample_is_clean(self):
        self.assertEqual(self.errors(), ([], []))

    def test_decided_needs_decided_by(self):
        self.edit("decisions/dr-0001.md", "decided_by: オーナー", "decided_by:")
        self.assertTrue(any("decided_by がない" in e for e in self.errors()[0]))

    def test_recorded_by_other_needs_evidence(self):
        self.edit("decisions/dr-0001.md", "evidence: sessions/2026-11-02_キックオフ.md（オーナーの回答）", "evidence:")
        self.assertTrue(any("evidence" in e for e in self.errors()[0]))

    def test_recommendation_needs_followed(self):
        self.edit("decisions/dr-0001.md", "followed_recommendation: true", "followed_recommendation:")
        self.assertTrue(any("followed_recommendation" in e for e in self.errors()[0]))

    def test_superseded_needs_successor(self):
        self.edit("decisions/dr-0005.md", "supersedes: DR-0003", "supersedes:")
        self.assertTrue(any("覆した決定記録" in e for e in self.errors()[0]))

    def test_task_needs_existing_decision(self):
        self.edit("tasks.csv", "T-0006,満席の表示の文言を決める,DR-0002", "T-0006,満席の表示の文言を決める,DR-0099")
        self.assertTrue(any("DR-0099" in e for e in self.errors()[0]))

    def test_done_task_needs_result(self):
        self.edit("tasks.csv", "2画面の下書き。オーナーの確認済み", "")
        self.assertTrue(any("T-0001" in e and "result" in e for e in self.errors()[0]))

    def test_task_on_superseded_decision_warns(self):
        self.edit("tasks.csv", "T-0006,満席の表示の文言を決める,DR-0002", "T-0006,満席の表示の文言を決める,DR-0003")
        errors, warnings = self.errors()
        self.assertEqual(errors, [])
        self.assertTrue(any("T-0006" in w and "覆された" in w for w in warnings))

    def test_unknown_wbs_and_document(self):
        self.edit("decisions/dr-0006.md", 'wbs: "2.1"', 'wbs: "9.9"')
        self.edit("decisions/dr-0006.md", "affects: [D02]", "affects: [D99]")
        errors = self.errors()[0]
        self.assertTrue(any("9.9" in e for e in errors))
        self.assertTrue(any("D99" in e for e in errors))


class TestGate(Sandbox):
    def test_passed_gate_needs_summary(self):
        (self.root / "gates" / "G1.md").unlink()
        self.assertTrue(any("gates/G1.md がない" in e for e in self.errors()[0]))

    def test_passed_gate_needs_decided_record(self):
        self.edit("gates/G1.md", "判断の決定記録：DR-0008", "判断の決定記録：DR-0006")
        self.assertTrue(any("DR-0006" in e for e in self.errors()[0]))

    def test_unknown_gate_status(self):
        self.edit("plan.json", '"status": "通過"', '"status": "たぶん通過"')
        self.assertTrue(any("status が違う" in e for e in self.errors()[0]))

    def test_verify_at_must_be_date_or_gate(self):
        self.edit("decisions/dr-0002.md", "verify_at: G1", "verify_at: G9")
        self.assertTrue(any("G9" in e for e in self.errors()[0]))

    def test_draft_has_snapshot_and_targets(self):
        text = gate.render(self.root, "G2")
        self.assertIn("7件のうち5件が確定", text)
        self.assertIn("| 2.1 | 要件 |", text)
        self.assertIn("（確定したら DR-NNNN を書く）", text)
        g1 = gate.render(self.root, "G1")
        self.assertIn("| DR-0002 |", g1)  # verify_at: G1 の決定と、その期待
        self.assertIn("満席の表示だけで", g1)

    def test_draft_does_not_overwrite(self):
        self.assertEqual(gate.main(["--root", str(self.root), "--gate", "G1"]), 1)
        self.assertEqual(gate.main(["--root", str(self.root), "--gate", "G2"]), 0)
        self.assertTrue((self.root / "gates" / "G2.md").exists())


class TestReport(Sandbox):
    def build(self):
        return report.build(self.root)

    def test_derived_counts(self):
        d = report.derive(self.root)
        self.assertEqual((d["decisions"]["decided"], d["decisions"]["open"], d["decisions"]["superseded"]), (5, 2, 1))
        self.assertEqual(d["decisions"]["overdue"], 1)
        self.assertEqual((d["ai"]["recommended_decided"], d["ai"]["followed"]), (5, 4))
        self.assertEqual((d["tasks"]["todo"], d["tasks"]["doing"], d["tasks"]["done"], d["tasks"]["dropped"]),
                         (2, 1, 2, 1))
        by_wbs = {x["wbs"]: x for x in d["deliverables"]["items"]}
        self.assertEqual((by_wbs["3.1"]["decided"], by_wbs["3.1"]["total"]), (1, 1))  # 覆された DR-0003 は数えない
        self.assertEqual(by_wbs["5.1"]["pct"], 100)

    def test_deliverable_without_questions_is_not_computed(self):
        self.edit("decisions/dr-0008.md", 'wbs: "5.1"', 'wbs: "4.1"')
        build_index.main(["--root", str(self.root)])
        by_wbs = {x["wbs"]: x for x in report.derive(self.root)["deliverables"]["items"]}
        self.assertIsNone(by_wbs["5.1"]["pct"])

    def test_wrong_phrase_number_is_rejected(self):
        self.edit("judgments.json", "7件のうち5件が確定", "8件のうち6件が確定")
        self.assertTrue(any("導出値" in e for e in self.build()[1]))

    def test_unknown_number_is_rejected(self):
        self.edit("judgments.json", "期限は11/30です", "期限は11/31です")
        self.assertTrue(any("31" in e for e in self.build()[1]))

    def test_unknown_reference_is_rejected(self):
        self.edit("judgments.json", "DR-0003 の前提", "DR-0099 の前提")
        self.assertTrue(any("DR-0099" in e for e in self.build()[1]))

    def test_bad_rating_is_rejected(self):
        self.edit("judgments.json", '"rating": "ok"', '"rating": "great"')
        self.assertTrue(any("rating" in e for e in self.build()[1]))

    def test_changed_input_warns_stale(self):
        with open(self.root / "tasks.csv", "a", encoding="utf-8", newline="") as f:
            f.write("T-0007,追加のタスク,DR-0005,todo,有志A,,,\r\n")
        _, errors, warnings = self.build()
        self.assertEqual(errors, [])
        self.assertTrue(any("tasks" in w for w in warnings))
        html = report.render(self.build()[0])
        self.assertIn("入力が更新済み", html)

    def test_empty_judgments_render(self):
        (self.root / "judgments.json").write_text("{}", encoding="utf-8")
        r, errors, _ = self.build()
        self.assertEqual(errors, [])
        self.assertIn("判断の欄はまだない", report.render(r))

    def test_output_is_deterministic(self):
        a = report.dumps(self.build()[0])
        b = report.dumps(self.build()[0])
        self.assertEqual(a, b)
        json.loads(a)


if __name__ == "__main__":
    unittest.main()
