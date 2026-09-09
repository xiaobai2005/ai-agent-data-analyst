# ============ 共享安全护栏：路径校验 ============
import os


def safe_path(path: str, base_dir: str | None = None) -> str:
    """校验文件路径安全：
    - 禁止绝对路径
    - 禁止 '..' 父目录穿越
    - 若给定 base_dir，则必须把路径限制在 base_dir 之内
    返回归一化后的相对路径；不合法则抛出 ValueError。

    注意：不能先对 Windows 路径调用 os.path.normpath 再按 '/' 切分
    （normpath 会把 '/' 转成 '\\'，导致 '..' 检测失效），
    因此这里先统一分隔符再按层级切分判断。
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("路径为空")

    norm = path.replace("\\", "/")
    # 注意：Windows 下 os.path.isabs('/etc/passwd') 返回 False（它只认盘符与反斜杠），
    # 因此这里额外把以 '/' 开头的 POSIX 风格绝对路径一并拦截。
    if os.path.isabs(path) or norm.startswith("/"):
        raise ValueError("禁止使用绝对路径")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ValueError("禁止路径穿越 (..)")

    if base_dir is not None:
        base_abs = os.path.abspath(base_dir)
        cand_abs = os.path.abspath(os.path.join(base_dir, *parts))
        if cand_abs != base_abs and not cand_abs.startswith(base_abs + os.sep):
            raise ValueError("路径越出允许目录")

    return os.path.join(*parts) if parts else ""
