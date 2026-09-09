# ============ tools 包：Agent 的工具箱 ============
#
# 这个 __init__.py 有两个作用：
#   1. 让 Python 把 tools/ 当成一个"包"，别的文件才能写 from tools.xxx import yyy
#   2. 对外暴露注册中心（registry），任何地方都能拿到当前已注册的全部工具
#
# 新增工具的正确姿势（详见 docs/工具扩展指南.md 与同目录下的 _template.py）：
#   在 tools/ 下新建任意 xxx_tool.py，写一个带类型注解 + docstring 的 @tool 函数即可，
#   注册中心会自动发现它，不需要改动本文件。

from .registry import catalog, discover_tools, get_tools, prompt_catalog, tool_names

__all__ = ["catalog", "discover_tools", "get_tools", "prompt_catalog", "tool_names"]
