"""Bounded game state and authoritative mechanics, embedded in Dify Code nodes."""
import json
import random
import re

# Replaced by the builder; local tests load the same source material.
MODULE = None
APPROACHES = ["谨慎", "机智", "华丽", "强势", "迅捷", "隐秘"]
ROLES = {
    "调查员": {"scores": [3, 2, 1, 0, 1, 2], "aspect": "总能注意到被忽略的细节"},
    "水手": {"scores": [1, 1, 0, 3, 2, 2], "aspect": "在风浪里讨生活的人"},
    "技师": {"scores": [2, 3, 1, 2, 1, 0], "aspect": "机器总会留下原因"},
}
KINDS = ["move", "investigate", "talk", "overcome", "attack", "defend", "advantage", "finale", "meta", "invalid"]
RULES = "本团采用 Fate Accelerated 的轻量改编。四枚骰子各取 -1/0/+1，加上行动方式分值，与难度比较：低于难度失败，相等为付出代价的成功，高出 1–2 成功，高出 3 及以上大成功。必要线索即使检定失败也会获得，但潮水加速。每三个有效行动潮水推进一格，失败或平手再推进一格；到 8 格触发撤离结局。压力到 3 的角色退出冒险，全员退出触发休整结局。命运点初始 3，明确填写 invoke=是并说明如何调用角色特质才可花 1 点获得 +2。创造优势成功获得一次 +2，下一次检定自动消耗。移动通常不掷骰，潮水达到 6 时需要检定。结束调查须到灯塔：校准需要名单与线路图，切断需要线路图，救人需要塔顶求救线索。攻击按一次危险行动结算，没有完整战术战斗。不会自动控制玩家角色。输入‘规则’或‘回顾’不消耗回合。"


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def text(value, limit=160):
    if not isinstance(value, str):
        raise ValueError("文本字段格式不正确")
    return value.strip()[:limit]


def initial_state(party):
    entries = [s.strip() for s in re.split(r"[;；\n]", party or "沈砚:调查员") if s.strip()]
    if not 1 <= len(entries) <= 3:
        raise ValueError("队伍请填写 1–3 人，格式：沈砚:调查员;林汐:技师")
    players = []
    for entry in entries:
        parts = re.split(r"[:：]", entry)
        if len(parts) != 2 or parts[1].strip() not in ROLES:
            raise ValueError("职业可选：调查员、水手、技师；格式：姓名:职业")
        name, role = text(parts[0], 16), parts[1].strip()
        if not name or any(p["name"] == name for p in players):
            raise ValueError("角色名不能为空或重复")
        players.append({"name": name, "role": role, "stress": 0, "fate": 3, "boost": 0})
    return {"schema": 1, "campaign": MODULE["id"], "scene": "dock", "turn": 0,
            "clock": 0, "players": players, "clues": [], "history": [], "ending": ""}


def validate_state(raw):
    if len(raw) > 16000:
        raise ValueError("存档超过长度限制")
    try:
        s = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("存档不是有效 JSON，请完整复制 session 输出")
    if not isinstance(s, dict) or s.get("schema") != 1 or s.get("campaign") != MODULE["id"]:
        raise ValueError("存档版本或剧本不匹配")
    if s.get("scene") not in MODULE["scenes"] or s.get("ending") not in ["", *MODULE["endings"]]:
        raise ValueError("存档地点或结局无效")
    for key, maximum in [("turn", 9999), ("clock", 8)]:
        if type(s.get(key)) is not int or not 0 <= s[key] <= maximum:
            raise ValueError("存档回合或潮水无效")
    if not isinstance(s.get("clues"), list) or len(s["clues"]) > 5 or any(c not in MODULE["clues"] for c in s["clues"]) or len(set(s["clues"])) != len(s["clues"]):
        raise ValueError("存档线索无效")
    if not isinstance(s.get("players"), list) or not 1 <= len(s["players"]) <= 3:
        raise ValueError("存档队伍无效")
    names, players = [], []
    for p in s["players"]:
        if not isinstance(p, dict) or p.get("role") not in ROLES:
            raise ValueError("存档职业无效")
        name = text(p.get("name"), 16)
        if not name or name in names:
            raise ValueError("存档角色名无效")
        names.append(name)
        clean = {"name": name, "role": p["role"]}
        for key, maximum in [("stress", 3), ("fate", 3), ("boost", 2)]:
            if type(p.get(key)) is not int or not 0 <= p[key] <= maximum:
                raise ValueError("存档角色数值无效")
            clean[key] = p[key]
        players.append(clean)
    if not isinstance(s.get("history"), list) or len(s["history"]) > 10:
        raise ValueError("存档历史无效")
    history = [{"action": text(h.get("action"), 120), "event": text(h.get("event"), 200)}
               for h in s["history"] if isinstance(h, dict)]
    return {"schema": 1, "campaign": MODULE["id"], "scene": s["scene"], "turn": s["turn"],
            "clock": s["clock"], "players": players, "clues": s["clues"], "history": history, "ending": s["ending"]}


