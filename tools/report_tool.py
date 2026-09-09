# ============ 导入部分 ============
import os
import time

from langchain_core.tools import tool


@tool
def report_tool(markdown_body: str, title: str = "数据分析报告") -> str:
    """把本轮分析整理成 Markdown 结构化报告并保存到 reports/。
    markdown_body 为报告正文（可含数据表格、文字结论、图表路径引用）。
    返回报告文件路径，供用户下载或前端展示。
    """
    os.makedirs("reports", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join("reports", f"report_{ts}.md")
    header = (f"# {title}\n\n"
               f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + markdown_body + "\n")
    return f"报告已生成: {path}"
