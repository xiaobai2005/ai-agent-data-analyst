# ============ 量化评估脚本（六指标 + 消融对比） ============
# 六指标口径严格取自实习方案「Agent 评估核心指标速查表」：
#   1 任务完成率  2 工具调用准确率  3 平均执行步数
#   4 Token 成本  5 平均响应时长  6 轨迹合理性（LLM-as-Judge）
# 用法：
#   python eval.py                 # 跑基线 + 两组消融（默认 8 线程并发）
#   python eval.py --judge         # 额外启用 LLM-as-Judge 评估轨迹合理性
#   python eval.py --baseline-only # 只跑基线
#   python eval.py --workers 1     # 串行跑：只有这样才能得到准确的响应时长指标
#   python eval.py --workers 16    # 提高并发（注意上游 API 限流）

import argparse
import csv
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib
matplotlib.use("Agg")          # 无窗口模式，直接存文件
import matplotlib.pyplot as plt
from matplotlib import font_manager

import agent as agent_module
from llm import llm

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

TASKS_PATH = os.path.join("tests", "tasks.json")
OUT_DIR = "tests"

# ---------------- 消融变体：追加到 system prompt 的额外提示 ----------------
VARIANTS = {
    "baseline": ("基线（无额外提示）", ""),
    "prompt_opt": ("优化①：Prompt 优化（Thought 引导 + Few-shot）", """
【推理要求 · Thought 引导 + Few-shot】
调用每个工具前，先用一句话写下你的思考（Thought），再选择工具。
示例：
  用户："按地区统计销量总和"
  Thought：需要按 region 分组对 quantity 求和 -> 调用 stats_group_agg(group_by='region', column='quantity') -> 给出结论。
要求：所有数值必须来自工具返回结果，禁止估算或编造；最终回答包含关键数字。
"""),
    "tool_desc": ("优化②：工具描述增强（何时用 / 何时不用）", """
【工具使用说明 · 何时用 / 何时不用】
- profile_csv：想了解文件结构、编码、缺失值时用；已知列名时不用。
- read_csv：只需预览前几行时用；需要聚合或筛选时用 sql_query 或 stats_*。
- sql_query：需要筛选、排序、多条件或复杂聚合时用；简单求和用 stats_group_agg 更快。
- stats_group_agg：按某列分组求和/均值时用；只数次数用 stats_value_counts。
- stats_mom / stats_yoy：涉及环比/同比时用；只看总量不用。
- make_chart：需要可视化（柱状/折线/饼图/直方图）时用；只问数字不用。
- calculator：仅用于纯算术表达式；不要用它做数据聚合。
- report_tool：用户明确要求"报告"时用；普通问答不用。
"""),
}

REASONABLE_STEPS_RANGE = (1, 6)   # 轨迹合理性启发式：合理步数区间


