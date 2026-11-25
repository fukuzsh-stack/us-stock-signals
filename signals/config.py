"""調整用の設定。数値を変えるだけでシグナルの厳しさを変えられます。"""
CFG = {
    "long_threshold": 80,      # 長期スコアがこれ以上で「長期買い候補」
    "short_threshold": 50,     # 短期スコアがこれ以上で「短期買いシグナル」
    "history_period": "2y",    # 株価の取得期間
    "fundamental_refresh_days": 7,  # 財務データの再取得間隔(日)
    "no_fundamental_penalty": 0.8,  # 財務データが取れない銘柄の割引率
    "top_n": 30,               # 画面に出す各ランキングの件数
}
