# ============ 导入部分 ============
import os
import re
import sqlite3

import pandas as pd
from langchain_core.tools import tool

from .guard import safe_path

# 危险 SQL 黑名单：拦截一切写/破坏操作，仅放行只读 SELECT
_DANGEROUS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|REPLACE|ALTER|CREATE|TRUNCATE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


@tool
def sql_query(csv_path: str, sql: str) -> str:
    """对 CSV 数据执行只读 SQL 查询（最多20行）。CSV 自动导入 SQLite，表名=文件名去后缀。
    仅放行 SELECT，拦截 DROP/DELETE/UPDATE/INSERT/ALTER/CREATE 等危险操作。"""
    # 护栏①：路径穿越校验
    try:
        safe_path(csv_path)
    except ValueError as e:
        return f"错误：{e}"

    # 护栏②：危险语句硬拦截
    if _DANGEROUS.search(sql):
        return ("错误：检测到危险 SQL 操作（DROP/DELETE/UPDATE/INSERT/ALTER/CREATE 等），"
                "已被安全护栏拦截。本工具仅支持只读 SELECT 查询。")
    # 护栏③：必须以 SELECT 开头（防 WITH... 等绕过）
    if not re.match(r"^\s*select\b", sql, re.IGNORECASE):
        return "错误：仅支持以 SELECT 开头的只读查询。"

    os.makedirs("data", exist_ok=True)
    db = "data/agent.db"

    # 导入阶段：首次把 CSV 写入库（系统行为，非用户 SQL）
    conn_w = sqlite3.connect(db)
    try:
        table = os.path.splitext(os.path.basename(csv_path))[0]
        exists = conn_w.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            pd.read_csv(csv_path).to_sql(table, conn_w, index=False)
    except Exception as e:
        return f"导入失败: {e}"
    finally:
        conn_w.close()

    # 查询阶段：只读连接执行用户 SQL（mode=ro 双保险）
    conn = sqlite3.connect(f"file:{os.path.abspath(db)}?mode=ro", uri=True)
    try:
        df = pd.read_sql_query(sql, conn)
    except Exception as e:
        return f"SQL 错误: {e}"
    finally:
        conn.close()

    return df.head(20).to_string(index=False)