def prepare(action, session="", party="", actor="", invoke="否"):
    action = text(action, 1200)
    if not action:
        raise ValueError("请填写行动，首次输入‘开团’")
    state = validate_state(session.strip()) if session and session.strip() else initial_state(party)
    operation = "play" if session and session.strip() else "open"
    if action in ["规则", "帮助", "help"]:
        operation = "rules"
    elif action in ["回顾", "状态", "存档"]:
        operation = "recap"
    elif state["ending"]:
        operation = "ended"
    elif operation == "play" and action in ["开团", "开始", "重新开始"]:
        operation = "recap"
    actor = text(actor or state["players"][0]["name"], 16)
    if actor not in [p["name"] for p in state["players"]]:
        raise ValueError("行动角色不在队伍中")
    scene = MODULE["scenes"][state["scene"]]
    context = {"operation": operation, "action": action, "actor": actor, "invoke": invoke == "是",
               "scene_id": state["scene"], "scene": scene,
               "known_clues": state["clues"], "clock": state["clock"],
               "players": state["players"], "history": state["history"][-4:],
               "destinations": {k: v["name"] for k, v in MODULE["scenes"].items()},
               "approaches": APPROACHES}
    # No hidden truth or undiscovered clue text goes to either LLM.
    return {"state": dumps(state), "context": dumps(context), "operation": operation,
            "action": action, "actor": actor, "invoke": "是" if invoke == "是" else "否"}


def parse_intent(raw):
    try:
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean).strip()
        obj = json.loads(clean)
        if not isinstance(obj, dict) or obj.get("kind") not in KINDS or obj.get("approach") not in APPROACHES:
            raise ValueError()
        return {"kind": obj["kind"], "approach": obj["approach"],
                "target": text(obj.get("target", ""), 32),
                "invoke_reason": text(obj.get("invoke_reason", ""), 80)}
    except (ValueError, TypeError, AttributeError):
        return {"kind": "invalid", "approach": "谨慎", "target": "", "invoke_reason": ""}


def choices_for(state):
    if state["ending"]:
        return ["回顾", "规则", "留空存档开启新团"]
    scene = MODULE["scenes"][state["scene"]]
    choices = []
    if scene["clue"] not in state["clues"]:
        choices.append(scene["investigate"])
    if state["scene"] == "lighthouse":
        for target, required, label in [
            ("restore", {"manifest", "diagram"}, "用完整名单校准共鸣装置"),
            ("seal", {"diagram"}, "切断主铜线，停止潮汐"),
            ("rescue", {"signal"}, "操作绞盘救出许照并组织撤离"),
        ]:
            if required <= set(state["clues"]):
                choices.append(label)
    for neighbor in scene["neighbors"]:
        choices.append("前往" + MODULE["scenes"][neighbor]["name"])
    choices.append(scene["talk"])
    return choices[:3]


