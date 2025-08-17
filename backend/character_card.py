import json
from pathlib import Path
from backend.schema import CharacterCard

BASE_DIR = Path(__file__).resolve().parents[1]

def load_character(card_id: str) -> CharacterCard:
    card_path = BASE_DIR / "data" / "lore" / "characters" / f"{card_id}.json"
    with open(card_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CharacterCard(**data)

def render_system_prompt(card: CharacterCard, hidden_context: str) -> str:
    identity= "\n- ".join(card.identity)
    appearence = "\n- ".join(card.appearence)
    personal = "\n- ".join(card.personal)
    speech_style = "\n- ".join(card.speech_style)
    relationships = "\n- ".join(card.relationships)
    interaction_with_xiaoyao = "\n- ".join(card.interaction_with_xiaoyao)
    principles = "\n- ".join(card.principles)
    world_rules = "\n- ".join(card.world_rules)
    safety_rules = "\n- ".join(card.safety_rules)
    return f"""
你现在是《{card.book_title}》中的 {card.display_name}。严格遵守以下人设与世界观，仅以角色身份进行对话：
【身份】
- {identity}
【外形气质】
- {appearence}
【性格特点】
- {personal}
【语言特点】
- {speech_style}
【人物关系】
- {relationships}
【与小夭关系】
- {interaction_with_xiaoyao}
【处事原则】
- {principles}
【世界观与回答原则】
- {world_rules}
【安全边界】
- {safety_rules}
【隐式剧情证据（来自原文检索，用户不可见）】
{hidden_context}
【对话规则】
1) 仅使用第一人称，不要跳出设定；
2) 基于隐式证据作答，如证据不足，可做克制延展但不得自相矛盾；
3) 语言简洁自然，必要时可有少量内心独白（括号标注）。
4) **不得直接引用原文文本或泄露“隐式证据”的具体来源/内容，仅在回答中消化其信息。**
5) 我的身份是小夭，我们将进行对话，你的回答可带有适当动作或神态描写，用于体现人物内心活动
""".strip()