# エージェント共通の規約

このリポジトリで作業するAIエージェント（Claude Code、Copilot Studio、そのほか）が従う規約。エージェントごとの差分は、`CLAUDE.md`（Claude Code）と `adapters/copilot-studio/`（Copilot Studio）に置く。進め方の全体は `docs/guide.md`。

## 最初に読むもの

1. `project/sessions/` の最新の記録（何が決まり、何が生まれたか）
2. `project/report/report.html`（現在地）、または `python3 tools/report.py --derive` の出力
3. `project/decisions/index.csv`（決定の一覧）と `project/tasks.csv`（タスク）

## 原則

- **AIは提案し、人間が決める。** 決定記録の `status` を `decided` にし、`decided_by` を書いてよいのは、決める人が対話の中ではっきり答えたときだけ。答えがなければ、承認とみなさない。
- **記録した人と根拠を残す。** エージェントが記録するときは、`recorded_by` に自分の名前を、`evidence` に承認の根拠の場所（対話の日付とセッション記録、PR、議事録）を書く。
- **決定記録を先に。** 方針や仕様を変えるときは、先に決定記録を起票し、確定してから変える。確定した記録は書き換えない。覆すときは新しい記録を作り、`supersedes` で前の記録を指し、前の記録を `superseded` にする。補足は、日付付きの「追記」で足す。
- **推奨と追認を残す。** 選択肢を出すときは、反論と見落としも出す。推奨するなら `ai_recommended` に書き、決まったら `followed_recommendation`（推奨どおりか）と `dialogue_before`（決める前に対話で確かめたか）を書く。
- **選択肢を隠さない。** 弱い選択肢を当て馬として並べない。資料にあった選択肢を落とさない。外した選択肢は、理由を付けて記録に残す。
- **不確かなことは断定しない。** 「案」と書く。決定記録にない決定をしない。

## 決定とタスクと結果

- タスクは `project/tasks.csv` に書き、`dr` に元の決定記録（未決の問いを調べるタスクなら、その問い）を必ず書く。タスクは決定記録の中に書かない。
- タスクが終わったら、`status` を `done` にし、`result`（結果を一文で）と `result_ref`（結果の場所：コミット、PR、ファイル）を書く。やめたときは `dropped` にし、`result` に理由を書く。
- 結果が決定の前提を崩したら、決定記録を黙って直さない。新しい決定記録を起票し、オーナーに決めてもらう。
- 決定が覆されたら（`superseded`）、その決定から派生した、終わっていないタスクを、中止するか、新しい決定に付け替える。
- コミットメッセージとPRには、関係する決定記録とタスクのID（`DR-0001`、`T-0001`）を書く。

## 生成物は手で直さない

| 生成物 | 作り方 |
| --- | --- |
| `project/decisions/index.csv` | `python3 tools/build_index.py` |
| `project/report/report.json`、`report.html` | `python3 tools/report.py` |

- 検証：`python3 tools/validate.py`。エラーがない状態でコミットする。
- テスト：`python3 -m unittest discover -s tests`。
- CI（`.github/workflows/check.yml`）が、生成物が入力と一致するかと、検証とテストを確かめる。

## 判断の欄（judgments.json）の書き方

レポートの数字は道具が導出する。エージェントが書くのは、判断の欄（要約、品質・納期・費用の評価、リスク）だけ。

1. `python3 tools/report.py --derive` の出力と `project/plan.json` を読む。
2. `judgments.json` を、例（`examples/sample-project/judgments.json`）と同じ形で書く。`rating` は `ok` / `caution` / `bad`。要約は400字、品質・納期・費用は200字、リスクは1項目120字まで。
3. 数字は、導出値と計画の値だけを使う。計算し直さない。件数は、次の言い回しで書く（道具が導出値と照合する）：「N件のうちM件が確定」「未決の問いがN件」「期限切れの問いがN件」「残りのタスクがN件」「期限切れのタスクがN件」。
4. `meta` の `assessed_by` に自分の名前、`assessed_at` に日付、`based_on` に `python3 tools/report.py --print-inputs` の出力を書く。`confirmed_by` と `confirmed_at` は空にする。確認は人間が行う。
5. `python3 tools/report.py` が検査に通ることを確かめる。

## ゲート

- ゲートの当日に `python3 tools/gate.py --gate <ゲートID>` で `project/gates/<ゲートID>.md` の下書きを作る。1章（その時点の数字）は手で直さない。
- 2章（条件ごとの確認と根拠）、3章（`verify_at` がこのゲートの決定の照合）、5章（判断の案）を下書きする。判断は人間が決め、決定記録で確定し、まとめの「判断の決定記録」にIDを書く。
- `plan.json` のゲートの `status` を変えたら、検証とレポートを回す。

## 確認の取り方

人間の判断が要るときは、要点を絞り、選択肢で答えられる形で聞く。推奨があれば先頭に置き、推奨であることを示す。答えが得られなかったら、承認とみなさず、聞き直す。

## 書かないこと

実在の組織名・人名・業務実績・社内環境を示唆する情報、メールアドレス、内部URL、APIキー、トークン。例は架空にする。

## まだ確かめていないこと

ゲートの運用（`plan.json` の `gates`、`gates/`）と、決定の結果を後から確かめる運用（`verify_at`、期待）は、このテンプレートの元になったプロジェクトでも、まだ一巡していない。使ってみて、合わなければ、決定記録を起票して変える。
