from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
import random
import statistics

@dataclass
class Status:
    name: str
    turns_left: int
    stacks: int = 1

@dataclass
class Skill:
    skill_id: str
    name: str
    slot: str          # unique / learn20 / awaken
    timing: str        # start / after_attack
    proc: float
    effects: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class Unit:
    unit_id: str
    name: str
    stats: Dict[str, float]      # str/int/lea/spd
    max_soldiers: int
    soldiers: int
    unique_skill: Skill
    learn20_skill: Optional[Skill] = None
    awaken_skill: Optional[Skill] = None
    statuses: Dict[str, Status] = field(default_factory=dict)

    def is_alive(self) -> bool:
        return self.soldiers > 0

    def has(self, status_name: str) -> bool:
        return status_name in self.statuses and self.statuses[status_name].turns_left > 0

    def add_status(self, name: str, turns: int, stacks: int = 1):
        if name in self.statuses:
            self.statuses[name].turns_left = max(self.statuses[name].turns_left, turns)
            self.statuses[name].stacks = min(self.statuses[name].stacks + stacks, 99)
        else:
            self.statuses[name] = Status(name=name, turns_left=turns, stacks=stacks)

    def tick_statuses_end_of_turn(self):
        for k in list(self.statuses.keys()):
            self.statuses[k].turns_left -= 1
            if self.statuses[k].turns_left <= 0:
                del self.statuses[k]

    def all_skills(self) -> List[Skill]:
        out = [self.unique_skill]
        if self.learn20_skill: out.append(self.learn20_skill)
        if self.awaken_skill: out.append(self.awaken_skill)
        return out

@dataclass
class BattleResult:
    winner: str
    turns: int
    a_loss_rate: float
    b_loss_rate: float
    triggers: Dict[str, int]