def load_tasks():
    with open(TASKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["tasks"]


def is_success(task, reply, error):
    """任务完成判定：无异常 + 回复非空 + 命中期望关键词 + 不含禁止词"""
    if error or not reply or not reply.strip():
        return False
    low = reply.lower()
    expect = task.get("expect_any") or []
    if expect and not any(str(k).lower() in low for k in expect):
        return False
    forbid = task.get("forbid_any") or []
    if forbid and any(str(k).lower() in low for k in forbid):
        return False
    return True


def tool_accuracy(task, steps):
    """工具调用准确率：期望工具中被实际调用到的比例（无期望工具的任务返回 None 不计入）"""
    expect = task.get("expect_tools") or []
    if not expect:
        return None
    called = {s.get("tool") for s in steps}
    matched = sum(1 for t in expect if t in called)
    return matched / len(expect)


def judge_trajectory(task, steps, reply):
    """轨迹合理性 LLM-as-Judge：让模型给推理路径打 1-5 分"""
    traj = "\n".join(f"- {s.get('tool')}({s.get('args')})" for s in steps) or "（无工具调用）"
    prompt = (
        "你是 Agent 推理轨迹评审专家。请根据下面的用户任务与 Agent 实际调用的工具序列，"
        "评估其推理路径是否合理（工具选择是否恰当、是否存在冗余或缺失步骤）。\n\n"
        f"用户任务：{task['question']}\n"
        f"工具调用序列：\n{traj}\n"
        f"最终回答：{str(reply)[:300]}\n\n"
        "只输出一个 1 到 5 之间的整数评分（5=非常合理），不要输出其他内容。"
    )
    try:
        out = llm.invoke(prompt)
        text = out.content if hasattr(out, "content") else str(out)
        score = int("".join(ch for ch in text if ch.isdigit())[:1] or 3)
        return max(1, min(5, score))
    except Exception:
        return 3


def run_one_task(task, variant_key, extra_prompt, use_judge=False):
    """跑单个任务并返回一行结果（抽成函数供线程池并发调用）

    并发安全性说明：agent 内部的状态字典（_sessions / _profiles / _context / _logs
    / _pending）都是按 session_id 分桶的，每个任务使用独立 session_id，
    因此多线程之间不会互相覆盖。
    """
    sid = f"{variant_key}_task{task['id']}"
    t0 = time.time()
    error = None
    try:
        res = agent_module.chat(
            session_id=sid,
            user_input=task["question"],
            csv_path="demo.csv",
            system_extra=extra_prompt,
        )
    except Exception as e:
        error = str(e)
        res = {"reply": "", "steps": [], "tokens": {}}
    latency_ms = int((time.time() - t0) * 1000)

    steps = res.get("steps") or []
    reply = res.get("reply") or ""
    tokens = res.get("tokens") or {}

    success = is_success(task, reply, error)
    acc = tool_accuracy(task, steps)
    judge = judge_trajectory(task, steps, reply) if use_judge else None

    return {
        "variant": variant_key,
        "task_id": task["id"],
        "category": task["category"],
        "question": task["question"],
        "success": success,
        "steps": len(steps),
        "tools_called": "|".join(sorted({s.get("tool", "") for s in steps})),
        "tool_accuracy": "" if acc is None else round(acc, 3),
        "tokens_total": int(tokens.get("total", 0) or 0),
        "latency_ms": latency_ms,
        "judge_score": "" if judge is None else judge,
        "error": error or "",
        "reply": reply.replace("\n", " ")[:300],
    }


def _fallback_row(task, variant_key, err):
    """单任务异常时的兜底行，保证并发下一条失败不会中断整批评估"""
    return {
        "variant": variant_key, "task_id": task["id"],
        "category": task.get("category", ""), "question": task["question"],
        "success": False, "steps": 0, "tools_called": "", "tool_accuracy": "",
        "tokens_total": 0, "latency_ms": 0, "judge_score": "",
        "error": str(err), "reply": "",
    }


def run_variant(variant_key, extra_prompt, tasks, use_judge=False, workers=1):
    """跑一个变体下的全部任务（可并发），返回逐条结果与汇总指标

    workers<=1 时串行执行，latency_ms 才是真实的端到端响应时间；
    workers>1 时并发执行以缩短总耗时，但 latency_ms 会包含排队等待，仅供参考。
    """
    rows = []
    if workers <= 1:
        # ---------- 串行：延迟指标准确 ----------
        for task in tasks:
            row = run_one_task(task, variant_key, extra_prompt, use_judge)
            rows.append(row)
            print(f"   [{variant_key}] task {task['id']:>2} 完成 "
                  f"success={row['success']} steps={row['steps']} "
                  f"{row['latency_ms']}ms")
    else:
        # ---------- 并发：LLM 请求是网络 I/O，线程池可显著提速 ----------
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(run_one_task, task, variant_key, extra_prompt, use_judge): task
                for task in tasks
            }
            done = 0
            for fu in as_completed(futures):
                task = futures[fu]
                try:
                    row = fu.result()
                except Exception as e:
                    row = _fallback_row(task, variant_key, e)
                rows.append(row)
                done += 1
                print(f"   [{variant_key}] ({done}/{len(tasks)}) task "
                      f"{task['id']:>2} 完成 success={row['success']} "
                      f"steps={row['steps']} {row['latency_ms']}ms")

    # 并发完成顺序不确定，按 task_id 排序，保证 CSV 与汇总结果稳定可复现
    rows.sort(key=lambda r: r["task_id"])

    # ---------- 六指标汇总 ----------
    total = len(rows)
    successes = sum(1 for r in rows if r["success"])
    accs = [float(r["tool_accuracy"]) for r in rows if r["tool_accuracy"] != ""]
    succ_rows = [r for r in rows if r["success"]] or rows

    metrics = {
        "任务完成率": round(successes / total, 4) if total else 0,
        "工具调用准确率": round(sum(accs) / len(accs), 4) if accs else 0,
        "平均执行步数": round(statistics.mean([r["steps"] for r in succ_rows]), 3),
        "单任务Token成本": round(statistics.mean([r["tokens_total"] for r in rows]), 1),
        "平均响应时长ms": round(statistics.mean([r["latency_ms"] for r in rows]), 1),
        "轨迹合理性": None,
    }
    if use_judge:
        jd = [int(r["judge_score"]) for r in rows if r["judge_score"] != ""]
        if jd:
            metrics["轨迹合理性"] = round(statistics.mean(jd) / 5, 4)
    else:
        # 未启用 Judge 时用启发式：步数落在合理区间视为轨迹合理
        ok = sum(1 for r in rows
                 if REASONABLE_STEPS_RANGE[0] <= r["steps"] <= REASONABLE_STEPS_RANGE[1])
        metrics["轨迹合理性"] = round(ok / total, 4) if total else 0

    return rows, metrics


