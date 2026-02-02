# 真戦 編成シミュ（ローカルアプリ / Streamlit）
Pythonで動く「編成ビルダー + 連戦シミュ」最小構成です。

- 最大8ターン / 途中決着あり
- 自軍/敵軍：武将3名
- 各武将：戦法スロット（固有/20Lv/覚醒）
- N回シミュして勝率・兵損率を集計

## セットアップ（Windows）
```powershell
cd shinsen_sim_app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 起動
```powershell
streamlit run app.py
```

## データ
- data/units.json … 武将（ステ/固有戦法ID）
- data/skills.json … 戦法（発動率proc、効果effects）
- data/tuning.json … ダメージ・回復の「つまみ」

## import_game8_min.py
Game8から「名前/対象/発動率/分類」など数値寄りの情報を取得してjsonに保存する補助スクリプト（長文説明は保存しません）。
