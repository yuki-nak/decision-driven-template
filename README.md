# decision-driven-template

LLMと一緒に、**意思決定を中心に**プロジェクトを進めるためのテンプレート。

- **対話で決める**：AIが選択肢・反論・推奨を出し、人間が決める。誰が決め、誰が記録し、AIの推奨に従ったかを残す。
- **いつでもレポートを出せる**：数字は記録から決まった計算で出し、LLMには判断の欄（要約、QCDの評価、リスク）だけを書かせる。LLMが書いた数字は、導出値と照合して検査する。
- **ゲートでまとめを残す**：ゲートの当日に、その時点の数字、条件ごとの確認、決定の期待の照合、判断を、1つのMarkdownに残す。
- **費用は実績で見る**：費用の評価は、外部の仕組み（会計、経費精算）から写した月ごとの実績と上限から、道具が導出した数字で行う。記録がなければ「未記録」となり、良好とは評価できない。
- **スプリントでも回せる**：`plan.json` に `sprints` を書くと、スプリントを小さなプロジェクトの集合として扱う。決定記録の台帳は1本のまま、今のスプリントで何が決まり、何が残っているかを絞って見られる。スプリントのレビューはゲートとして残る。書かなければ、使わないときと同じに動く。
- **決定・タスク・結果がつながる**：タスクは必ず元の決定を指し、終わったら結果とその場所を残す。決定が覆されれば、残っているタスクが警告として見える。

記録はMarkdownとCSVとJSONだけで、特定のツールに依存しない。道具はPythonの標準ライブラリだけで動く。

## 状態

v0（試作）。ゲートとスプリントの運用と、Copilot Studio での手順は、まだ実際には確かめていない（`docs/guide.md`、`adapters/copilot-studio/`）。

## 始め方

1. このリポジトリを写す（GitHub の「Use this template」、または複製）。
2. `project/plan.json` に、プロジェクトの名前、完成の期限と範囲、壁（品質・納期・費用）を書く。
3. `project/wbs.csv` を、自分のプロジェクトの成果物に直す。
4. 最初の問いを、`project/decisions/_template.md` を写して起票する。
5. 道具を回す：

```bash
python3 tools/build_index.py
```

```bash
python3 tools/validate.py
```

```bash
python3 tools/report.py
```

`project/report/report.html` を開くと、現在地が見える。

まず `examples/sample-project/`（架空の例）を見ると、決定 → タスク → 結果 → 決定の見直し、の流れが分かる。スプリントで回すなら、`examples/agile-sample/`（架空の例）と、`docs/guide.md` の「スプリント」を見る。

## 構成

```
AGENTS.md              エージェント共通の規約
CLAUDE.md              Claude Code 用の差分
adapters/copilot-studio/  Copilot Studio と Microsoft 365 で回す手順（案）
docs/guide.md          進め方（記録の形、サイクル、ゲート、スプリント）
project/               あなたのプロジェクト（空で始まる）
examples/sample-project/  架空の例
examples/agile-sample/    架空の例（スプリントで回す）
tools/                 索引・検証・レポート・ゲートのまとめの道具
tests/                 道具のテスト
.github/workflows/     CI（記録の整合、生成物の一致、テスト）
```

## ライセンス

未定。決まるまでは著作権を留保する。
