import pandas as pd
from langchain_core.tools import tool

from .guard import safe_path


# 设计说明（讲给学生）：这里把原来"一个函数带 operation 参数"拆成了
# 三个独立工具。原因：让模型"选工具"比让模型"填参数"更不容易出错。
# 就像把遥控器上"模式+数值"两个键，做成三个标了名字的专用键。

@tool
def stats_summary(csv_path: str) -> str:
    """对 CSV 所有数值列计算均值、中位数、标准差、最小值、最大值。"""
    # describe() 是 pandas 的"一键全套统计"：
    # 自动算出 count/mean/std/min/25%/50%/75%/max
    # round(4) 保留 4 位小数，防止 3.14159265... 刷屏
    df = pd.read_csv(csv_path)
    return df.describe().round(4).to_string()


@tool
def stats_value_counts(csv_path: str, column: str) -> str:
    """统计 CSV 某一列中每个值出现的次数。"""
    df = pd.read_csv(csv_path)
    # 防御：模型可能猜错列名（比如把 Region 写成 region），
    # 先检查再计算，给出"可用列"提示方便它自我纠正
    if column not in df.columns:
        return f"错误：列不存在，可用列 {list(df.columns)}"
    # value_counts() ：数每个值出现几次，按次数从多到少排好序
    return df[column].value_counts().to_string()


@tool
def stats_group_agg(csv_path: str, group_by: str, column: str) -> str:
    """按某列分组，对另一数值列计算总和与平均值。
    示例: group_by='region', column='quantity' 得到各地区销量统计。"""
    df = pd.read_csv(csv_path)
    # 两列都要检查：分组列和数值列缺一不可
    if group_by not in df.columns or column not in df.columns:
        return f"错误：列不存在，可用列 {list(df.columns)}"
    # 分组聚合拆解：
    #   df.groupby(group_by)      -> 按分组列把行分成几堆（北京一堆上海一堆…）
    #   [column]                  -> 每堆里只取要计算的数值列
    #   .agg(["sum", "mean"])     -> 每堆各算"总和"和"平均"两种指标
    #   .round(4)                 -> 结果保留 4 位小数
    result = df.groupby(group_by)[column].agg(["sum", "mean"]).round(4)
    return result.to_string()


@tool
def stats_mom(csv_path: str, date_col: str, value_col: str) -> str:
    """计算环比（逐期增长率 %）：按 date_col 分组对 value_col 求和，再算相邻期变化率。
    示例: date_col='date', value_col='quantity' 得到每日销量的环比增长。"""
    try:
        safe_path(csv_path)
    except ValueError as e:
        return f"错误：{e}"
    df = pd.read_csv(csv_path)
    if date_col not in df.columns or value_col not in df.columns:
        return f"错误：列不存在，可用列 {list(df.columns)}"
    s = df.groupby(date_col)[value_col].sum().sort_index()
    mom = s.pct_change() * 100
    out = pd.DataFrame({
        "日期": [str(i) for i in s.index],
        "数值": s.values,
        "环比%": mom.round(2).values,
    })
    return out.to_string(index=False)


@tool
def stats_yoy(csv_path: str, date_col: str, value_col: str) -> str:
    """计算同比（年增长率 %）：把 date_col 解析为日期、按年汇总 value_col，再算年度变化率。"""
    try:
        safe_path(csv_path)
    except ValueError as e:
        return f"错误：{e}"
    df = pd.read_csv(csv_path)
    if date_col not in df.columns or value_col not in df.columns:
        return f"错误：列不存在，可用列 {list(df.columns)}"
    try:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    except Exception:
        return f"错误：无法把 {date_col} 解析为日期"
    s = df.dropna(subset=[date_col]).groupby(df[date_col].dt.year)[value_col].sum()
    yoy = s.pct_change() * 100
    out = pd.DataFrame({
        "年份": [str(int(i)) for i in s.index],
        "数值": s.values,
        "同比%": yoy.round(2).values,
    })
    return out.to_string(index=False)