def resolve(state, intent, operation, action, actor, invoke="否"):
    s = validate_state(state)
    p = next(p for p in s["players"] if p["name"] == actor)
    scene = MODULE["scenes"][s["scene"]]
    plan = parse_intent(intent)
    event = {"kind": operation, "message": "", "roll": None, "new_clues": [], "costs": []}
    active = operation == "play" and not s["ending"]
    if operation == "open":
        event["message"] = MODULE["opening"]
    elif operation == "rules":
        event["message"] = RULES
    elif operation == "recap":
        event["message"] = "回顾已发现的线索和最近行动，不推进时间。"
    elif operation == "ended" or s["ending"]:
        event["message"] = MODULE["endings"].get(s["ending"], "本团已结束。")
        active = False
    elif p["stress"] >= 3:
        event["message"] = actor + "已退出冒险，请换一位未退出的角色。"
        active = False
    elif plan["kind"] in ["invalid", "meta"]:
        event["message"] = "请描述一个当前场景中的具体行动；规则和回顾可单独输入。"
        active = False
    kind, target = plan["kind"], plan["target"]
    event["intent"] = {"kind": kind, "approach": plan["approach"], "target": target}
    if active and kind == "move" and target not in scene["neighbors"]:
        event["message"] = "无法直接到达该地点，请从当前可去的地点选择。"
        active = False
    requirements = {"restore": {"manifest", "diagram"}, "seal": {"diagram"}, "rescue": {"signal"}}
    if active and kind == "finale" and (s["scene"] != "lighthouse" or target not in requirements or not requirements[target] <= set(s["clues"])):
        event["message"] = "还无法进行这项终局行动：需要到达灯塔，并找到相应的线索。"
        active = False
    if active and kind in ["investigate", "talk"] and scene["clue"] in s["clues"]:
        event["message"] = "这里的核心线索已记录。可以追问细节，或前往其他地点。"
        active = False
    if active:
        difficulty = {"move": 2 if s["clock"] >= 6 else 0, "investigate": MODULE["clues"][scene["clue"]]["difficulty"],
                      "talk": MODULE["clues"][scene["clue"]]["difficulty"], "overcome": 2, "attack": 3,
                      "defend": 2, "advantage": 2, "finale": 3 if target == "restore" else 2}[kind]
        outcome, margin = "automatic", 0
        if kind != "move" or difficulty:
            dice = [random.choice([-1, 0, 1]) for _ in range(4)]
            score = ROLES[p["role"]]["scores"][APPROACHES.index(plan["approach"])]
            bonus = 0
            if invoke == "是" and plan["invoke_reason"] and p["fate"] > 0:
                p["fate"] -= 1
                bonus += 2
                event["costs"].append("命运点 -1（调用角色特质）")
            elif invoke == "是":
                event["costs"].append("特质未成功调用：需说明理由且有命运点")
            if p["boost"]:
                p["boost"] -= 1
                bonus += 2
                event["costs"].append("消耗一次优势 +2")
            total = sum(dice) + score + bonus
            margin = total - difficulty
            outcome = "failure" if margin < 0 else "tie" if margin == 0 else "style" if margin >= 3 else "success"
            event["roll"] = {"dice": dice, "dice_sum": sum(dice), "approach": plan["approach"],
                             "score": score, "bonus": bonus, "total": total, "difficulty": difficulty,
                             "margin": margin, "outcome": outcome}
        s["turn"] += 1
        clock_change = (1 if s["turn"] % 3 == 0 else 0) + (1 if outcome in ["failure", "tie"] else 0)
        s["clock"] = min(8, s["clock"] + clock_change)
        event["kind"] = kind
        if clock_change:
            event["costs"].append("潮水 +" + str(clock_change))
        if kind == "move":
            s["scene"] = target
            event["message"] = "队伍抵达" + MODULE["scenes"][target]["name"] + "。"
            if outcome == "failure":
                p["stress"] = min(3, p["stress"] + 1)
                event["costs"].append(actor + "压力 +1（涉水通过）")
        elif kind in ["investigate", "talk"]:
            clue_id = scene["clue"]
            s["clues"].append(clue_id)
            event["new_clues"] = [{"id": clue_id, **MODULE["clues"][clue_id]}]
            event["message"] = "发现线索：" + MODULE["clues"][clue_id]["title"] + "。"
            if outcome in ["failure", "tie"]:
                event["message"] += "必要线索仍然获得，但调查耽误时间，潮水加速。"
        elif kind == "advantage":
            if outcome != "failure":
                p["boost"] = min(2, p["boost"] + (2 if outcome == "style" else 1))
                event["message"] = "准备奏效，获得后续检定可用的优势。"
            else:
                event["message"] = "准备未能奏效，局势更紧迫。"
        elif kind == "finale":
            if outcome != "failure":
                s["ending"] = target
                event["message"] = MODULE["endings"][target]
            else:
                p["stress"] = min(3, p["stress"] + 1)
                event["costs"].append(actor + "压力 +1")
                event["message"] = "终局行动暂未成功，可以调整办法再试，或选择其他退路。"
        elif kind in ["attack", "defend", "overcome"]:
            event["message"] = "行动奏效，眼前阻碍被化解。" if outcome != "failure" else "行动未能奏效，局势恶化。"
            if outcome == "failure":
                p["stress"] = min(3, p["stress"] + 1)
                event["costs"].append(actor + "压力 +1")
        if outcome == "style" and kind == "overcome":
            p["boost"] = min(2, p["boost"] + 1)
        if not s["ending"] and all(p["stress"] >= 3 for p in s["players"]):
            s["ending"] = "retreat"
        elif not s["ending"] and s["clock"] >= 8:
            s["ending"] = "flood"
        if s["ending"]:
            event["ending"] = MODULE["endings"][s["ending"]]
        s["history"] = (s["history"] + [{"action": text(action, 120), "event": text(event["message"], 200)}])[-10:]
    now = MODULE["scenes"][s["scene"]]
    known = [{"id": c, "title": MODULE["clues"][c]["title"], "text": MODULE["clues"][c]["text"]} for c in s["clues"]]
    packet = {"title": MODULE["title"], "operation": operation, "actor": actor, "action": text(action, 1200),
              "event": event, "scene": {"name": now["name"], "description": now["description"], "npc": now["npc"]},
              "players": [{**p, "aspect": ROLES[p["role"]]["aspect"]} for p in s["players"]],
              "known_clues": known, "history": s["history"][-4:], "clock": s["clock"], "turn": s["turn"],
              "ending": MODULE["endings"].get(s["ending"], ""), "choices": choices_for(s)}
    return {"state": dumps(s), "packet": dumps(packet), "event": dumps(event), "choices": dumps(choices_for(s))}


