import json
import re
from pathlib import Path
from typing import Dict, Any, List

import requests
from bs4 import BeautifulSoup

# パス設定
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UNITS_PATH = DATA_DIR / "units.json"
SKILLS_PATH = DATA_DIR / "skills.json"


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def slug(text: str) -> str:
    """ID用に、安全な文字だけ残す（全部ASCIIにするのは難しいので、とりあえず記号だけ除去）"""
    return re.sub(r"[^\w]+", "_", text).strip("_")


def extract_name_from_html(html: str) -> str:
    """
    ページタイトルから「◯◯の評価と戦法」の ◯◯ を抜く
    例: 〖信長の野望 真戦〗織田信長の評価と戦法
    """
    # titleタグから取る
    m = re.search(r"信長の野望[^】]*】\s*([^の]+)の評価と戦法", html)
    if m:
        return m.group(1).strip()
    # ダメなら見出しテキストから
    m2 = re.search(r"〖信長の野望 真戦〗([^の]+)の評価と戦法", html)
    if m2:
        return m2.group(1).strip()
    return "不明武将"


def extract_stats_from_text(text: str) -> Dict[str, int]:
    """
    ページ全体のテキストから 武勇/知略/統率/速度 のLv50値を抜く
    Game8 の表: 「武勇 ... 161 知略 ... 175 統率 ... 231 速度 ... 110」
    """
    # 改行・余計な空白をまとめる
    t = re.sub(r"\s+", " ", text)

    m = re.search(
        r"武勇[^0-9]*([0-9]+)[^0-9]*知略[^0-9]*([0-9]+)[^0-9]*統率[^0-9]*([0-9]+)[^0-9]*速度[^0-9]*([0-9]+)",
        t
    )
    if not m:
        return {}

    return {
        "str": int(m.group(1)),
        "int": int(m.group(2)),
        "lea": int(m.group(3)),
        "spd": int(m.group(4)),
    }


def extract_unique_skill_name(text: str) -> str:
    """
    「固有戦法」の直後の行から戦法名を抜く（かなりざっくり）
    """
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if "固有戦法" in line:
            # 次の非空行を探す
            for j in range(i + 1, min(i + 8, len(lines))):
                cand = lines[j].strip()
                if not cand:
                    continue
                # 「適性兵種」などの行はスキップ
                if "適性兵種" in cand or "対象種別" in cand or "発動確率" in cand:
                    continue
                return cand
    return ""


def build_unique_skill_id(unique_name: str, skills: List[Dict[str, Any]]) -> str:
    """
    skills.json から名前で一致する戦法を探し、skill_id を返す。
    見つからなければ UNQ_◯◯ 形式の仮IDを作る。
    """
    if not unique_name:
        return ""

    # 完全一致優先
    for s in skills:
        if s.get("name") == unique_name:
            return s.get("skill_id", "")

    # 部分一致
    for s in skills:
        if unique_name in (s.get("name") or ""):
            return s.get("skill_id", "")

    # 見つからない場合は仮ID
    return f"UNQ_{slug(unique_name)}"


def fetch_unit_from_url(url: str, skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Game8 の武将ページURLから:
      - unit_id（= 名前そのもの）
      - name
      - base_stats: 武勇/知略/統率/速度 (Lv50)
      - max_soldiers: とりあえず10000に固定（必要ならあとで手動調整）
      - unique_skill_id: 固有戦法名から skills.json を引いてIDに変換
    を作る
    """
    print(f"\n=== 取得中: {url} ===")
    res = requests.get(url)
    res.raise_for_status()
    html = res.text

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    name = extract_name_from_html(html)
    stats = extract_stats_from_text(text)
    unique_name = extract_unique_skill_name(text)
    unique_skill_id = build_unique_skill_id(unique_name, skills)

    if not stats:
        print("  [!] ステータス(武勇/知略/統率/速度)が取れませんでした。あとで手動で入れてください。")

    unit_id = name  # 日本語IDでOK。必要なら手で U_NOBU などに変えても良い

    unit_obj = {
        "unit_id": unit_id,
        "name": name,
        "base_stats": stats or {"str": 0, "int": 0, "lea": 0, "spd": 0},
        "unique_skill_id": unique_skill_id,
        "max_soldiers": 10000,  # とりあえず固定。必要ならJSONを直接編集して調整。
    }

    print(f"  名称: {name}")
    if stats:
        print(f"  武勇:{stats['str']} 知略:{stats['int']} 統率:{stats['lea']} 速度:{stats['spd']}")
    print(f"  固有戦法名: {unique_name or '不明'}")
    print(f"  固有戦法ID: {unique_skill_id or '(未割り当て)'}")
    print("  unit_id:", unit_id)
    return unit_obj


def main():
    print("===== 真戦: Game8 武将ページURL → units.json 自動生成ツール =====")
    print("信長の野望 真戦の Game8『◯◯の評価と戦法』ページの URL を1行ずつ入力してください。")
    print("例:")
    print("  https://game8.jp/nobunaga-shinsen/747895   ← 織田信長")
    print("入力が終わったら Enter → Ctrl+Z → Enter で終了（Windows）")
    print("既存の units.json とマージ（unit_id が同じものは上書き）します。")
    print("--------------------------------------------------")

    skills = load_json(SKILLS_PATH, [])
    units_existing = load_json(UNITS_PATH, [])
    unit_map = {u["unit_id"]: u for u in units_existing if u.get("unit_id")}

    urls = []
    try:
        while True:
            line = input().strip()
            if not line:
                continue
            urls.append(line)
    except EOFError:
        pass

    added = 0
    for url in urls:
        try:
            unit_obj = fetch_unit_from_url(url, skills)
            unit_map[unit_obj["unit_id"]] = unit_obj
            added += 1
        except Exception as e:
            print(f"  [ERROR] {url} の処理中にエラー: {e}")

    units_new = sorted(unit_map.values(), key=lambda u: u["unit_id"])
    save_json(UNITS_PATH, units_new)

    print("--------------------------------------------------")
    print(f"{added} 件の武将を追加/更新しました。")
    print(f"合計 {len(units_new)} 件の武将が units.json に保存されています。")
    print(f"path: {UNITS_PATH}")


if __name__ == "__main__":
    main()
