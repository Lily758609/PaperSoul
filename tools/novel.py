import os
import re
import argparse
#  预处理小说，章节分段
def clean_text(text: str) -> str:
    """简单清洗：去掉多余空行、首尾空格"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_into_chapters(text: str):
    """
    按常见章节标题切分（你可根据小说格式调整正则）
    例：第1章 / 第一章 / 第一节 / 第一回
    """
    pattern = r"(第[一二三四五六七八九十百零\d]+[章节回卷].*?)\n"
    parts = re.split(pattern, text)
    chapters = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        chapters.append((title, content))
    return chapters

def process_novel(input_path: str, output_dir: str):
    # 读取原文
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    text = clean_text(text)
    chapters = split_into_chapters(text)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    for idx, (title, content) in enumerate(chapters, start=34):
        filename = f"{idx:03d}.txt"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n\n{content}")
        print(f"✅ 已保存章节：{filename} ({title})")

    print(f"\n📚 共切分 {len(chapters)} 章，保存至 {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小说按章节切分工具（独立运行）")
    parser.add_argument("--input", default=r"D:\python_work\Learning\data\思无涯.txt",
                        help=r"输入文件路径")
    parser.add_argument("--output", default=r"D:\python_work\Learning\data\novel2",
                        help=r"输出目录")
    args = parser.parse_args()
    process_novel(args.input, args.output)