# ============ 导入部分 ============

# import pandas as pd ：表格处理库，读 CSV 全靠它
import pandas as pd

# from langchain_core.tools import tool ：从 LangChain 里借出 @tool 装饰器
# "装饰器"是 Python 的一种语法：写在函数上方、以 @ 开头，
# 作用是"给函数盖章加工"。@tool 盖章后，普通函数就变成
# LangChain 认识的"工具"，还自动生成给大模型看的说明书
from langchain_core.tools import tool

from .guard import safe_path


# ============ 定义工具函数 ============

# @tool 装饰器：把下面的普通函数"注册"成 LangChain 工具
# 它会自动读取两样东西来生成说明书：
#   1. 函数参数的类型注解（file_path: str = 参数是字符串）
#   2. 三引号里的 docstring（工具是干什么的）
# 所以这两样必须认真写，模型全靠它们决定"什么时候用这个工具"
@tool

# def 定义函数。参数说明：
#   file_path: str         -> 必填，CSV 文件路径
#   nrows: int = 5         -> 选填，预览几行，默认 5（= 号是"默认值"写法）
# -> str                  -> 明确声明返回字符串
# 为什么要返回字符串？因为工具结果要塞进对话消息里发给大模型，
# 大模型只读文本，DataFrame 对象塞进去会报错（我们真实踩过的 400 坑）
def read_csv(file_path: str, nrows: int = 5) -> str:
    """读取 CSV 文件，返回前 N 行预览，用于了解数据结构。file_path 是文件路径。"""

    # try / except 是"保险丝"结构：
    # try 里放"可能出错的危险操作"，一旦真出错，
    # 程序不会崩溃，而是跳进 except 里执行"补救措施"
    try:
        # 护栏：先校验路径安全（禁绝对路径 / 父目录穿越）
        safe_path(file_path)
        # pd.read_csv(路径) ：把 CSV 读成表格（DataFrame），存进 df
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        # FileNotFoundError = "找不到文件"错误
        # 返回一句人话而不是崩溃——模型收到这句话就知道要去问用户正确路径
        return f"错误：文件不存在: {file_path}"

    # df.empty ：判断表格是不是空的（0 行数据），返回 True/False
    if df.empty:
        return "错误：文件是空的，没有任何数据"

    # 组装返回文本，拆开看：
    # len(df)               -> 表格有多少行
    # list(df.columns)      -> df.columns 是所有列名，list() 转成列表
    # f"..."                -> f 字符串，{} 里可以放变量或表达式，直接拼进文字
    # df.head(nrows)        -> 取前 nrows 行（head = 头部）
    # .to_string(index=False) -> 把表格变成多行文本；index=False 表示
    #                            不要把行号 0,1,2... 也打出来（更干净）
    return (f"共 {len(df)} 行，列: {list(df.columns)}\n"
            + df.head(nrows).to_string(index=False))
