# 对提取文本进行二次处理
# 从旧版 lines.jsonl（无 speaker）生成 ctx 拼接后的 jsonl，并补充 speaker 标注
import json, re, argparse
from pathlib import Path

SAY = r"(说|道|问|答|应道|回道|解释道|提醒道|低声道|沉声道|淡淡道|冷冷道|笑道|轻声道|冷笑道|叹道|喝道|斥道|说道|说完)"
ACT = r"(看|望|瞥|盯|凝视|负手|垂眸|皱眉|抿唇|点头|摇头|叹气|沉默|抽手|牵起|拥|抱|握|抓|抬头|闭眼|转身|停顿|顿了顿|轻笑|冷笑|飞射|乘风破浪|沉入|跃入)"
CN_QUOTES = r"[“”\"『』「」]"

def _union(names):
    names = [re.escape(x) for x in names if x]
    return "(?:" + "|".join(names) + ")" if names else r"(?!x)x"

def guess_speaker(text, action, role, aliases, others, mode="strict"):
    """返回 (speaker, conf, rule) —— 保守：强证据才判定为 role，其它给 '未知' 或 '其他'。"""
    RU = _union([role] + aliases)
    OU = _union(others)

    rules = []
    def hit(name, score): rules.append((name, score))

    # 强证据：相柳作为说话/动作主体
    if re.search(rf"^{RU}.{{0,12}}{SAY}", text or ""):       hit("xl_front_say", 1.0)
    if re.search(rf"{RU}.{{0,12}}{SAY}\s*$", text or ""):    hit("xl_tail_say", 0.9)
    if re.search(rf"^{RU}.{{0,16}}{ACT}", action or ""):     hit("xl_act_subject", 0.9)

    # 反证据：他人作为主体
    if re.search(rf"^{OU}.{{0,12}}{SAY}", text or ""):       hit("other_front_say", -1.0)
    if re.search(rf"{OU}.{{0,12}}{SAY}\s*$", text or ""):    hit("other_tail_say", -0.9)
    if re.search(rf"^{OU}.{{0,16}}{ACT}", action or ""):     hit("other_act_subject", -0.8)

    # 纯引号弱归属（仅 balanced/lenient）
    if mode in ("balanced","lenient") and re.search(rf"{CN_QUOTES}.+?{CN_QUOTES}", text or ""):
        if re.search(rf"{RU}.{{0,12}}{SAY}", text or "") or re.search(rf"{RU}", text or ""):
            hit("weak_quote_ctx_xl", 0.4 if mode=="balanced" else 0.5)

    score = sum(s for _, s in rules)
    if mode == "strict":  score *= 1.2
    if mode == "lenient": score *= 0.9

    conf = max(0.0, min(1.0, 0.5 + 0.4 * score))
    if conf >= 0.7:
        speaker = role
    elif conf <= 0.3:
        speaker = "其他"
    else:
        speaker = "未知"

    return speaker, round(conf, 3), "+".join(n for n,_ in rules) or "none"

def join_ctx(item):
    """把 ctx_prev + line_raw + ctx_next 拼成一条 doc（不截断）"""
    prev = item.get("ctx_prev") or []
    nxt  = item.get("ctx_next") or []
    if isinstance(prev, str): prev = [prev]
    if isinstance(nxt, str):  nxt  = [nxt]
    raw  = item.get("line_raw") or item.get("text","")
    parts = [*(p for p in prev if p), raw, *(n for n in nxt if n)]
    return " ".join(x.strip() for x in parts if x and x.strip())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="book_id，如 num1_csx")
    ap.add_argument("--role", required=True, help="主角名，如 相柳")
    ap.add_argument("--aliases", default="", help="主角别名，逗号分隔")
    ap.add_argument("--others",  default="小六,小夭,涂山璟,轩,颛顼", help="互动中常见他者名字，逗号分隔")
    ap.add_argument("--mode", choices=["strict","balanced","lenient"], default="strict", help="说话人判定严格度")
    ap.add_argument("--src", default="lines.jsonl", help="输入文件名（默认 roles_corpus/.../lines.jsonl）")
    ap.add_argument("--dst", default="ctx_with_speaker.jsonl", help="输出文件名")
    ap.add_argument("--preview_tsv", action="store_true", help="额外输出一个预览 TSV，便于人工快速审查")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    in_path  = base / "data" / "roles_corpus" / args.book / args.role / args.src
    out_path = base / "data" / "roles_corpus" / args.book / args.role / args.dst
    assert in_path.exists(), f"not found: {in_path}"

    aliases = [x.strip() for x in args.aliases.split(",") if x.strip()]
    others  = [x.strip() for x in args.others.split(",")  if x.strip()]

    rows, out_rows = [], []
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            rows.append(json.loads(line))

    for r in rows:
        text   = r.get("text","")
        action = r.get("action","")
        doc    = join_ctx(r)
        spk, conf, rule = guess_speaker(text, action, args.role, aliases, others, mode=args.mode)

        out_rows.append({
            "doc": doc,                          # 用于向量库
            "anchor": r.get("line_raw") or text, # 显示给用户看的核心句
            "type": r.get("type","speech"),
            "speaker": spk,
            "speaker_conf": conf,
            "rule": rule,
            "source_idx": r.get("source_idx"),
        })

    with open(out_path, "w", encoding="utf-8") as f:
        for it in out_rows:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"✅ wrote {len(out_rows)} items → {out_path}")

    if args.preview_tsv:
        tsv_path = out_path.with_suffix(".tsv")
        with open(tsv_path, "w", encoding="utf-8") as f:
            f.write("speaker\tspeaker_conf\ttype\tanchor\tdoc\n")
            for it in out_rows[:1000]:  # 防止超大文件卡编辑器
                f.write(f"{it['speaker']}\t{it['speaker_conf']}\t{it['type']}\t{it['anchor']}\t{it['doc']}\n")
        print(f"👀 preview: {tsv_path}")

if __name__ == "__main__":
    main()
