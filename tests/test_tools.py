# ============ 工具自测脚本（不经过 Agent，直接调用工具验证正确性）============
# 对应实习方案 Day2 任务 8：5 类工具 × 多用例 + 安全护栏用例
# 运行：python tests/test_tools.py      （退出码 0 = 全部通过，1 = 有失败）
# 说明：脚本会自动把工作目录切到项目根目录，保证 demo.csv / charts 等相对路径可用

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from tools.calculator_tool import calculator
from tools.chart_tool import make_chart
from tools.csv_tool import read_csv
from tools.guard import safe_path
from tools.profile_tool import profile_csv
from tools.report_tool import report_tool
from tools.sql_tool import sql_query
from tools.stats_tool import (stats_group_agg, stats_mom, stats_summary,
                              stats_value_counts, stats_yoy)

CSV = "demo.csv"
_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = ""):
    """断言并打印结果：cond 为真记通过，否则记失败并打印返回内容片段"""
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name} -> {detail[:200]}")


def run_case(name: str, fn, expect_sub: str = "", expect_not: str = ""):
    """执行一个工具用例：expect_sub 必须出现在结果中；expect_not 必须不出现"""
    try:
        out = str(fn())
    except Exception:
        print(f"  [FAIL] {name} -> 抛异常")
        print(traceback.format_exc(limit=2))
        global _failed
        _failed += 1
        return
    ok = (not expect_sub or expect_sub in out) and (not expect_not or expect_not not in out)
    check(name, ok, out)


def main():
    print("=" * 60)
    print("工具自测：CSV / SQL / 统计 / 图表 / 计算器 + 安全护栏")
    print("=" * 60)

    # ---------- 1. CSV 读取 ----------
    print("\n[1] CSV 读取")
    run_case("预览前 5 行含列名", lambda: read_csv.invoke({"file_path": CSV, "nrows": 5}), "region")
    run_case("文件不存在返回人话提示", lambda: read_csv.invoke({"file_path": "nope.csv"}), "不存在")

    # ---------- 2. 数据画像 ----------
    print("\n[2] 数据画像")
    run_case("返回行数与编码", lambda: profile_csv.invoke({"csv_path": CSV}), "行数")
    run_case("识别缺失值", lambda: profile_csv.invoke({"csv_path": CSV}), "缺失值")

    # ---------- 3. SQL 查询 ----------
    print("\n[3] SQL 查询")
    run_case("分组聚合",
             lambda: sql_query.invoke(
                 {"csv_path": CSV, "sql": "SELECT region, SUM(quantity) AS q FROM demo GROUP BY region"}),
             "北京")
    run_case("高危 DROP 被拦截",
             lambda: sql_query.invoke({"csv_path": CSV, "sql": "DROP TABLE demo"}), "拦截")
    run_case("非 SELECT 被拦截",
             lambda: sql_query.invoke({"csv_path": CSV, "sql": "UPDATE demo SET price=1"}), "拦截")

    # ---------- 4. 统计工具 ----------
    print("\n[4] 统计工具")
    run_case("描述统计", lambda: stats_summary.invoke({"csv_path": CSV}), "mean")
    run_case("取值计数", lambda: stats_value_counts.invoke({"csv_path": CSV, "column": "product"}), "键盘")
    run_case("分组聚合", lambda: stats_group_agg.invoke(
        {"csv_path": CSV, "group_by": "region", "column": "quantity"}), "北京")
    run_case("环比", lambda: stats_mom.invoke(
        {"csv_path": CSV, "date_col": "date", "value_col": "quantity"}), "环比")
    run_case("同比", lambda: stats_yoy.invoke(
        {"csv_path": CSV, "date_col": "date", "value_col": "quantity"}), "同比")
    run_case("列名不存在给出可用列", lambda: stats_value_counts.invoke(
        {"csv_path": CSV, "column": "not_exist"}), "可用列")

    # ---------- 5. 图表生成 ----------
    print("\n[5] 图表生成")
    bar_out = make_chart.invoke({"csv_path": CSV, "chart_type": "bar", "x": "region", "y": "quantity"})
    check("柱状图生成成功", bar_out.startswith("图表已保存:") and
          os.path.exists(bar_out.split(":", 1)[1].strip()), bar_out)
    pie_out = make_chart.invoke({"csv_path": CSV, "chart_type": "pie", "x": "region"})
    check("饼图（无 y）生成成功", pie_out.startswith("图表已保存:"), pie_out)
    run_case("非法图表类型被拒", lambda: make_chart.invoke(
        {"csv_path": CSV, "chart_type": "3d", "x": "region"}), "错误")

    # ---------- 6. 计算器 ----------
    print("\n[6] 计算器")
    run_case("四则运算 (3+5)*12", lambda: calculator.invoke({"expression": "(3+5)*12"}), "96")
    run_case("代码注入被拦截", lambda: calculator.invoke({"expression": "__import__('os')"}), "错误")
    run_case("嵌套乘方被拦截", lambda: calculator.invoke({"expression": "9**9**9"}), "错误")
    run_case("除零提示", lambda: calculator.invoke({"expression": "1/0"}), "除零")

    # ---------- 7. 安全护栏 ----------
    print("\n[7] 安全护栏")
    for bad in ("/etc/passwd", "C:\\Windows\\win.ini", "../secret.csv"):
        try:
            safe_path(bad)
            check(f"拦截危险路径 {bad}", False, "未被拦截")
        except ValueError:
            check(f"拦截危险路径 {bad}", True)
    check("放行合法相对路径", safe_path("uploads/demo.csv").replace("\\", "/") == "uploads/demo.csv")

    # ---------- 8. 报告工具 ----------
    print("\n[8] 报告工具")
    rep = report_tool.invoke({"markdown_body": "## 自测\n- ok", "title": "自测报告"})
    check("报告落盘", rep.startswith("报告已生成:") and os.path.exists(rep.split(":", 1)[1].strip()), rep)

    print("\n" + "=" * 60)
    print(f"结果：通过 {_passed} 项，失败 {_failed} 项")
    print("=" * 60)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
