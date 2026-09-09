# ============ 导入部分 ============

import os
import uuid
import pandas as pd

import matplotlib          # 画图库
# use("Agg")：切换到"无窗口模式"——不弹图窗，直接存文件
# 服务器上没有屏幕，弹窗会直接报错，所以必须在 import pyplot 之前设置
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # 引入"画笔"，小名 plt

from langchain_core.tools import tool

from .guard import safe_path

# ============ 全局字体设置（解决中文变方框） ============
# 列表里写了两个字体：优先用第一个，电脑上没有就用第二个
# macOS 有 "PingFang SC"（苹方），Windows 有 "Microsoft YaHei"（微软雅黑）
plt.rcParams["font.sans-serif"] = ["PingFang SC", "Microsoft YaHei"]
# 中文缺"数学负号"字形，改用普通减号显示负数
plt.rcParams["axes.unicode_minus"] = False

# 启动时就建好图表输出文件夹（exist_ok 防止重复创建报错）
os.makedirs("charts", exist_ok=True)


@tool
def make_chart(csv_path: str, chart_type: str, x: str, y: str = "") -> str:
    """画图并保存 PNG。chart_type 支持 line(折线)/bar(柱状)/scatter(散点)/hist(直方图)/pie(饼图)。
    hist/pie 不需要 y。x、y 是 CSV 的列名。返回保存路径。"""
    # ---------- 安全护栏①：图表类型白名单 ----------
    if chart_type not in ("line", "bar", "scatter", "hist", "pie"):
        return "错误：chart_type 必须是 line/bar/scatter/hist/pie"

    # 护栏：先校验路径安全（禁绝对路径 / 父目录穿越）
    try:
        safe_path(csv_path)
    except ValueError as e:
        return f"错误：{e}"
    df = pd.read_csv(csv_path)
    # ---------- 安全护栏②：列名存在性校验 ----------
    # 条件拆解：x 不存在，或者（需要 y 的图型却没有合法 y）-> 拒绝
    # hist 直方图、pie 饼图都可以只靠 x 一列（饼图不传 y 时按 x 计数），所以豁免
    need_y = chart_type not in ("hist", "pie")
    if x not in df.columns or (need_y and y not in df.columns):
        return f"错误：列不存在，可用列 {list(df.columns)}"

    # 创建画纸(fig)和坐标系(ax)
    # 饼图必须用正方形画布，否则 8x5 的矩形会让正圆在浏览器里被拉成椭圆
    figsize = (6, 6) if chart_type == "pie" else (8, 5)
    fig, ax = plt.subplots(figsize=figsize)

    # 四种图各一段画法（此时类型已经过白名单，放心处理）
    if chart_type == "line":          # 折线图：看趋势
        ax.plot(df[x], df[y], marker="o")      # marker="o" 每个点画圆圈
    elif chart_type == "bar":         # 柱状图：比大小
        # astype(str) 把横轴转文字，防止数字横轴显示错乱
        ax.bar(df[x].astype(str), df[y])
    elif chart_type == "scatter":     # 散点图：看两列的相关性
        ax.scatter(df[x], df[y])
    elif chart_type == "pie":         # 饼图：看占比
        sizes = df.groupby(x)[y].sum() if y else df[x].value_counts()
        ax.pie(sizes, labels=[str(i) for i in sizes.index],
               autopct="%1.1f%%", startangle=90)
        ax.axis("equal")              # 正圆
    else:                             # 走到这里必然是 hist（白名单保证了）
        ax.hist(df[x], bins=20)                # bins=20：把数据分 20 个区间统计

    # 标题：f 字符串里嵌套条件表达式——y 非空才显示 " vs y"
    ax.set_title(f"{chart_type}: {x}" + (f" vs {y}" if y else ""))
    # 倾斜 30 度显示横轴文字，防止挤成一团；ha="right" 让文字右端对准刻度
    plt.xticks(rotation=30, ha="right")
    # 自动调整边距，防止标题被裁掉
    plt.tight_layout()

    # 拼出保存路径：charts/chart_bar_region.png 这样的形式
    # os.path.join 用系统正确的分隔符拼路径（Windows 是 \ ，Mac/Linux 是 /）
    # 唯一命名：追加 uuid 前 8 位，避免同名覆盖导致前端漏图（修复目录 diff 竞态）
    path = os.path.join("charts", f"chart_{chart_type}_{x}_{uuid.uuid4().hex[:8]}.png")
    # dpi=120：每英寸 120 像素点，清晰度和文件大小的平衡点
    fig.savefig(path, dpi=120)
    # 必须关闭画布释放内存，否则程序画几百张图后会越来越慢
    plt.close(fig)

    # 返回路径给模型——模型拿到路径可以告诉用户图存哪里了
    return f"图表已保存: {path}"