def finalize(state, event, narration, choices):
    s, e, options = validate_state(state), json.loads(event), json.loads(choices)
    prose = re.sub(r"<think>.*?</think>", "", narration, flags=re.S).strip()[:2200]
    if not prose:
        prose = e["message"]
    if e["kind"] == "rules":
        prose = RULES
    roll = e.get("roll")
    if roll:
        labels = {"failure": "失败", "tie": "付出代价的成功", "success": "成功", "style": "大成功"}
        symbols = " ".join({-1: "−", 0: "0", 1: "+"}[d] for d in roll["dice"])
        mechanic = "检定：4dF [%s] = %+d；%s %+d；加值 %+d；总计 %d / 难度 %d → %s。" % (
            symbols, roll["dice_sum"], roll["approach"], roll["score"], roll["bonus"], roll["total"], roll["difficulty"], labels[roll["outcome"]])
    else:
        mechanic = "检定：本次无需掷骰。"
    if e["costs"]:
        mechanic += " 代价：" + "；".join(e["costs"]) + "。"
    if e["new_clues"]:
        prose += "\n\n线索入册：\n" + "\n".join("- " + c["title"] + "：" + c["text"] for c in e["new_clues"])
    board = "状态：%s｜回合 %d｜潮水 %d/8｜线索 %d/5\n%s" % (
        MODULE["scenes"][s["scene"]]["name"], s["turn"], s["clock"], len(s["clues"]),
        "；".join("%s（%s）：压力 %d/3，命运点 %d，优势 %d" % (p["name"], p["role"], p["stress"], p["fate"], p["boost"]) for p in s["players"]))
    if s["ending"]:
        prose += "\n\n结局：" + MODULE["endings"][s["ending"]]
    answer = prose + "\n\n" + mechanic + "\n\n" + board + "\n\n接下来可以：\n" + "\n".join(str(i + 1) + ". " + c for i, c in enumerate(options))
    return {"answer": answer, "session": dumps(s), "choices": "\n".join(options),
            "roll": dumps(roll or {}), "status": "ended" if s["ending"] else "playing", "turn": s["turn"]}
