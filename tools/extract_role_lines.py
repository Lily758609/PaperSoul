# -*- coding: utf-8 -*-
# 提取指定角色（如“相柳”）的台词 + 动作/心理
# 新增：--recall high 开高召回；输出上下文；可关闭去重
import argparse, json, re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
NOVELS_DIR = BASE / "data" / "novels"
OUT_DIR   = BASE / "data" / "roles_corpus"

CN_QUOTES = r"[“”\"『』「」]"
BRACKETS  = r"[（）\(\)]"
PAUSE     = r"[，、,—\-：:]"

SAY_VERBS = [
    "说","道","问","答","应道","回道","解释道","提醒道",
    "低声道","沉声道","淡淡道","冷冷道","缓缓道","轻声道",
    "笑道","冷笑道","轻笑道","淡笑道","叹道","喝道","斥道",
    "只道","淡声道","冷声道","低声说","冷声说","淡声说","说道","说完",
    "应了一声","嗯了一声"
]
# [NEW] 无“道/说”后缀但常用于发话的谓词/短语
SAY_NO_TAIL = [
    "斥","冷斥","喝","呵斥","吩咐","命令","令","提醒","应声","应了声",
    "淡声","冷声","淡笑","轻笑","点头","垂眸"
]
SAY_TAIL  = r"(?:道|说)"

ACTION_VERBS = [
    "看","望","瞥","盯","凝视","负手而立","负手","眺望",
    "笑","冷笑","轻笑","皱眉","抿唇","点头","摇头","叹气","沉默",
    "抽手","牵起","拥","抱","握","抓","抬头","垂眸","闭眼","转身",
    "停顿","顿了顿","哼","沉入","跃入","飞射","乘风破浪"
]
MENTAL_VERBS = [
    "想","心想","心道","心里想","心里道","暗想","暗道","回忆","记起",
    "犹豫","迟疑","放心","担心","不耐","厌烦","在意","不以为然"
]

def build_role_union(role, aliases):
    names = [role] + aliases
    names = [re.escape(x) for x in names if x]
    return "(?:" + "|".join(names) + ")"

def build_patterns(role, aliases, recall="default"):
    RU = build_role_union(role, aliases)
    say_union = "(?:" + "|".join(map(re.escape, SAY_VERBS)) + ")"
    say_no_tail = "(?:" + "|".join(map(re.escape, SAY_NO_TAIL)) + ")"
    WS = r"[ \t\u3000]*"
    AFTER = r"(?:[\s\S]{0,50}?)?"
    # 强匹配台词
    p1 = re.compile(
        rf"{RU}{AFTER}(?:{say_union}|{say_no_tail}(?:{WS}{SAY_TAIL})?){WS}[:：]?{WS}"
        rf"(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES})"
    )

    # [ADDED] 1b) 角色+（无谓词）+直接引号：“相柳负手而立，‘……’”
    p1b = re.compile(
        rf"{RU}{AFTER}{WS}[:：]?{WS}(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES})"
    )

    # [CHANGED] 2) 角色：台词 / 角色，台词（有/无引号）；允许可选修饰
    p2 = re.compile(
        rf"{RU}{AFTER}{WS}(?:[:：]|{PAUSE}){WS}(?:{CN_QUOTES})?{WS}(.+?){WS}(?:{CN_QUOTES})?$"
    )

    # [ADDED] 2b) 角色+谓词(+可选尾缀)+冒号+无引号内容（内心独白/书信式）
    p2b = re.compile(
        rf"{RU}{AFTER}(?:{say_union}|{say_no_tail}(?:{WS}{SAY_TAIL})?){WS}[:：]{WS}(.+)$"
    )

    # [CHANGED] 3) 引号在前 + 角色在后（尾部允许轻动作触发）
    p3 = re.compile(
        rf"(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES}){WS}"
        rf"{RU}{AFTER}(?:{say_union}|(?:[^\w]|^)(?:笑了?[一两]?声?|淡笑|轻笑|点头|垂眸)){WS}(?:{SAY_TAIL})?"
    )

    # 动作+台词组合（保持原索引 4/5/6 不变）
    p5 = re.compile(rf"{RU}(?P<act>[^。！？\n]*?){PAUSE}(?:{CN_QUOTES})(?P<sp>.+?)(?:{CN_QUOTES})")
    p6 = re.compile(rf"(?:{CN_QUOTES})(?P<sp>.+?)(?:{CN_QUOTES})(?:{PAUSE})?{RU}(?P<act>[^。！？\n]*)")
    p7 = re.compile(
        rf"{RU}{WS}(?:{BRACKETS}){WS}(?P<act>.+?){WS}(?:{BRACKETS}){WS}[:：]?{WS}(?:{CN_QUOTES}){WS}(?P<sp>.+?){WS}(?:{CN_QUOTES})")

    # [ADDED] 破折号体
    p4a = re.compile(rf"[—\-]{{2}}{WS}{RU}{WS}[:：]?{WS}(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES})")
    p4b = re.compile(rf"[—\-]{{2}}{WS}(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES})")

    # [CHANGED] 弱匹配引号：允许前置破折号
    p4 = re.compile(rf"(?:[—\-]{{2}}{WS})?(?:{CN_QUOTES}){WS}(.+?){WS}(?:{CN_QUOTES})")

    # 保持索引兼容：0=p1,1=p1b,2=p2,3=p3,4=p5,5=p6,6=p7,7=p4a,8=p4b,9=p4(弱)
    return [p1, p1b, p2, p3, p5, p6, p7, p4a, p4b, p4]