class Engine:
    def __init__(self, tuning: Dict[str, Any], seed: int):
        self.T = tuning
        self.rng = random.Random(seed)
        self.triggers: Dict[str, int] = {}

    def _alive(self, team: List[Unit]) -> List[Unit]:
        return [u for u in team if u.is_alive()]

    def _pick_enemy(self, enemy_team: List[Unit]) -> Optional[Unit]:
        alive = self._alive(enemy_team)
        return self.rng.choice(alive) if alive else None

    def _pick_allies_lowest(self, team: List[Unit], count: int) -> List[Unit]:
        alive = self._alive(team)
        alive.sort(key=lambda u: u.soldiers)
        return alive[:max(0, min(count, len(alive)))]

    def _record(self, sk: Skill):
        self.triggers[sk.name] = self.triggers.get(sk.name, 0) + 1

    # --- Tunable formulas ---
    def physical_damage(self, a: Unit, d: Unit, rate: float) -> int:
        atk_mix_lea = float(self.T.get("attack_mix_lea", 0.5))
        def_fac = float(self.T.get("defense_factor_physical", 0.7))
        scale = float(self.T.get("physical_scale", 20.0))
        atk = a.stats["str"] + atk_mix_lea * a.stats["lea"]
        df  = d.stats["lea"]
        base = max(0.0, atk - def_fac * df)
        troop_scale = (a.soldiers / a.max_soldiers) if a.max_soldiers else 1.0
        dmg = base * rate * scale * troop_scale
        dmg *= self.rng.uniform(float(self.T.get("random_min", 0.95)), float(self.T.get("random_max", 1.05)))
        return int(max(1, dmg))

    def strategy_damage(self, a: Unit, d: Unit, rate: float) -> int:
        def_fac = float(self.T.get("defense_factor_strategy", 0.8))
        scale = float(self.T.get("strategy_scale", 22.0))
        atk = a.stats["int"]
        df  = d.stats["int"]
        base = max(0.0, atk - def_fac * df)
        troop_scale = (a.soldiers / a.max_soldiers) if a.max_soldiers else 1.0
        dmg = base * rate * scale * troop_scale
        dmg *= self.rng.uniform(float(self.T.get("random_min", 0.95)), float(self.T.get("random_max", 1.05)))
        return int(max(1, dmg))

    def heal(self, h: Unit, t: Unit, rate: float) -> int:
        scale = float(self.T.get("heal_scale", 18.0))
        base = h.stats["int"] * rate * scale
        base *= self.rng.uniform(float(self.T.get("random_min", 0.95)), float(self.T.get("random_max", 1.05)))
        amt = int(max(1, base))
        t.soldiers = min(t.max_soldiers, t.soldiers + amt)
        return amt
    # ------------------------

    def _apply_effects(self, sk: Skill, self_u: Unit, enemy_u: Unit, team_self: List[Unit], team_enemy: List[Unit]):
        for eff in sk.effects or []:
            et = eff.get("type")
            if et == "physical_damage":
                dmg = self.physical_damage(self_u, enemy_u, float(eff.get("rate", 1.0)))
                enemy_u.soldiers = max(0, enemy_u.soldiers - dmg)
            elif et == "strategy_damage":
                dmg = self.strategy_damage(self_u, enemy_u, float(eff.get("rate", 1.0)))
                enemy_u.soldiers = max(0, enemy_u.soldiers - dmg)
            elif et == "heal":
                count = int(eff.get("count", 1))
                targets = self._pick_allies_lowest(team_self, count) if eff.get("target") == "ally_lowest" else [self_u]
                for t in targets:
                    self.heal(self_u, t, float(eff.get("rate", 1.0)))
            elif et == "status":
                if eff.get("name") == "confusion":
                    enemy_u.add_status("confusion", int(eff.get("turns", 1)))

    def run_battle(self, team_a: List[Unit], team_b: List[Unit]) -> BattleResult:
        max_turns = int(self.T.get("max_turns", 8))
        all_units = team_a + team_b
        a_initial = sum(u.soldiers for u in team_a)
        b_initial = sum(u.soldiers for u in team_b)

        for turn in range(1, max_turns + 1):
            if not self._alive(team_a):
                return self._final("B", turn-1, a_initial, b_initial, team_a, team_b)
            if not self._alive(team_b):
                return self._final("A", turn-1, a_initial, b_initial, team_a, team_b)

            order = sorted([u for u in all_units if u.is_alive()],
                           key=lambda u: (u.stats.get("spd", 0.0), self.rng.random()),
                           reverse=True)

            # start timing skills
            for u in order:
                if not u.is_alive(): continue
                if self.T.get("confusion_skip_action", True) and u.has("confusion"):
                    continue
                enemy_team = team_b if u in team_a else team_a
                target = self._pick_enemy(enemy_team)
                if not target: continue
                for sk in u.all_skills():
                    if sk.timing == "start" and self.rng.random() < sk.proc:
                        self._record(sk)
                        self._apply_effects(sk, u, target, team_a if u in team_a else team_b, enemy_team)

            # normal attack + after_attack
            for u in order:
                if not u.is_alive(): continue
                if self.T.get("confusion_skip_action", True) and u.has("confusion"):
                    continue
                enemy_team = team_b if u in team_a else team_a
                target = self._pick_enemy(enemy_team)
                if not target: continue

                dmg = self.physical_damage(u, target, 1.0)
                target.soldiers = max(0, target.soldiers - dmg)

                if target.is_alive():
                    for sk in u.all_skills():
                        if sk.timing == "after_attack" and self.rng.random() < sk.proc:
                            self._record(sk)
                            self._apply_effects(sk, u, target, team_a if u in team_a else team_b, enemy_team)

            for u in all_units:
                if u.is_alive():
                    u.tick_statuses_end_of_turn()

        return self._final("draw", max_turns, a_initial, b_initial, team_a, team_b)

    def _final(self, winner: str, turns: int, a_initial: int, b_initial: int, team_a: List[Unit], team_b: List[Unit]) -> BattleResult:
        a_now = sum(u.soldiers for u in team_a)
        b_now = sum(u.soldiers for u in team_b)
        a_loss = (a_initial - a_now) / a_initial if a_initial else 0.0
        b_loss = (b_initial - b_now) / b_initial if b_initial else 0.0
        return BattleResult(winner, turns, a_loss, b_loss, dict(self.triggers))

def simulate_many(build_once: Callable[[int], BattleResult], n: int, seed: int = 0) -> Dict[str, Any]:
    rng = random.Random(seed)
    wins = {"A": 0, "B": 0, "draw": 0}
    a_losses, b_losses = [], []
    trig: Dict[str, int] = {}

    for _ in range(n):
        res = build_once(rng.randint(0, 10**9))
        wins[res.winner] += 1
        a_losses.append(res.a_loss_rate)
        b_losses.append(res.b_loss_rate)
        for k,v in res.triggers.items():
            trig[k] = trig.get(k, 0) + v

    def stats(xs: List[float]) -> Dict[str, float]:
        return {
            "mean": float(statistics.mean(xs)) if xs else 0.0,
            "median": float(statistics.median(xs)) if xs else 0.0,
            "min": float(min(xs)) if xs else 0.0,
            "max": float(max(xs)) if xs else 0.0,
            "stdev": float(statistics.pstdev(xs)) if xs else 0.0,
        }

    trig_top = dict(sorted(trig.items(), key=lambda x: x[1], reverse=True)[:15])
    return {
        "n": n,
        "wins": wins,
        "win_rate_A": wins["A"]/n if n else 0.0,
        "win_rate_B": wins["B"]/n if n else 0.0,
        "draw_rate": wins["draw"]/n if n else 0.0,
        "loss_A": stats(a_losses),
        "loss_B": stats(b_losses),
        "skill_triggers_top": trig_top,
    }
