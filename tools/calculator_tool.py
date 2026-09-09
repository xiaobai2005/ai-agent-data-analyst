import re                                   # 正则表达式库（文本模式匹配）
from langchain_core.tools import tool

# 编译正则模式（编译一次，之后反复使用更快）
# ^[...]$ 的意思是"从头到尾每个字符都必须在方括号这个集合里"：
#   \d   任何数字 0-9
#   \s   空格
#   \+\-\*/  加减乘除号（* . 在正则里有特殊含义，所以前面加了反斜杠 \ 转义）
#   \.   小数点
#   \(\) 括号
#   %    百分号（取余）
# 故意【不放行任何字母】——没有字母就写不出函数名、属性名，
# __import__('os') 这类恶意代码在字符检查这关就被拦下
_ALLOWED = re.compile(r'^[\d\s\+\-\*/\.\(\)%]+$')


@tool
def calculator(expression: str) -> str:
    """安全计算一个纯算术表达式，如 (3+5)*2 或 2**10。
    只允许数字和 + - * / ( ) . % 运算符。"""
    # ---------- 护栏①：空串和超长串 ----------
    # not expression：空字符串本身就是 False，not 后为 True -> 拦截
    # 超过 100 字符的表达式也拒绝（超长输入本身就有风险）
    if not expression or len(expression) > 100:
        return "错误：表达式为空或超过 100 字符"

    # ---------- 护栏②：字符白名单 ----------
    # .match() 检查整个字符串是否符合 ^...$ 模式，不符合返回 None
    if not _ALLOWED.match(expression):
        return "错误：只允许数字和 + - * / ( ) . %"

    # ---------- 护栏③：防"卡死"攻击 ----------
    # ** 是乘方。9**9**9**9 是个天文数字，计算机会算到天荒地老
    # 限制乘方最多出现一次，杜绝嵌套乘方
    if expression.count("**") > 1:
        return "错误：不允许嵌套乘方，防止计算卡死"

    try:
        # eval：把字符串当代码执行。本身很危险（能执行任意代码），
        # 但我们前面三道护栏保证了：里面只有数字和运算符。
        # 第二三个参数 {"__builtins__": {}}, {} 是"清空内置函数环境"，
        # 双保险：即使字符检查被绕过，表达式也拿不到任何可用的函数
        value = eval(expression, {"__builtins__": {}}, {})

        # 12.0 -> 12 的美化：is_integer() 判断小数部分是否为 0
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        # 注意返回 str(value)：工具结果必须是字符串
        return str(value)
    except ZeroDivisionError:
        return "错误：除零"
    except Exception as e:
        # 兜底：其他所有错误（语法错误等）都返回给模型让它自己改
        return f"错误：{e}"
