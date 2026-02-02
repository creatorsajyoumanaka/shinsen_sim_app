import json
from pathlib import Path

# data/units.json を作る／更新する簡易ツール
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UNITS_PATH = DATA_DIR / "units.json"


def load_units():
    if UNITS_PATH.exists():
        return json.loads(UNITS_PATH.read_text(encoding="utf-8"))
    return []


def save_units(units):
    UNITS_PATH.write_text(
        json.dumps(units, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    print("===== 真戦: 武将データ生成ツール =====")
    print("1行に1武将、カンマ区切りで入力してください。")
    print("形式:")
    print("  unit_id,名前,武勇,知略,統率,速度,最大兵数,固有戦法ID")
    print("例:")
    print("  U_NOBU,織田信長,95,90,92,85,10000,S_UNQ_NOBU")
    print("")
    print("入力が終わったら Enter → Ctrl+Z → Enter で終了（Windows）")
    print("既存の units.json とマージ（同じ unit_id は上書き）します。")
    print("--------------------------------------------------")

    existing = load_units()
    unit_map = {u["unit_id"]: u for u in existing if u.get("unit_id")}

    raw_lines = []
    try:
        while True:
            line = input()
            raw_lines.append(line)
    except EOFError:
        pass

    added = 0
    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            print(f"スキップ（列数不足）: {line}")
            continue

        unit_id = parts[0]
        name = parts[1]
        try:
            str_v = float(parts[2])
            int_v = float(parts[3])
            lea_v = float(parts[4])
            spd_v = float(parts[5])
            max_soldiers = int(parts[6])
        except ValueError:
            print(f"数値変換エラー: {line}")
            continue

        unique_skill_id = parts[7] if len(parts) >= 8 and parts[7] else ""

        unit_obj = {
            "unit_id": unit_id,
            "name": name,
            "base_stats": {
                "str": str_v,
                "int": int_v,
                "lea": lea_v,
                "spd": spd_v,
            },
            "unique_skill_id": unique_skill_id,
            "max_soldiers": max_soldiers,
        }

        unit_map[unit_id] = unit_obj
        added += 1

    units = sorted(unit_map.values(), key=lambda u: u["unit_id"])
    save_units(units)

    print("--------------------------------------------------")
    print(f"{added} 件の武将を追加/更新しました。")
    print(f"合計 {len(units)} 件の武将が units.json に保存されています。")
    print(f"path: {UNITS_PATH}")


if __name__ == "__main__":
    main()
