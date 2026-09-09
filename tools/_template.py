# ============ 新工具模板（复制本文件 → 改名 → 改函数 → 完成接入）============
#
# 文件名以 _ 开头，注册中心会跳过它，因此本文件不会被当成真工具加载。
# 使用方法（30 分钟接入流程，详见 docs/工具扩展指南.md）：
#   1. 复制本文件为 tools/my_tool.py（去掉下划线前缀）
#   2. 改造下面 my_tool 函数：改函数名、改参数、改 docstring、写业务逻辑
#   3. 重启后端：uvicorn api:app --reload
#   4. 访问 GET /tools 或运行 python -m tools.registry 确认新工具已出现
#
# 三条铁律（踩过的坑）：
#   · 必须写参数类型注解（csv_path: str）——模型靠它填参数
#   · 必须写 docstring（三引号说明）——模型靠它决定"什么时候用这个工具"
#   · 必须返回字符串——工具结果要塞进对话消息，DataFrame / 图片对象会报错

from langchain_core.tools import tool

from .guard import safe_path

# 可选：声明本模块工具的风险等级（low / medium / high）
# high 会被 GET /tools 标记出来，供 HITL（人工确认）机制重点关注
RISK_LEVEL = "low"


@tool
def my_tool(csv_path: str, column: str = "") -> str:
    """一句话说明这个工具干什么（给模型看，决定"何时用"）。
    第二句补充"何时不用"或参数含义，例如：只做数值列统计，文本列请用 sql_query。"""
    # 1) 安全护栏：所有涉及文件路径的工具，第一件事就是校验路径
    try:
        safe_path(csv_path)
    except ValueError as e:
        return f"错误：{e}"

    # 2) 业务逻辑：出错时返回"人话"，让模型能自我纠正，而不是抛异常中断整个 Agent
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if column and column not in df.columns:
            return f"错误：列不存在，可用列 {list(df.columns)}"
        result = f"共 {len(df)} 行" + (f"，{column} 唯一值 {df[column].nunique()} 个" if column else "")
    except Exception as e:
        return f"错误：{type(e).__name__}: {e}"

    # 3) 返回字符串
    return result
