# ============ 导入部分 ============
import os
import chardet                      # 编码检测库
import pandas as pd
from langchain_core.tools import tool


@tool
def profile_csv(csv_path: str) -> str:
    """分析 CSV 数据结构：自动检测编码、列类型、缺失值、唯一值基数与数值列统计。
    csv_path 是文件路径。返回一份"数据画像"文本，供 Agent 和用户快速了解数据。"""
    # ---------- 1. 检测文件编码（chardet 抽样前 100KB 推断） ----------
    try:
        with open(csv_path, "rb") as f:
            raw = f.read(100_000)
        enc = chardet.detect(raw).get("encoding") or "utf-8"
    except Exception:
        enc = "utf-8"

    # ---------- 2. 用检测到的编码读入 ----------
    try:
        df = pd.read_csv(csv_path, encoding=enc)
    except Exception:
        df = pd.read_csv(csv_path)          # 兜底：交给 pandas 自己猜

    n_rows, n_cols = len(df), len(df.columns)

    # ---------- 3. 列类型 ----------
    dtypes = {c: str(t) for c, t in df.dtypes.items()}

    # ---------- 4. 缺失值统计 ----------
    missing = df.isna().sum()
    missing_dict = {c: int(v) for c, v in missing.items() if v > 0}

    # ---------- 5. 唯一值基数（每列有多少不同取值） ----------
    nunique = {c: int(df[c].nunique()) for c in df.columns}

    # ---------- 6. 数值列描述统计（含非数值列的混合概览） ----------
    desc = df.describe(include="all").round(4).to_string()

    # ---------- 7. 组装返回文本 ----------
    lines = [
        f"行数: {n_rows}，列数: {n_cols}，检测编码: {enc}",
        "列类型: " + str(dtypes),
    ]
    lines.append("缺失值: " + (str(missing_dict) if missing_dict else "无"))
    lines.append("唯一值基数: " + str(nunique))
    lines.append("统计概览:\n" + desc)
    return "\n".join(lines)