def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip("“”\"『』「」")
    s = s.strip("（）()")
    s = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩]", "", s)
    return s.strip()

def split_lines(blob: str):
    lines, buf, in_quote = [], [], False
    for ch in blob:
        if ch in "“『「\"":
            in_quote = not in_quote
        buf.append(ch)
        if not in_quote and ch in "。！？…？」』」\n":
            seg = "".join(buf).strip()
            if seg: lines.append(seg)
            buf = []
    tail = "".join(buf).strip()
    if tail: lines.append(tail)
    # 再做一次温和分割（长空白）
    out = []
    for ln in lines:
        parts = re.split(r"\s{2,}", ln.strip())
        for p in parts:
            if p: out.append(p)
    return out

def load_book_lines(book_dir: Path):
    texts = []
    for p in sorted(book_dir.glob("*.txt")):
        try:
            texts.append(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            texts.append(p.read_text(encoding="gbk", errors="ignore"))
    return split_lines("\n".join(texts))

def keep_range(s: str, min_len: int, max_len: int) -> bool:
    s2 = clean_text(s)
    if s2.endswith(("：", ":")): return False
    return (min_len <= len(s2) <= max_len)

def extract_role_lines(role: str, aliases, lines, min_len=4, max_len=140, with_context=2,
                       recall="default", include_neighbors=1, keep_duplicates=False,
                       include_loose_actions=False):
    """
    recall: default / high
    include_neighbors: 对命中句附带前/后邻居句，便于人工修订（0/1/2）
    keep_duplicates: 是否保留重复文本（高召回时建议 True，便于后期人工挑）
    include_loose_actions: 高召回时，收“句内出现角色名+动作词”的动作（不要求主语在句首）
    """
    patterns = build_patterns(role, aliases, recall=recall)
    out = []
    N = len(lines)

    act_kw = re.compile("|".join(map(re.escape, ACTION_VERBS + MENTAL_VERBS)))

    def add_item(text, idx, kind="speech", action=None):
        item = {
            "type": kind,
            "text": clean_text(text),
            "source_idx": idx,
            "line_raw": lines[idx]
        }
        if action:
            item["action"] = clean_text(action)
        # 附上下文辅助人工改
        if include_neighbors:
            L = include_neighbors
            item["ctx_prev"] = [lines[j] for j in range(max(0, idx-L), idx)]
            item["ctx_next"] = [lines[j] for j in range(idx+1, min(N, idx+1+L))]
        out.append(item)

    for i, raw in enumerate(lines):
        line = raw

        # 1) 先抓“动作+台词”组合
        mixed_hit = False
        for pat in (patterns[4], patterns[5], patterns[6]):
            m = pat.search(line)
            if m:
                sp = m.groupdict().get("sp"); act = m.groupdict().get("act")
                if sp and keep_range(sp, min_len, max_len):
                    add_item(sp, i, kind="mixed", action=act or "")
                    mixed_hit = True; break
        if mixed_hit: continue

        # 2) 经典强匹配台词
        got = None
        for pat in (patterns[0], patterns[1], patterns[2], re.compile(
                rf"{build_role_union(role, aliases)}(?:[\s\S]{{0,50}})?"
                rf"(?:{'|'.join(map(re.escape, SAY_VERBS + SAY_NO_TAIL))})[ \t\u3000]*[:：][ \t\u3000]*(.+)$"
                # [ADDED] p2b 作为内联强匹配
        ), patterns[3], patterns[7]):  # p1,p1b,p2,p2b,p3,p4a
            m = pat.search(line)
            if m:
                got = m.group(1) if m.groups() else line
                break

        # 3) 弱匹配引号：依据 recall 策略放宽
        if not got:
            for pat in (patterns[8], patterns[9]):  # p4b, p4(弱)
                m = pat.search(line)
                if not m:
                    continue
                candidate = m.group(1)
                if recall == "high":
                    got = candidate
                    break
                else:
                    ctx = " ".join(lines[max(0, i - with_context): min(N, i + with_context + 1)])
                    RU = build_role_union(role, aliases)
                    has_role = re.search(rf"{RU}", ctx)
                    has_say = re.search(
                        rf"{RU}(?:[\s\S]{{0,50}})?(?:{'|'.join(map(re.escape, SAY_VERBS + SAY_NO_TAIL))})",
                        ctx
                    )
                    if has_say or (has_role and len(candidate) <= 50):
                        got = candidate
                        break

        if got and keep_range(got, min_len, max_len):
            add_item(got, i, kind="speech")

        # 4) 动作句
        # 默认：主语更像角色（句首附近含 角色名 + 动作词）
        lead_act = re.search(rf"^\s*{build_role_union(role,aliases)}.{{0,16}}(?:{act_kw.pattern})", line)
        if lead_act and not re.search(CN_QUOTES, line) and keep_range(line, 4, 90) and "：" not in line and ":" not in line:
            add_item(line, i, kind="action")
        # 高召回可选：句中任何位置出现 角色名 + 动作词 也收（可能混入“他人对角色的动作描写”——你后续人工筛）
        elif recall == "high" and include_loose_actions and act_kw.search(line) and re.search(build_role_union(role,aliases), line) and not re.search(CN_QUOTES, line):
            if keep_range(line, 4, 120):
                add_item(line, i, kind="action")

    # 5) 去重（可关闭）
    if not keep_duplicates:
        uniq = {}
        for it in out:
            key = (it["type"], it["text"], it.get("action",""))
            if key not in uniq:
                uniq[key] = it
        out = list(uniq.values())

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="book_id, e.g. num1_csx")
    ap.add_argument("--role", required=True, help="角色名，如：相柳")
    ap.add_argument("--aliases", default="", help="角色别名，逗号分隔")
    ap.add_argument("--min_len", type=int, default=4)
    ap.add_argument("--max_len", type=int, default=140)
    ap.add_argument("--with_context", type=int, default=2)
    ap.add_argument("--recall", choices=["default","high"], default="default", help="高召回请选 high")
    ap.add_argument("--include_neighbors", type=int, default=1, help="每条样本附带的上下文窗口（前后各N句）")
    ap.add_argument("--keep_duplicates", action="store_true", help="保留重复样本")
    ap.add_argument("--include_loose_actions", action="store_true", help="高召回时，收句中任意位置的 角色名+动作词")
    args = ap.parse_args()

    book_dir = NOVELS_DIR / args.book
    assert book_dir.exists(), f"not found: {book_dir}"

    aliases = [x.strip() for x in args.aliases.split(",") if x.strip()]

    lines = load_book_lines(book_dir)
    samples = extract_role_lines(
        role=args.role,
        aliases=aliases,
        lines=lines,
        min_len=args.min_len,
        max_len=args.max_len,
        with_context=args.with_context,
        recall=args.recall,
        include_neighbors=args.include_neighbors,
        keep_duplicates=args.keep_duplicates,
        include_loose_actions=args.include_loose_actions
    )

    out_dir = OUT_DIR / args.book / args.role
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_dir / "lines.jsonl"
    txt_path   = out_dir / "lines.txt"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for it in samples:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    with open(txt_path, "w", encoding="utf-8") as f:
        for it in samples:
            tag = it["type"]
            if tag == "mixed":
                f.write(f"[mixed] 动作：{it.get('action','')} ｜ 台词：{it['text']}\n")
            elif tag == "action":
                f.write(f"[action] {it['text']}\n")
            else:
                f.write(f"[speech] {it['text']}\n")

    print(f"✅ 抽取完成：{len(samples)} 条")
    print(f"JSONL: {jsonl_path}")
    print(f"TXT  : {txt_path}")

if __name__ == "__main__":
    main()

