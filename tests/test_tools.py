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
AGILE = REPO / "examples" / "agile-sample"


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
        for root in (REPO / "project", SAMPLE, AGILE):
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

    def test_unknown_wbs_and_affects(self):
        self.edit("decisions/dr-0006.md", 'wbs: "2.1"', 'wbs: "9.9"')
        self.edit("decisions/dr-0006.md", "affects: [2.1]", "affects: [2.1, 8.8]")
        errors = self.errors()[0]
        self.assertTrue(any("wbs 9.9" in e for e in errors))
        self.assertTrue(any("affects の 8.8" in e for e in errors))

    def test_started_deliverable_needs_file(self):
        (self.root / "docs" / "design.md").unlink()
        self.assertTrue(any("docs/design.md がない" in e for e in self.errors()[0]))

    def test_todo_deliverable_may_lack_file(self):
        self.edit("wbs.csv", "4.1,受け入れ基準,todo,完成の条件,", "4.1,受け入れ基準,todo,完成の条件,docs/acceptance.md")
        self.assertEqual(self.errors(), ([], []))


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
                         (2, 2, 2, 1))
        self.assertNotIn("overdue", d["tasks"])  # 期限はタスクではなく問いに置く
        by_wbs = {x["wbs"]: x for x in d["deliverables"]["items"]}
        self.assertEqual((by_wbs["3.1"]["decided"], by_wbs["3.1"]["total"]), (1, 1))  # 覆された DR-0003 は数えない
        self.assertEqual(by_wbs["5.1"]["pct"], 100)

    def test_deliverable_without_questions_is_not_computed(self):
        self.edit("decisions/dr-0008.md", 'wbs: "5.1"', 'wbs: "4.1"')
        build_index.main(["--root", str(self.root)])
        by_wbs = {x["wbs"]: x for x in report.derive(self.root)["deliverables"]["items"]}
        self.assertIsNone(by_wbs["5.1"]["pct"])

    def test_open_question_lists_its_tasks(self):
        opened = {o["id"]: o for o in report.derive(self.root)["decisions"]["open_list"]}
        self.assertEqual(opened["DR-0007"]["tasks"], [{"id": "T-0007", "status": "doing"}])
        self.assertEqual(opened["DR-0006"]["tasks"], [])
        html = report.render(self.build()[0])
        self.assertIn("進めているタスク", html)

    def test_wrong_phrase_number_is_rejected(self):
        self.edit("judgments.json", "7件のうち5件が確定", "8件のうち6件が確定")
        self.assertTrue(any("導出値" in e for e in self.build()[1]))

    def test_unknown_number_is_rejected(self):
        self.edit("judgments.json", "期限は12/15です", "期限は12/31です")
        self.assertTrue(any("数字 31" in e for e in self.build()[1]))

    def test_unknown_reference_is_rejected(self):
        self.edit("judgments.json", "DR-0003 の前提", "DR-0099 の前提")
        self.assertTrue(any("DR-0099" in e for e in self.build()[1]))

    def test_bad_rating_is_rejected(self):
        self.edit("judgments.json", '"rating": "ok"', '"rating": "great"')
        self.assertTrue(any("rating" in e for e in self.build()[1]))

    def test_changed_input_warns_stale(self):
        with open(self.root / "tasks.csv", "a", encoding="utf-8", newline="") as f:
            f.write("T-0008,追加のタスク,DR-0005,todo,,,\r\n")
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


