# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 统一错误类型与返回信封   #
# =================================== #

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """
    可预期错误：带稳定的错误码，前端据此展示文案.
    """

    def __init__(self, code: str, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def ok(data: Any = None) -> dict:
    return {"ok": True, "data": data}


def fail(error: AppError) -> dict:
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

    try:
        return ok(fn(*args, **kwargs))
    except AppError as exc:
        return fail(exc)
    except Exception as exc:  # noqa: BLE001 - 最外层兜底
        return fail(AppError("INTERNAL", "内部错误", f"{type(exc).__name__}: {exc}"))
