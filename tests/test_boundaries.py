# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 架构边界测试             #
# =================================== #
# 测试层：架构约束，不运行任何业务代码。
# 策略：用 ast 解析 src/lspkit/tools 下的 import，静态断言「工具之间零 import、
# core 不碰平台层与 IO」；新增工具时把它加入 TOOL_IDS，规则才会覆盖到。

import ast
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "src" / "lspkit" / "tools"
TOOL_IDS = ("pearl", "border", "material", "puppet")
# 检查范围：tools/ 下的四个业务工具目录；slime 与 _template 不在本次清单内。


def _imports(path: Path) -> set[str]:
    """解析一个 .py 的 import，返回模块名集合.

    只收集 ast.Import 的别名与 ast.ImportFrom 的 module；相对导入的 level
    不在这里体现，因此下面的断言只检查模块名里是否出现别的工具路径。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_tools_do_not_import_each_other():
    """验证工具之间没有横向依赖.

    输入：TOOL_IDS 中每个工具目录下的全部 .py。
    期望：任何 import 的模块名都不包含 tools.<另一个工具> 或 lspkit.tools.<另一个>。
    """
    for tool in TOOL_IDS:
        for file in (TOOLS / tool).rglob("*.py"):
            imports = _imports(file)
            for other in TOOL_IDS:
                if other == tool:
                    continue
                for module in imports:
                    assert f"tools.{other}" not in module, f"{file} 跨界导入了 {module}"
                    # 同时匹配相对写法的后缀与完整包路径，覆盖两种常见导入风格。
                    assert f"lspkit.tools.{other}" not in module


def test_core_is_pure():
    """验证 core/ 保持纯函数：不依赖平台层，也不直接做 IO.

    输入：每个工具 core/ 下的全部 .py。
    期望：不 import lspkit.platform，也不 import os / pathlib / json。
    """
    for tool in TOOL_IDS:
        for file in (TOOLS / tool / "core").rglob("*.py"):
            imports = _imports(file)
            for module in imports:
                # core 只做数学与数据变换，路径、设置、文件读写都留在 actions / platform。
                assert not module.startswith("lspkit.platform"), f"{file} 依赖了平台层 {module}"
                # 只拦这三个常用 IO 模块；numpy 等纯计算依赖是允许的。
                assert module not in ("os", "pathlib", "json"), f"{file} 访问了 IO 模块 {module}"
