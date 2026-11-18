# Copilot Studio で使う（まだ確かめていない）

Microsoft 365（SharePoint、Teams、Power Automate）とCopilot Studioのエージェントで、このテンプレートを回すための手順の案。**この手順は、まだ実際には確かめていない。** 使ってみて合わなかった点は、決定記録を起票して直す。

## 前提

- 正本はGitのまま。CI（`.github/workflows/check.yml`）が、記録の整合を確かめる。
- Copilot Studio のエージェントは、GitもPythonも実行できない。ファイルを読み、決定記録やタスクの**案を文章で作る**ところまでを担う。
- 確定は、Power Automate の承認で人間が行う。承認のIDが、決定記録の `evidence` になる。

## 構成

| 役割 | 置き場・道具 |
| --- | --- |
| 正本 | GitHubのリポジトリ（`project/`） |
| 読むための写し | SharePointのドキュメントライブラリ（`project/` の写し、`report.html`） |
| 対話 | Copilot Studio のエージェント（Teams から使う） |
| 承認 | Power Automate の承認（承認者は決める人） |
| 正本への反映 | 人間がコミットする。またはフローがGitHubにPRを作る |

## 手順

1. **写しを置く**：`project/` と `project/report/report.html` を、SharePointのライブラリに置く。更新のたびに置き直す（手で置く、またはGitHub Actionsから送る。送る場合の認証の情報は、リポジトリのシークレットに置き、ファイルには書かない）。
2. **エージェントを作る**：Copilot Studio でエージェントを作り、知識（ナレッジ）に、手順1のライブラリを指定する。指示（Instructions）に、`instructions.md` の内容を貼る。
3. **問いと選択肢**：利用者がTeamsでエージェントに相談する。エージェントは、決定記録の案（`_template.md` の形）を、選択肢・反論・推奨とともに出す。
4. **承認**：決める人に、Power Automate の承認を送る。承認の本文に、決定記録の案と、選ばれた選択肢を入れる。
5. **反映**：承認されたら、決定記録の案を `project/decisions/dr-NNNN.md` として保存し、`decided_by` に承認者の役割、`recorded_by` に「Copilot Studio」、`evidence` に承認のIDを書く。コミットまたはPRで正本に入れる。
6. **確かめる**：CIが、決定記録・タスク・レポートの整合を確かめる。レポートは `python3 tools/report.py` で作り直し、手順1で写しを置き直す。

## 注意

- エージェントの出力は、案である。承認なしに `status: decided` の記録を正本に入れない。
- 承認者は、決定記録の `owner`（決める人の役割）と一致させる。代理で承認するときは、`evidence` に、本人の承認が分かる記録（会議の議事録など）を書く。
- 実在の組織名、人名、社内のURLは、決定記録に書かない（`AGENTS.md`）。
