import json
import re
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

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


def extract_name_from_html(html: str) -> str:
    """
    ページタイトルなどから「◯◯の評価と戦法」の ◯◯ 部分を抜く
    ある程度ゆるくマッチさせる
    """
    # title タグ優先
    m = re.search(r"信長の野望[^】]*】\s*([^の]+)の評価と戦法", html)
    if m:
        return m.group(1).strip()

    m2 = re.search(r"〖信長の野望 真戦〗([^の]+)の評価と戦法", html)
    if m2:
        return m2.group(1).strip()

    return "不明武将"


def extract_unique_skill_block(text: str) -> str:
    """
    ページ全体テキストから「固有戦法」付近だけを切り出す
    （発動率やダメージ倍率がこの近くにある想定）
    """
    idx = text.find("固有戦法")
    if idx == -1:
        return text  # 見つからない場合は全体で妥協
    # 固有戦法から先の 800 文字くらいを切り出す（適当だが実用には十分）
    return text[idx: idx + 800]


def parse_unique_skill_name(text: str) -> str:
    """
    「固有戦法」の次あたりの行から戦法名を推定
    """
    lines = [l.strip() for l in text.splitlines()]
    name = ""
    for i, line in enumerate(lines):
        if "固有戦法" in line:
            # 次の非空行を戦法名候補にする
            for j in range(i + 1, min(i + 6, len(lines))):
                cand = lines[j].strip()
                if not cand:
                    continue
                # それっぽくない行をざっくりスキップ
                if "適性" in cand or "対象" in cand or "発動率" in cand:
                    continue
                name = cand
                break
            break
    return name


def parse_unique_skill_params(block: str) -> Dict[str, Any]:
    """
    固有戦法ブロックから発動率やダメージ倍率を推定
    見つからなければそこそこ妥当なデフォルトを入れる
    """
    # 余計な空白をまとめる
    t = re.sub(r"\s+", " ", block)

    # 発動率 XX%
    m_proc = re.search(r"発動率\s*([0-9]+)%", t)
    if m_proc:
        proc = int(m_proc.group(1)) / 100.0
    else:
        proc = 0.30  # デフォルト 30%

    # ダメージ倍率
    dmg_type = None
    rate = None

    m_dmg = re.search(r"(兵刃|計略)ダメージ\s*([0-9]+)%", t)
    if m_dmg:
        dmg_type = "physical" if m_dmg.group(1) == "兵刃" else "strategy"
        rate = int(m_dmg.group(2)) / 100.0

    effects: List[Dict[str, Any]] = []
    if dmg_type and rate:
        effects.append({
            "type": dmg_type,
            "rate": rate,
        })

    return {
        "proc": proc,
        "effects": effects,
    }


