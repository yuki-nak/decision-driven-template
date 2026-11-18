"""ゲートのまとめ（gates/<ゲートID>.md）の下書きを作る。

使い方:
  python3 tools/gate.py --gate G1                      # project/gates/G1.md を作る（あれば作らない）
  python3 tools/gate.py --gate G1 --root examples/sample-project
  python3 tools/gate.py --gate G1 --force              # 作り直す（記入済みの内容は消える）
  python3 tools/gate.py --gate G1 --stdout             # ファイルに書かず、標準出力に出す

ゲートの当日に作る。1章（その時点の数字）は導出値から書く（LLMを使わない。手で直さない）。
2〜5章は、AIが下書きし、人間が確かめて埋める。ゲートの判断そのものは決定記録で確定し、
「判断の決定記録：DR-NNNN」の行に、そのIDを書く。plan.json のゲートの status を変えると、
tools/validate.py が、まとめと判断の決定記録があるかを確かめる。
"""
import argparse
import pathlib
import re
import sys

import report
from common import DECISION_COLUMNS, DEFAULT_ROOT, InputError, WBS_COLUMNS, read_csv

STATUS_LABEL = {"confirmed": "確定", "partial": "一部決定", "todo": "未着手", "deferred": "後回し"}
TASK_LABEL = {"todo": "未着手", "doing": "作業中", "done": "完了", "dropped": "中止"}
GATE_DECISION_RE = re.compile(r"^- 判断の決定記録：(DR-\d{4})\s*$", re.M)


def expectation(root, filename):
    """決定記録の「期待」の節の最初の段落。なければ空。"""
    text = (root / "decisions" / filename).read_text(encoding="utf-8")
    m = re.search(r"^## 期待[^\n]*\n+(.+?)(?:\n\n|\n## |\Z)", text, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""


def render(root, gate_id):
    d = report.derive(root)
    gate = next((g for g in d["plan"]["gates"] if g.get("id") == gate_id), None)
    if gate is None:
        raise InputError(f"plan.json にゲート {gate_id} がない")
    wbs = {r["wbs"]: r for r in read_csv(root / "wbs.csv", WBS_COLUMNS)}
    decisions = read_csv(root / "decisions" / "index.csv", DECISION_COLUMNS)
    dec, tk, ai = d["decisions"], d["tasks"], d["ai"]
    ids = "、".join(f"{k} {v}" for k, v in report.input_ids(root).items())

    lines = [
        f"# {gate_id} {gate.get('name', '')}（{gate.get('date', '')}）",
        "",
        f"- 作成：`python3 tools/gate.py --gate {gate_id}`（{d['as_of']} の入力から）",
        f"- 入力：{ids}",
        "- 判断の決定記録：（確定したら DR-NNNN を書く）",
        "",
        "## 1. その時点の数字",
        "",
        "道具が導出値から書いた。手で直さない。",
        "",
        "| 項目 | 値 |",
        "| --- | --- |",
        f"| 決定 | {dec['decided'] + dec['open']}件のうち{dec['decided']}件が確定、未決の問いが{dec['open']}件"
        f"（期限切れ{dec['overdue']}件） |",
        f"| 成果物 | 問いのある{d['deliverables']['with_questions']}件のうち、すべて確定したもの"
        f"{d['deliverables']['complete']}件 |",
        f"| タスク | 残り{tk['todo'] + tk['doing']}件、完了{tk['done']}件、中止{tk['dropped']}件 |",
        f"| AIの推奨の追認 | {ai['recommended_decided']}件のうち{ai['followed']}件 |",
        "",
        "## 2. 通過の条件",
        "",
        f"- 条件：{gate.get('condition', '')}",
        "",
        "| WBS | 成果物 | 状態 | 満たしたか | 根拠 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for w in dict.fromkeys(re.findall(r"\d+\.\d+", gate.get("condition", ""))):
        if w in wbs:
            lines.append(f"| {w} | {wbs[w]['title']} | {STATUS_LABEL.get(wbs[w]['status'], wbs[w]['status'])} |  |  |")
    lines += [
        "",
        "条件をWBSの番号で書いていない項目は、下に足す。",
        "",
        "## 3. このゲートで結果を確かめる決定",
        "",
        f"`verify_at: {gate_id}` の決定記録。決定の時点の期待どおりだったかを照合する。",
        "",
        "| 決定記録 | 結論 | 期待 | 照合の結果 |",
        "| --- | --- | --- | --- |",
    ]
    targets = [r for r in decisions if r["verify_at"] == gate_id and r["status"] == "decided"]
    for r in targets:
        lines.append(f"| {r['id']} | {r['title']} | {expectation(root, r['file']) or '（期待の記載なし）'} |  |")
    if not targets:
        lines.append("| （なし） |  |  |  |")
    lines += ["", "## 4. 未決の問い", ""]
    def task_note(o):
        return "、".join(f"{t['id']} {TASK_LABEL.get(t['status'], t['status'])}" for t in o["tasks"]) or "なし"
    lines += [f"- {o['id']} {o['title']}（期限 {o['due'] or 'なし'}{'、期限切れ' if o['overdue'] else ''}。"
              f"進めているタスク：{task_note(o)}）" for o in dec["open_list"]] or ["なし。"]
    lines += [
        "",
        "## 5. 判断",
        "",
        "- 結論：通過 ／ 範囲を絞って通過 ／ 通過しない",
        "- 理由：",
        "- 絞った範囲（あれば）：",
        "- 承認者：",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        text = render(root, args.gate)
    except InputError as e:
        print("エラー: " + str(e), file=sys.stderr)
        return 1
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out = root / "gates" / f"{args.gate}.md"
    if out.exists() and not args.force:
        print(f"{out} はもうある。作り直すときは --force（記入済みの内容は消える）", file=sys.stderr)
        return 1
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"ゲートのまとめの下書きを書いた: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
