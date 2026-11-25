# 米国株シグナル

S&P500全銘柄+ウォッチリストを毎朝(日本時間7:30ごろ)自動で分析し、
**長期の買い候補**と**短期の買いシグナル**をスコア化してスマホ用ページに表示、新しいシグナルを ntfy で通知します。

> 機械的なスクリーニング結果であり、投資助言・売買の推奨ではありません。

## 仕組み
- GitHub Actions が毎朝 `python -m signals.main` を実行(無料枠内)
- 株価・財務データ: yfinance(Yahoo Finance)、銘柄リスト: Wikipedia
- 結果 `docs/data/signals.json` を GitHub Pages(`docs/index.html`)で表示
- `docs/data/history.json` に毎日のシグナルを蓄積(後で的中率を検証する用)

## スコア
| 種類 | 内訳 |
|---|---|
| 長期(100) | 長期トレンド50: 200日線より上12 / 50日線>200日線10 / 200日線上向き8 / 1年モメンタム10 / 押し目10<br>割安度・財務50: PER10 / PEG8 / ROE8 / 売上成長8 / 利益成長6 / 負債5 / 利益率5 |
| 短期(100) | RSI反発25 / MACDゴールデンクロス20 / ボリンジャー下限から回復20 / 出来高急増20 / 200日線より上15 |

しきい値は `signals/config.py`(長期80点・短期50点)。

## 使い方
- 銘柄を追加: `watchlist.txt` に1行1ティッカー
- 手動実行: Actions → daily-signals → Run workflow
- 通知: ntfy アプリで自分のトピック名を購読し、リポジトリの Settings → Secrets → Actions に `NTFY_TOPIC` を登録

## テスト
```
python -m tests.test_engine
```