def fetch_page(url: str) -> BeautifulSoup:
    res = requests.get(url)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def ensure_unique_skill(
    unit_name: str,
    skills: List[Dict[str, Any]],
    units_map: Dict[str, Dict[str, Any]],
    url: str,
):
    """
    1URL(=1武将ページ) から固有戦法を取得し:
      - skills.json にスキルを追加/更新
      - units.json の該当武将の unique_skill_id をそのIDに設定
    """
    print(f"\n=== 取得中: {url} ===")

    soup = fetch_page(url)
    html = str(soup)
    text = soup.get_text("\n", strip=True)

    # まず武将名をページから確認（unit_name が空ならここから使う）
    page_name = extract_name_from_html(html)
    if not unit_name or unit_name == "不明武将":
        unit_name = page_name

    if unit_name not in units_map:
        print(f"  [!] units.json に '{unit_name}' が見つかりません。スキップします。")
        return

    unit_obj = units_map[unit_name]

    block = extract_unique_skill_block(text)
    skill_name = parse_unique_skill_name(block)
    params = parse_unique_skill_params(block)

    if not skill_name:
        print(f"  [!] 固有戦法名が取得できませんでした。武将: {unit_name}")
        return

    # すでに同名スキルが skills.json にあるか？
    skills_map_by_name = {s.get("name"): s for s in skills if s.get("name")}
    skills_map_by_id = {s.get("skill_id"): s for s in skills if s.get("skill_id")}

    if skill_name in skills_map_by_name:
        skill_id = skills_map_by_name[skill_name]["skill_id"]
        skill_obj = skills_map_by_name[skill_name]
        print(f"  既存のスキルを更新: {skill_name} (id={skill_id})")
    else:
        # ユニットがすでに何か unique_skill_id を持っていればそれを尊重
        current_id = unit_obj.get("unique_skill_id") or ""
        if current_id:
            skill_id = current_id
        else:
            # 新しいIDを振る (UNQ001, UNQ002, ...)
            existing_ids = [s.get("skill_id", "") for s in skills]
            base = "UNQ"
            n = 1
            while True:
                cand = f"{base}{n:03}"
                if cand not in existing_ids:
                    skill_id = cand
                    break
                n += 1
        print(f"  新規スキルを追加: {skill_name} (id={skill_id})")
        skill_obj = {
            "skill_id": skill_id,
            "name": skill_name,
        }

    # 内容を上書き/設定
    skill_obj["slot"] = "unique"
    skill_obj["timing"] = "after_attack"
    skill_obj["proc"] = params["proc"]
    skill_obj["effects"] = params["effects"]

    # skills 配列に反映（存在していれば置き換え、なければ追加）
    replaced = False
    for i, s in enumerate(skills):
        if s.get("skill_id") == skill_obj["skill_id"]:
            skills[i] = skill_obj
            replaced = True
            break
    if not replaced:
        skills.append(skill_obj)

    # unit 側の unique_skill_id を更新
    unit_obj["unique_skill_id"] = skill_obj["skill_id"]
    units_map[unit_name] = unit_obj

    print(f"  武将名: {unit_name}")
    print(f"  固有戦法名: {skill_name}")
    print(f"  発動率: {params['proc']*100:.1f}%")
    if params["effects"]:
        e0 = params["effects"][0]
        print(f"  ダメージ: 種類={e0['type']} 倍率={e0['rate']}")
    else:
        print("  ダメージ効果は自動検出できませんでした（バフ系か、解析漏れの可能性）。")


def main():
    print("===== 真戦: Game8 武将ページURL → 固有戦法を skills.json に自動登録ツール =====")
    print("◆ 使い方")
    print(" 1) すでに build_units_from_url.py で星5武将などを units.json に登録している前提です。")
    print(" 2) Game8 の『◯◯の評価と戦法』ページの URL を1行ずつ入力してください。")
    print(" 3) 入力が終わったら → Enter → Ctrl+Z → Enter で実行開始（Windows）。")
    print(" 4) 対象の武将の固有戦法が skills.json に追加/更新され、")
    print("    同時に units.json の unique_skill_id もそのIDに揃えられます。")
    print("--------------------------------------------------")

    units = load_json(UNITS_PATH, [])
    skills = load_json(SKILLS_PATH, [])

    units_map = {u.get("name"): u for u in units if u.get("name")}
    urls: List[str] = []

    try:
        while True:
            line = input().strip()
            if not line:
                continue
            urls.append(line)
    except EOFError:
        pass

    if not urls:
        print("URL が1つも入力されませんでした。終了します。")
        return

    for url in urls:
        try:
            # unit_name はここでは空で渡して、ページ側から推定する
            ensure_unique_skill("", skills, units_map, url)
        except Exception as e:
            print(f"[ERROR] {url} の処理中にエラーが発生しました: {e}")

    # 反映結果を保存
    units_new = sorted(units_map.values(), key=lambda u: u.get("unit_id", ""))
    save_json(UNITS_PATH, units_new)
    save_json(SKILLS_PATH, skills)

    print("--------------------------------------------------")
    print(f"{len(urls)} 件のURLについて固有戦法の登録/更新処理を行いました。")
    print(f"units.json / skills.json を更新しました。")
    print(f"units: {UNITS_PATH}")
    print(f"skills: {SKILLS_PATH}")


if __name__ == "__main__":
    main()
