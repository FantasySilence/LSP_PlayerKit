# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 统一错误类型与返回信封   #
# =================================== #
# 本文件职责：定义全项目唯一的“可预期错误”异常 AppError，以及前后端约定的返回信封。
# 所有对外 API 都从这里取信封：成功 {ok: True, data}，失败 {ok: False, error}。

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """
    可预期错误：带稳定的错误码，前端据此展示文案.
    """

    def __init__(self, code: str, message: str, detail: str = "") -> None:
        """code：稳定的错误码（前端按它找文案）；message：给人看的中文说明；detail：可选排查细节。"""

        super().__init__(message)
        # 三个字段分工不同：code 给程序判断，message 给人看，detail 留给排查
        self.code = code
        self.message = message
        self.detail = detail


def ok(data: Any = None) -> dict:
    """构造成功信封：前端只看 ok 字段判断成败，data 需可被 JSON 序列化。"""

    return {"ok": True, "data": data}


def fail(error: AppError) -> dict:
    """把 AppError 转成失败信封，字段名与前端拿到的 error 对象一一对应。"""

    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "detail": error.detail,
        },
    }


def envelope(fn, *args, **kwargs) -> dict:
    """
    执行并包成信封，任何异常都不外泄 traceback.
    """

    # AppError 属于“可预期错误”，原样透出；其它异常统一降级成 INTERNAL 文案
    try:
        return ok(fn(*args, **kwargs))
    except AppError as exc:
        return fail(exc)
    except Exception as exc:  # noqa: BLE001 - 最外层兜底
        return fail(AppError("INTERNAL", "内部错误", f"{type(exc).__name__}: {exc}"))