def write_csv(path, rows, fieldnames):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def plot_ablation(all_metrics):
    """绘制消融对比图：任务完成率 / 工具调用准确率 / 平均步数 / Token 成本"""
    keys = list(all_metrics.keys())
    idx = {k: VARIANTS[k][0] for k in keys}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    plots = [
        ("任务完成率", "任务完成率", "#4F8DFD"),
        ("工具调用准确率", "工具调用准确率", "#7C5CFC"),
        ("平均执行步数", "平均执行步数", "#22D3EE"),
        ("单任务Token成本", "单任务 Token 成本", "#F59E0B"),
    ]
    for ax, (mk, title, color) in zip(axes.ravel(), plots):
        vals = [all_metrics[k][mk] for k in keys]
        bars = ax.bar([idx[k] for k in keys], vals, color=color)
        ax.set_title(title)
        ax.tick_params(axis="x", labelrotation=15, labelsize=8)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{v}", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "eval_ablation.png")
    plt.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true", help="启用 LLM-as-Judge 评估轨迹合理性")
    parser.add_argument("--baseline-only", action="store_true", help="只跑基线变体")
    parser.add_argument("--workers", type=int, default=8,
                        help="并发线程数，默认 8；设为 1 则串行（只有串行时的响应时长才准确）")
    args = parser.parse_args()

    tasks = load_tasks()
    mode = (f"并发 {args.workers} 线程" if args.workers > 1 else "串行")
    print(f"载入测试任务 {len(tasks)} 条，开始评估（{mode}）…\n")

    all_rows, all_metrics = [], {}
    variants = VARIANTS if not args.baseline_only else {"baseline": VARIANTS["baseline"]}
    for key, (desc, extra) in variants.items():
        print(f"—— 运行变体：{key}（{desc}）——")
        v_t0 = time.time()
        rows, metrics = run_variant(key, extra, tasks, use_judge=args.judge,
                                    workers=args.workers)
        print(f"   变体耗时 {time.time() - v_t0:.1f}s")
        all_rows.extend(rows)
        all_metrics[key] = metrics
        for k, v in metrics.items():
            print(f"   {k}: {v}")

    # 逐条结果
    write_csv(os.path.join(OUT_DIR, "eval_results.csv"), all_rows,
              ["variant", "task_id", "category", "question", "success", "steps",
               "tools_called", "tool_accuracy", "tokens_total", "latency_ms",
               "judge_score", "error", "reply"])

    # 各变体六指标
    metric_rows = []
    for key, m in all_metrics.items():
        row = {"variant": key, "description": VARIANTS[key][0]}
        row.update(m)
        metric_rows.append(row)
    write_csv(os.path.join(OUT_DIR, "eval_metrics.csv"), metric_rows,
              ["variant", "description"] + list(all_metrics[list(all_metrics)[0]].keys()))

    # 消融对比（相对基线）
    if not args.baseline_only and "baseline" in all_metrics:
        print("\n===== 消融对比（相对基线）=====")
        base = all_metrics["baseline"]
        for key in all_metrics:
            if key == "baseline":
                continue
            print(f"\n[{key}] {VARIANTS[key][0]}")
            for mk in base:
                d = all_metrics[key][mk] - base[mk]
                print(f"   {mk}: {base[mk]} -> {all_metrics[key][mk]}  "
                      f"({'%+.4f' % d})")
        png = plot_ablation(all_metrics)
        print(f"\n消融对比图已保存: {png}")

    print(f"\n逐条结果: tests/eval_results.csv")
    print(f"六指标汇总: tests/eval_metrics.csv")
    if args.workers > 1:
        print("\n提示：本次为并发执行，CSV 中的 latency_ms 含排队等待，"
              "「平均响应时长」仅供参考；需要准确延迟请用 `python eval.py --workers 1` 串行跑。")


if __name__ == "__main__":
    main()
