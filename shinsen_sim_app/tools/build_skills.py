import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SKILLS_PATH = DATA_DIR / "skills.json"


def parse_skills(raw_text: str):
    skills = []

    # 1行ずつ読む
    lines = raw_text.splitlines()

    current = {}
    buffer = []

    def push_current():
        nonlocal current, buffer
        if current:
            current["effects_text"] = "\n".join(buffer).strip()
            skills.append(current)
        current = {}
        buffer = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 戦法名行の検出（例：火攻）
        if re.match(r"^[一-龠ぁ-んァ-ンA-Za-z0-9].*?（", line):
            push_current()
            skill_name = line.split("（")[0].strip()
            current = {
                "skill_id": f"S_{len(skills)+1:03}",
                "name": skill_name,
                "proc": 0.0,
                "slot": "learn20",
                "timing": "after_attack",
                "effects": []
            }
            continue

        # 発動率の抽出（例：発動率20%）
        m = re.search(r"発動率\s*([0-9]+)%", line)
        if m and current:
            current["proc"] = int(m.group(1)) / 100.0

        # 効果倍率の抽出（例：兵刃ダメージ200%）
        m2 = re.search(r"([兵刃計略]+)ダメージ\s*([0-9]+)%", line)
        if m2 and current:
            dmg_type = m2.group(1)
            rate = int(m2.group(2)) / 100.0
            current["effects"].append({
                "type": "physical" if dmg_type == "兵刃" else "strategy",
                "rate": rate
            })

        buffer.append(line)

    push_current()

    return skills


def main():
    print("===== 真戦: 戦法データ生成ツール =====")
    print("game8 戦法一覧ページのテキストを全部コピーして貼り付けてください。")
    print("入力終了後 Enter → Ctrl+Z → Enter（Windows）")

    raw_text = ""
    try:
        while True:
            line = input()
            raw_text += line + "\n"
    except EOFError:
        pass

    skills = parse_skills(raw_text)
    print(f"{len(skills)} 件の戦法を検出しました。")

    # JSON書き出し
    SKILLS_PATH.write_text(json.dumps(skills, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"skills.json に保存しました: {SKILLS_PATH}")


if __name__ == "__main__":
    main()
