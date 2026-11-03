# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 工具注册入口             #
# =================================== #

from __future__ import annotations

from lspkit.platform.registry import Registry

from . import border, material, pearl


def build_registry() -> Registry:
    registry = Registry()
    registry.register(pearl.MANIFEST, pearl.HANDLERS, pearl.LEGACY)
    registry.register(border.MANIFEST, border.HANDLERS, border.LEGACY)
    registry.register(material.MANIFEST, material.HANDLERS, material.LEGACY)
    return registry
