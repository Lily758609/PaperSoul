# 用于去重
import json

def deduplicate_jsonl(file_path, key="line_raw"):
    """
    去重 JSONL 文件，按 key 判断重复
    :param input_file: 输入的 jsonl 文件路径
    :param output_file: 输出的 jsonl 文件路径
    :param key: 判断重复的字段，默认是 'line_raw'
    """
    seen = set()
    unique_lines = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # 避免坏行

            # 用 key 去重
            if key in obj:
                val = obj[key].strip()
                if val not in seen:
                    seen.add(val)
                    unique_lines.append(obj)
            else:
                # 如果没有 key，就直接保留
                unique_lines.append(obj)

    # 写回新文件
    with open(file_path, "w", encoding="utf-8") as f:
        for obj in unique_lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"✅ 去重完成，输入 {file_path} 共 {len(seen)} 条唯一记录，输出到 {file_path}")

if __name__ == "__main__":
    deduplicate_jsonl(r"D:\python_work\PaperSoul\data\roles_corpus\num1_cxs\相柳\lines.jsonl")
