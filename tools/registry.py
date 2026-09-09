# ============ 工具注册中心（Tool Registry）============
# 目标：做到「写一个函数即接入平台」。
# 只要把一个用 @tool 装饰的函数放进 tools/ 目录下的任意 .py 文件里，
# 本模块会在启动时自动发现它、生成 JSON Schema、注入给大模型的工具清单，
# 无需修改 agent.py / api.py / app.py 的任何一行代码。
#
# 发现规则：
#   1. 扫描 tools/ 包下的所有模块（文件名以 _ 开头的模块跳过，例如 _template.py 模板）
#   2. 收集模块中所有 BaseTool 实例（@tool 装饰器的产物）
#   3. 按 TOOL_ORDER 指定的顺序排列；未列出的工具排在末尾（按名称排序）
#      —— 顺序稳定很重要：工具清单会原样进入 Prompt，顺序变化会影响模型选工具

from __future__ import annotations

import importlib
import os
import pkgutil
from typing import Any

from langchain_core.tools import BaseTool

# 工具在 Prompt 中的展示顺序（按"数据入口 → 统计 → 可视化 → 输出"的认知顺序排列）
# 新增工具时：若希望它出现在特定位置，把工具函数名加进这个列表即可，不写则自动追加
TOOL_ORDER = [
    "profile_csv",
    "read_csv",
    "sql_query",
    "stats_summary",
    "stats_value_counts",
    "stats_group_agg",
    "stats_mom",
    "stats_yoy",
    "make_chart",
    "calculator",
    "report_tool",
]

# 风险等级默认值；模块内可通过 RISK_LEVEL = "high" 覆盖（高风险工具将被 HITL 关注）
DEFAULT_RISK_LEVEL = "low"

_CACHE: list[BaseTool] | None = None


def _iter_module_names() -> list[str]:
    """列出 tools/ 目录下所有可导入的模块名（跳过 _ 开头的内部模块）"""
    here = os.path.dirname(os.path.abspath(__file__))
    names = []
    for mod in pkgutil.iter_modules([here]):
        if mod.name.startswith("_"):        # _template.py 等模板/内部模块不参与注册
            continue
        names.append(mod.name)
    return names


def _risk_of(module: Any, tool_name: str) -> str:
    """读取模块中声明的工具风险等级（模块级 RISK_LEVEL 或 TOOL_META 字典）"""
    if isinstance(getattr(module, "TOOL_META", None), dict):
        return module.TOOL_META.get(tool_name, {}).get(
            "risk", getattr(module, "RISK_LEVEL", DEFAULT_RISK_LEVEL)
        )
    return getattr(module, "RISK_LEVEL", DEFAULT_RISK_LEVEL)


def discover_tools(force: bool = False) -> list[BaseTool]:
    """扫描 tools/ 包，返回所有已注册工具（按 TOOL_ORDER 排序）"""
    global _CACHE
    if _CACHE is not None and not force:
        return list(_CACHE)

    found: dict[str, BaseTool] = {}
    risks: dict[str, str] = {}

    for mod_name in _iter_module_names():
        module = importlib.import_module(f".{mod_name}", package=__package__)
        for obj in vars(module).values():
            # @tool 装饰器产出的对象就是 BaseTool 实例
            if isinstance(obj, BaseTool):
                found[obj.name] = obj
                risks[obj.name] = _risk_of(module, obj.name)

    def sort_key(name: str):
        # 在 TOOL_ORDER 里的按索引排，不在的统一放后面按名字排
        return (TOOL_ORDER.index(name) if name in TOOL_ORDER else len(TOOL_ORDER), name)

    tools = [found[n] for n in sorted(found, key=sort_key)]
    for t in tools:
        t.metadata = {**(t.metadata or {}), "risk": risks.get(t.name, DEFAULT_RISK_LEVEL)}
    _CACHE = tools
    return list(tools)


def get_tools(force: bool = False) -> list[BaseTool]:
    """对外主入口：获取全部已注册工具"""
    return discover_tools(force=force)


def catalog() -> list[dict]:
    """返回工具元信息（名称 / 说明 / 参数 Schema / 风险等级），供 GET /tools 与文档生成"""
    out = []
    for t in get_tools():
        schema = getattr(t, "args_schema", None)
        if schema is not None and hasattr(schema, "model_json_schema"):
            params = schema.model_json_schema()
        else:
            params = {"type": "object", "properties": {}}
        out.append({
            "name": t.name,
            "description": (t.description or "").strip(),
            "parameters": params,
            "risk": (t.metadata or {}).get("risk", DEFAULT_RISK_LEVEL),
        })
    return out


def prompt_catalog() -> str:
    """把工具清单渲染成一多行文本，直接注入 System Prompt（新增工具自动可见）"""
    return "\n".join(
        f"- {c['name']}：{c['description'].splitlines()[0] if c['description'] else ''}"
        for c in catalog()
    )


def tool_names() -> list[str]:
    return [t.name for t in get_tools()]


if __name__ == "__main__":
    # 自检：python -m tools.registry   → 打印当前已注册的全部工具
    print(f"已注册 {len(get_tools())} 个工具：")
    for c in catalog():
        print(f"  · {c['name']:<20} risk={c['risk']:<5} {c['description'].splitlines()[0][:60]}")