class AgileSandbox(Sandbox):
    """アジャイルの例を写して確かめる。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "p"
        shutil.copytree(AGILE, self.root)

    def plan(self, **changes):
        p = self.root / "plan.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for i, sp in changes.get("sprints", {}).items():
            data["sprints"][i].update(sp)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def reindex(self):
        build_index.main(["--root", str(self.root)])


class TestSprintValidate(AgileSandbox):
    def test_agile_sample_is_clean(self):
        self.assertEqual(self.errors(), ([], []))

    def test_reviewed_sprint_needs_summary(self):
        (self.root / "gates" / "S1.md").rename(self.tmp / "S1.md")
        self.assertTrue(any("スプリント S1" in e and "まとめ" in e for e in self.errors()[0]))

    def test_unknown_sprint_status(self):
        self.plan(sprints={1: {"status": "通過"}})
        self.assertTrue(any("S2 の status" in e for e in self.errors()[0]))

    def test_overlapping_sprints(self):
        self.plan(sprints={1: {"start": "2026-11-13"}})
        self.assertTrue(any("重なっている" in e for e in self.errors()[0]))

    def test_start_after_end(self):
        self.plan(sprints={0: {"start": "2026-11-20"}})
        self.assertTrue(any("start が end より後" in e for e in self.errors()[0]))

    def test_sprint_id_must_not_collide_with_gate(self):
        self.plan(sprints={2: {"id": "R1"}})
        self.assertTrue(any("ゲートのIDと重なっている" in e for e in self.errors()[0]))

    def test_task_sprint_must_exist(self):
        self.edit("tasks.csv", ",todo,,,,S2", ",todo,,,,S9")
        self.assertTrue(any("sprint S9" in e for e in self.errors()[0]))

    def test_verify_at_may_be_sprint(self):
        self.assertFalse(any("verify_at" in e for e in self.errors()[0]))  # DR-0005 は verify_at: S3


class TestSprintDerive(AgileSandbox):
    def test_membership_by_date_and_column(self):
        sp = report.derive(self.root)["sprints"]
        self.assertEqual(sp["current"], "S2")
        by = {s["id"]: s for s in sp["items"]}
        self.assertEqual((by["S1"]["decided"], by["S1"]["tasks_done"]), (4, 2))
        self.assertEqual((by["S2"]["decided"], by["S2"]["open"], by["S2"]["tasks_remaining"]), (1, 1, 2))
        self.assertEqual(by["S3"]["open"], 1)
        self.assertEqual(sp["unassigned_decisions"], 0)

    def test_open_question_moves_with_due(self):
        self.edit("decisions/dr-0006.md", "due: 2026-11-25", "due: 2026-12-01")
        self.reindex()
        by = {s["id"]: s for s in report.derive(self.root)["sprints"]["items"]}
        self.assertEqual((by["S2"]["open"], by["S3"]["open"]), (0, 2))

    def test_selected_sprint(self):
        sp = report.derive(self.root, "S1")["sprints"]
        self.assertEqual(sp["current"], "S1")
        self.assertEqual([d["id"] for d in sp["current_detail"]["decided_list"]],
                         ["DR-0001", "DR-0002", "DR-0003", "DR-0004"])

    def test_unknown_selected_sprint(self):
        with self.assertRaises(report.InputError):
            report.derive(self.root, "S9")

    def test_as_of_outside_sprints(self):
        self.edit("plan.json", '"as_of": "2026-11-19"', '"as_of": "2026-11-28"')
        r, errors, _ = report.build(self.root)
        self.assertEqual(r["derived"]["sprints"]["current"], "")
        self.assertIn("を含むスプリントはない", report.render(r))

    def test_sprint_phrase_is_checked(self):
        self.edit("judgments.json", "このスプリントで確定した決定が1件", "このスプリントで確定した決定が3件")
        _, errors, _ = report.build(self.root)
        self.assertTrue(any("このスプリントで確定した決定が3件" in e for e in errors))

    def test_sprint_open_phrase_does_not_hit_global_rule(self):
        # 「このスプリントの未決の問いが1件」は、全体の「未決の問いが2件」の規則で照合しない
        self.assertEqual(report.build(self.root)[1], [])

    def test_sprint_report_has_no_judgments(self):
        r, errors, _ = report.build(self.root, "S1")
        self.assertEqual((r["judgments"], errors), ({}, []))
        self.assertIn("今のスプリント：S1", report.render(r))

    def test_review_draft(self):
        text = gate.render(self.root, "S2")
        self.assertIn("# S2 スプリントレビュー（2026-11-27）", text)
        self.assertIn("スプリントゴール：データの置き場を移し、延滞が分かる", text)
        self.assertIn("達成 ／ 一部達成 ／ 未達成", text)
        self.assertIn("このスプリント（2026-11-16〜2026-11-27）", text)


class TestNoSprints(Sandbox):
    """スプリントがなければ、従来どおり。"""

    def test_no_sprints_key(self):
        self.assertNotIn("sprints", report.derive(self.root))
        self.assertNotIn("今のスプリント", report.render(report.build(self.root)[0]))

    def test_sprint_option_needs_sprints(self):
        with self.assertRaises(report.InputError):
            report.derive(self.root, "S1")

    def test_tasks_without_sprint_column_are_read(self):
        self.assertEqual(self.errors(), ([], []))


class TestCosts(Sandbox):
    """費用の実績（月ごとの合計）と上限。"""

    def costs(self, *rows, limit=None):
        (self.root / "costs.csv").write_text("\ufeffmonth,item,kind,amount,ref\r\n" + "".join(
            ",".join(r) + "\r\n" for r in rows), encoding="utf-8")
        if limit is not None:
            p = self.root / "plan.json"
            data = json.loads(p.read_text(encoding="utf-8"))
            data["cost_limit"] = limit
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def set_cost_rating(self, rating, text=None):
        p = self.root / "judgments.json"
        j = json.loads(p.read_text(encoding="utf-8"))
        j["cost"]["rating"] = rating
        if text is not None:
            j["cost"]["text"] = text
        p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

    def test_unrecorded(self):
        c = report.derive(self.root)["costs"]
        self.assertEqual((c["recorded"], c["limit"], c["total"]), (False, None, 0))
        self.assertIn("実績：未記録", report.render(report.build(self.root)[0]))

    def test_monthly_limit(self):
        self.costs(["2026-10", "サーバー", "opex", "800", "請求書"], ["2026-11", "サーバー", "opex", "900", "請求書"],
                   ["2026-11", "ドメイン", "opex", "300", "請求書"], limit={"per": "month", "amount": 1000})
        c = report.derive(self.root)["costs"]
        self.assertEqual((c["total"], c["latest_month"], c["latest_month_total"]), (2000, "2026-11", 1200))
        self.assertEqual((c["used_pct"], c["over"], c["over_months"]), (120, True, ["2026-11"]))

    def test_total_limit(self):
        self.costs(["2026-11", "外注", "capex", "50000", "請求書"], limit={"per": "total", "amount": 100000})
        c = report.derive(self.root)["costs"]
        self.assertEqual((c["used_pct"], c["over"]), (50, False))

    def test_ok_needs_record_and_limit(self):
        self.set_cost_rating("ok")
        self.assertTrue(any("ok にできない" in e for e in report.build(self.root)[1]))
        self.costs(["2026-11", "サーバー", "opex", "500", "請求書"])
        self.assertTrue(any("ok にできない" in e for e in report.build(self.root)[1]))  # 上限がない
        self.costs(["2026-11", "サーバー", "opex", "500", "請求書"], limit={"per": "month", "amount": 1000})
        self.set_cost_rating("ok", "11月の実績は500円で、上限の50%です。")
        self.assertEqual(report.build(self.root)[1], [])

    def test_ok_rejected_when_over(self):
        self.costs(["2026-11", "サーバー", "opex", "1500", "請求書"], limit={"per": "month", "amount": 1000})
        self.set_cost_rating("ok", "収まっています。")
        self.assertTrue(any("超えている" in e for e in report.build(self.root)[1]))

    def test_amount_with_separator_is_checked(self):
        self.costs(["2026-11", "サーバー", "opex", "4200", "請求書"], limit={"per": "month", "amount": 5000})
        self.set_cost_rating("ok", "11月の実績は4,200円です。")
        self.assertEqual(report.build(self.root)[1], [])
        self.set_cost_rating("ok", "11月の実績は4,300円です。")
        self.assertTrue(any("4300" in e or "4,300" in e for e in report.build(self.root)[1]))

    def test_validate_costs(self):
        self.costs(["2026-13", "サーバー", "opex", "\"1,000\"", "請求書"], ["2026-13", "サーバー", "opex", "5", "請求書"],
                   ["2026-11", "機器", "asset", "5", "請求書"],
                   limit={"per": "week", "amount": -1, "kind": "both"})
        errors = self.errors()[0]
        for word in ("YYYY-MM", "整数でない", "重複", "kind が capex / opex でない", "per が month / total でない",
                     "amount が0以上の数でない", "cost_limit の kind"):
            self.assertTrue(any(word in e for e in errors), word)

    def test_costs_change_input_ids(self):
        self.assertNotIn("costs", report.input_ids(self.root))
        self.costs(["2026-11", "サーバー", "opex", "500", "請求書"])
        self.assertIn("costs", report.input_ids(self.root))

    def test_capex_and_opex_are_split(self):
        self.costs(["2026-11", "機器", "capex", "30000", "請求書"], ["2026-11", "サーバー", "opex", "900", "請求書"],
                   limit={"per": "month", "amount": 1000})
        c = report.derive(self.root)["costs"]
        self.assertEqual(c["by_kind"], {"capex": 30000, "opex": 900})
        self.assertEqual((c["total"], c["over"]), (30900, True))  # kind がなければ、すべてを上限と比べる

    def test_limit_scoped_to_kind(self):
        self.costs(["2026-11", "機器", "capex", "30000", "請求書"], ["2026-11", "サーバー", "opex", "900", "請求書"],
                   limit={"per": "month", "amount": 1000, "kind": "opex"})
        c = report.derive(self.root)["costs"]
        self.assertEqual((c["total"], c["latest_month_total"], c["used_pct"], c["over"]), (900, 900, 90, False))
        html = report.render(report.build(self.root)[0])
        self.assertIn("Opexの合計 900", html)
        self.assertIn("上限：Opex 月 1,000", html)

    def test_gate_draft_has_cost_row(self):
        self.assertIn("| 費用 | 実績は未記録（costs.csv）。上限は未設定 |", gate.render(self.root, "G2"))


if __name__ == "__main__":
    unittest.main()
