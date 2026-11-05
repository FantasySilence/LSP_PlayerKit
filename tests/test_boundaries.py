# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 架构边界测试             #
# =================================== #

import ast
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "src" / "lspkit" / "tools"
TOOL_IDS = ("pearl", "border", "material", "puppet")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_tools_do_not_import_each_other():
    for tool in TOOL_IDS:
        for file in (TOOLS / tool).rglob("*.py"):
            imports = _imports(file)
            for other in TOOL_IDS:
                if other == tool:
                    continue
                for module in imports:
                    assert f"tools.{other}" not in module, f"{file} 跨界导入了 {module}"
                    assert f"lspkit.tools.{other}" not in module


def test_core_is_pure():
    for tool in TOOL_IDS:
        for file in (TOOLS / tool / "core").rglob("*.py"):
            imports = _imports(file)
            for module in imports:
                assert not module.startswith("lspkit.platform"), f"{file} 依赖了平台层 {module}"
                assert module not in ("os", "pathlib", "json"), f"{file} 访问了 IO 模块 {module}"
