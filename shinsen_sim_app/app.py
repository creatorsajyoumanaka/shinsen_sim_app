import json
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from engine import Engine, Unit, Skill, simulate_many

# ---------- パス設定 ----------
DATA_DIR = Path(__file__).parent / "data"
TUNING_PATH = DATA_DIR / "tuning.json"
UNITS_PATH = DATA_DIR / "units.json"
SKILLS_PATH = DATA_DIR / "skills.json"
PRESETS_PATH = DATA_DIR / "presets.json"

st.set_page_config(page_title="真戦 編成シミュ（改良版）", layout="wide")


# ---------- 共通関数 ----------
def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    return copy.deepcopy(default)


def save_json(path: Path, obj: Any):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def to_skill(obj: Dict[str, Any]) -> Skill:
    return Skill(
        skill_id=obj.get("skill_id", ""),
        name=obj.get("name", ""),
        slot=obj.get("slot", "learn20"),
        timing=obj.get("timing", "after_attack"),
        proc=float(obj.get("proc", 0.0) or 0.0),
        effects=obj.get("effects") or [],
    )


def build_skill_map(skills: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["skill_id"]: s for s in skills if s.get("skill_id")}


def build_unit_map(units: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {u["unit_id"]: u for u in units if u.get("unit_id")}


def make_unit(
    unit_data: Dict[str, Any],
    skill_map: Dict[str, Dict[str, Any]],
    soldiers: int,
    learn20_id: Optional[str],
    awaken_id: Optional[str],
) -> Unit:
    base = unit_data.get("base_stats", {})
    unique_id = unit_data.get("unique_skill_id")

    if unique_id in skill_map:
        unique_raw = skill_map[unique_id]
    else:
        unique_raw = {
            "skill_id": unique_id or "",
            "name": unit_data.get("name", ""),
            "slot": "unique",
            "timing": "after_attack",
            "proc": 0.0,
            "effects": [],
        }

    unique_skill = to_skill(unique_raw)
    learn20_skill = to_skill(skill_map[learn20_id]) if learn20_id else None
    awaken_skill = to_skill(skill_map[awaken_id]) if awaken_id else None

    max_soldiers = int(unit_data.get("max_soldiers", 10000))
    soldiers = int(max(0, min(max_soldiers, soldiers)))

    return Unit(
        unit_id=unit_data["unit_id"],
        name=unit_data["name"],
        stats={
            "str": float(base.get("str", 0)),
            "int": float(base.get("int", 0)),
            "lea": float(base.get("lea", 0)),
            "spd": float(base.get("spd", 0)),
        },
        max_soldiers=max_soldiers,
        soldiers=soldiers,
        unique_skill=unique_skill,
        learn20_skill=learn20_skill,
        awaken_skill=awaken_skill,
    )


# ---------- データ読み込み ----------
tuning = load_json(TUNING_PATH, {})
units_list = load_json(UNITS_PATH, [])
skills_list = load_json(SKILLS_PATH, [])
presets = load_json(PRESETS_PATH, {})

unit_map = build_unit_map(units_list)
skill_map = build_skill_map(skills_list)

all_unit_ids = list(unit_map.keys())
all_skill_ids = [s["skill_id"] for s in skills_list if s.get("skill_id")]

# learn20 / 覚醒 はいったん「全戦法から自由に選べる」
learn20_ids = all_skill_ids
awaken_ids = all_skill_ids


def skill_display_label(s: Dict[str, Any]) -> str:
    """UIに出す名前。display_name > name > skill_id の優先度。"""
    base = s.get("display_name") or s.get("name") or s.get("skill_id", "")
    return f"{base} ({s.get('skill_id','')})"


skill_choices = {
    s["skill_id"]: skill_display_label(s)
    for s in skills_list
    if s.get("skill_id")
}

st.title("真戦 編成シミュ（戦法表示名＋プリセット対応版）")
st.caption("・戦法の表示名を編集可能 / 自軍Aのプリセット保存・読み込み対応")


# ---------- サイドバー：tuning ----------
with st.sidebar:
    st.header("シミュ設定")
    n_runs = st.number_input("検証回数 N", min_value=1, max_value=100000, value=500, step=100)
    seed = st.number_input("乱数シード", min_value=0, value=123, step=1)

    st.subheader("tuning.json（調整用）")
    tuning_text = st.text_area(
        "編集（上級者向け）",
        value=json.dumps(tuning, ensure_ascii=False, indent=2),
        height=260,
    )
    if st.button("tuning 保存"):
        try:
            tuning = json.loads(tuning_text)
            save_json(TUNING_PATH, tuning)
            st.success("tuning.json を保存しました")
        except Exception as e:
            st.error(f"JSON形式が壊れています: {e}")


# ---------- 編成 ----------
def team_picker(prefix: str, default_ids: List[str]):
    st.subheader(f"{prefix} 編成")
    picked = []
    for i in range(3):
        default_id = default_ids[i] if i < len(default_ids) else (all_unit_ids[0] if all_unit_ids else "")
        uid = st.selectbox(
            f"{prefix} 武将{i+1}",
            all_unit_ids,
            index=all_unit_ids.index(default_id) if default_id in all_unit_ids else 0,
            key=f"{prefix}_unit_{i}",
        )
        u = unit_map[uid]
        max_sold = int(u.get("max_soldiers", 10000))
        soldiers = st.slider(
            f"{prefix} 武将{i+1} 兵数",
            min_value=1000, max_value=max_sold,
            value=max_sold,
            step=500,
            key=f"{prefix}_sold_{i}",
        )
        picked.append((uid, soldiers))
    return picked


colA, colB = st.columns(2)
with colA:
    defaults_A = all_unit_ids[:3] if len(all_unit_ids) >= 3 else all_unit_ids
    picked_A = team_picker("A(自軍)", defaults_A)
with colB:
    defaults_B = all_unit_ids[3:6] if len(all_unit_ids) >= 6 else all_unit_ids
    picked_B = team_picker("B(敵軍)", defaults_B)

st.divider()


# ---------- 戦法設定 ----------
def team_skills(prefix: str, picked):
    st.subheader(f"{prefix} 戦法設定")
    results = []
    for i, (uid, soldiers) in enumerate(picked):
        u = unit_map[uid]
        st.markdown(f"**{prefix}{i+1}: {u['name']}**")

        unique_id = u.get("unique_skill_id")
        unique_name = skill_map.get(unique_id, {}).get("name", unique_id)
        st.caption(f"固有戦法: {unique_name}")

        l20_view = ["(なし)"] + [skill_choices[x] for x in learn20_ids]
        awk_view = ["(なし)"] + [skill_choices[x] for x in awaken_ids]

        l20_sel = st.selectbox("20レベ戦法", l20_view, index=0, key=f"{prefix}_l20_{i}")
        awk_sel = st.selectbox("覚醒戦法", awk_view, index=0, key=f"{prefix}_awk_{i}")

        def decode(v: str) -> Optional[str]:
            if v == "(なし)":
                return None
            # "... (SKILL_ID)" から ID 部分だけ抜く
            m_start = v.rfind("(")
            m_end = v.rfind(")")
            if m_start != -1 and m_end != -1 and m_end > m_start:
                return v[m_start + 1:m_end]
            return None

        results.append((uid, soldiers, decode(l20_sel), decode(awk_sel)))

    return results


colA2, colB2 = st.columns(2)
with colA2:
    slots_A = team_skills("A", picked_A)
with colB2:
    slots_B = team_skills("B", picked_B)

st.divider()


# ---------- ④ 戦法表示名 編集 ----------
st.header("④ 戦法の表示名（ラベル）編集")

if all_skill_ids:
    edit_id = st.selectbox("表示名を編集する戦法", sorted(all_skill_ids), key="edit_skill_id")
    target = next((s for s in skills_list if s.get("skill_id") == edit_id), None)

    if target:
        current_label = target.get("display_name") or target.get("name") or edit_id
        st.write(f"skill_id: `{edit_id}`")
        new_label = st.text_input("表示名（UIに出したい名前）", value=current_label, key="edit_skill_label")

if st.button("この戦法の表示名を保存"):
    for s in skills_list:
        if s.get("skill_id") == edit_id:
            s["display_name"] = new_label
            break
    save_json(SKILLS_PATH, skills_list)
    st.success("skills.json に保存しました。再読み込みして反映されます。")
    st.rerun()
else:
    st.info("skills.json に戦法がありません。")

st.divider()

# ---------- 既存の戦法数値 編集（proc / rate） ----------
st.header("戦法データ（proc / rate の簡易編集）")

if all_skill_ids:
    edit_id2 = st.selectbox("数値を編集する戦法ID", all_skill_ids, index=0, key="edit_skill_id2")
    s2 = copy.deepcopy(skill_map[edit_id2])
    st.write(f"名前: {s2.get('name','')} / 表示名: {s2.get('display_name', s2.get('name',''))}")

    proc_val = st.slider(
        "発動率 proc (0〜1)",
        min_value=0.0, max_value=1.0,
        value=float(s2.get("proc", 0.0)),
        step=0.01,
    )

    rate_val = None
    if s2.get("effects") and isinstance(s2["effects"], list) and s2["effects"] and isinstance(s2["effects"][0], dict):
        if "rate" in s2["effects"][0]:
            rate_val = s2["effects"][0]["rate"]
            rate_val = st.slider(
                "倍率 rate (effects[0].rate)",
                min_value=0.1, max_value=3.0,
                value=float(rate_val),
                step=0.01,
            )

    if st.button("この戦法の数値を保存"):
        s2["proc"] = proc_val
        if rate_val is not None:
            s2["effects"][0]["rate"] = rate_val

        for idx, ss in enumerate(skills_list):
            if ss.get("skill_id") == edit_id2:
                skills_list[idx] = s2
                break

        save_json(SKILLS_PATH, skills_list)
        st.success("data/skills.json に保存しました")


st.divider()


# ---------- ⑤ 編成プリセット（自軍A） ----------
st.header("⑤ 編成プリセット（自軍Aのみ）")

colP1, colP2 = st.columns(2)

with colP1:
    preset_name = st.text_input("新しく保存するプリセット名", key="preset_name")
    if st.button("この A 編成をプリセット保存"):
        if not preset_name:
            st.error("プリセット名を入力してください")
        else:
            presets[preset_name] = {
                "A": [
                    {
                        "unit_id": uid,
                        "soldiers": soldiers,
                        "learn20": l20_id,
                        "awaken": awk_id,
                    }
                    for (uid, soldiers, l20_id, awk_id) in slots_A
                ]
            }
            save_json(PRESETS_PATH, presets)
            st.success(f"プリセット '{preset_name}' を保存しました")

with colP2:
    preset_options = ["(選択なし)"] + sorted(presets.keys())
    load_choice = st.selectbox("読み込むプリセットを選択", preset_options, key="preset_select")
    if st.button("選択したプリセットを A に読み込み"):
        if load_choice == "(選択なし)":
            st.error("プリセットを選択してください")
        else:
            data = presets.get(load_choice, {}).get("A", [])
            for i, entry in enumerate(data):
                if i >= 3:
                    break
                uid = entry.get("unit_id")
                soldiers = entry.get("soldiers", 10000)
                l20_id = entry.get("learn20")
                awk_id = entry.get("awaken")

                st.session_state[f"A_unit_{i}"] = uid
                st.session_state[f"A_sold_{i}"] = soldiers

                # 戦法セレクト用のラベルに変換
                st.session_state[f"A_l20_{i}"] = (
                    skill_choices.get(l20_id, "(なし)") if l20_id else "(なし)"
                )
                st.session_state[f"A_awk_{i}"] = (
                    skill_choices.get(awk_id, "(なし)") if awk_id else "(なし)"
                )

            st.success(f"プリセット '{load_choice}' を読み込みました")
            st.experimental_rerun()


st.divider()


# ---------- シミュレーション実行 ----------
st.header("連戦シミュレーション")


def build_once(seed_val: int):
    eng = Engine(tuning, seed=seed_val)

    def make_team(slots):
        team = []
        for uid, soldiers, l20_id, awk_id in slots:
            ud = unit_map[uid]
            team.append(make_unit(ud, skill_map, soldiers, l20_id, awk_id))
        return team

    team_a = make_team(slots_A)
    team_b = make_team(slots_B)
    return eng.run_battle(team_a, team_b)


if st.button("実行（N回）"):
    with st.spinner("計算中..."):
        res = simulate_many(build_once, n=int(n_runs), seed=int(seed))

    st.subheader("勝率・兵損率")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("検証回数", res["n"])
    c2.metric("勝率 A", pct(res["win_rate_A"]))
    c3.metric("勝率 B", pct(res["win_rate_B"]))
    c4.metric("引き分け", pct(res["draw_rate"]))
    c5.metric("平均兵損 A", pct(res["loss_A"]["mean"]))
    c6.metric("平均兵損 B", pct(res["loss_B"]["mean"]))

    st.subheader("兵損統計")
    st.write("A:", res["loss_A"])
    st.write("B:", res["loss_B"])

    st.subheader("戦法発動回数（上位）")
    for name, count in res.get("skill_triggers_top", {}).items():
        st.write(f"{name}: {count}回")
