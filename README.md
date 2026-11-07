# claude-rss-curation

Inoreaderのフォルダ記事をGeminiで選別し、コメント付きRSSとして公開する仕組みです。
Claude活用の実践事例を毎日自動で拾います。
Gemini無料枠とGitHub無料枠だけで動き、Claudeの使用量・課金は発生しません。

フィード: https://yoshiken31.github.io/claude-rss-curation/feed.xml

## 仕組み
1. 毎日 05:00 JST（cron `0 20 * * *` UTC）に GitHub Actions が `scripts/curate.py` を実行します。手動実行は Actions の `curate` → Run workflow です。
2. Secret `INOREADER_FEED_URL` のRSSを取得します。処理済み・重複（同じ元URL、ほぼ同じタイトル）を除きます。Googleアラートの中継URLは元記事のURLに変換します。
3. 初回は直近3日分だけが対象で、それより古い記事は処理済み扱いで取り込みません。
4. 1次選別: 25件ずつまとめてGeminiに渡し、分野・実践事例か・1〜5点を判定します。
5. 2次確認: しきい値以上の記事だけ本文を取得（10秒タイムアウト、失敗時はタイトルと要約で代用）し、日本語コメントを付けて再評価します。
6. 採用記事を `docs/feed.xml` に追加します（件数上限なし、60日で削除）。guidは元記事URLです。タイトルの先頭に分野マーク（📝MD運用 🪙トークン節約 📱アプリ開発 ⚙️DX自動化）が付きます。
7. `state/seen.json` と `docs/feed.xml` をワークフローがコミットします（変更がなければコミットしません）。

## 設定の変更
- `config/criteria.md`: 分野の定義、実践事例の条件、除外条件、点数の目安。文章を編集するだけで反映されます。
- `config/settings.json`: 数値設定（1行ずつの意味）。
  - `model`: 使うGeminiモデル名。
  - `stage1_batch_size`: 1次選別で1回のAPI呼び出しに渡す記事数。
  - `stage1_threshold`: 1次選別の通過しきい値（この点数以上が2次確認へ。既定3）。
  - `final_threshold`: 2次確認の採用しきい値（この点数以上をフィードに載せる。既定4）。
  - `first_run_days`: 初回実行で対象にする日数（それより古い記事は取り込まない）。
  - `feed_retention_days`: フィードに記事を残す日数（既定60）。
  - `seen_retention_days`: 処理済みの記録を残す日数。
  - `max_items_per_run`: 1回の実行で判定する記事数の上限。超えた分は翌日に回す。
  - `max_api_calls_per_run`: 1回の実行でのGemini呼び出し回数の上限。
  - `min_seconds_between_calls`: Gemini呼び出しの最小間隔（秒）。
  - `retry_wait_seconds` / `max_retries`: 上限エラー(429等)時の待ち秒数と再試行回数。
  - `fetch_*` / `body_max_chars`: 本文取得のタイムアウト・最大サイズ・Geminiに渡す最大文字数。
  - `feed_title` / `feed_description` / `feed_link`: フィードの表示情報。
  - `curation_link_param`: 新しく採用した記事の link・guid に付ける目印（既定 `via=curation`）。空にすると付けない。
  - `report_pubdate_offset_minutes`: 完了報告の pubDate を実行時刻から何分進めるか（既定1）。
  - `fetch_limit`: Inoreaderから1回に取得する最大件数（既定300。`INOREADER_FEED_URL` の `n` をこの値で上書きして使う。Inoreaderは300件を返すことを確認済み）。新規がこの件数に達した回は、完了報告に「新規300件（上限超）」と出て、取りこぼしの可能性を示す。
- 再評価: Actions の `curate` → Run workflow で「reevaluate_days」に日数（例 3）を入れると、処理済みを無視して直近N日分を現在の基準で判定し直し、`docs/feed.xml` を作り直します。呼び出し間隔と上限回数は通常どおりです。空欄なら通常実行です。
- 実行ログには、1次・2次それぞれの点数ごとの件数（5点／4点／3点以下）が出ます。点数の偏りの確認に使えます。
- Secrets: `INOREADER_FEED_URL`、`GEMINI_API_KEY`（リポジトリの Settings → Secrets and variables → Actions）。

## 注意点
- **Geminiの無料枠の上限**: 公式ドキュメントには無料枠のRPM・RPD数値がなく、Google AI Studio の Rate limit ページでのみ確認できます。既定モデルは公式一覧で無料と明記された安定版 `gemini-3.5-flash-lite` です。429等は待って3回まで再試行し、それでも失敗したらその日は中断します。未判定の記事は処理済みにせず翌日に回します。
- **課金**: 課金設定は行っていません。課金を有効にしないでください。無料枠の入力は製品改善に使われる場合があります（公式pricing）。
- **ログ・本文取得**: ログは件数の要約のみです。本文を取れない記事は、タイトルと要約からコメントを作ります。
- **定期実行の自動停止**: 公開リポジトリでは、60日間動きがないと定期実行が自動で無効になります。`state/seen.json` は通常毎日更新・コミットされるため止まりにくい設計ですが、ワークフロー自身（GITHUB_TOKEN）のコミットが「動き」に数えられるかは公式文書で確認できていません。無効化された場合は Actions タブで再度有効にしてください。
- Inoreaderの出力フィードURLには `?n=100` を付けています（件数指定。公式文書には記載がなく、動作確認のみ）。

## 調整履歴
- 2026-11-07：Inoreaderの重複フィルター（URLが同じ・比較期間1日）で選別フィードの記事が元記事の重複として消されていたため、新規採用記事の link・guid に `via=curation` を付け、完了報告の link に日本時間の実行日時（`?run=YYYY-MM-DDThhmm`）を付けるようにした（既存記事は変更なし）。
- 2026-11-07：Inoreaderで完了報告が同じ回の記事の間に入ってしまうため、完了報告の pubDate を実行時刻の1分後にして記事より上に出るようにした（記事の pubDate・既存の完了報告は変更なし）。
- 2026-11-07：取得上限を100件から300件（`fetch_limit`）に引き上げ。完了報告のタイトルに「新規N件」（上限に達したら「（上限超）」）、本文に取得・処理済み・新規・上限・スキップの件数を追加。上限を上げた初回に古い記事がまとめて配信されないよう、通常実行では処理済みの一番古い記事より古い未処理記事を判定せず処理済みにする（再評価モードでは行わない）。
