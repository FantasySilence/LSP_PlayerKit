# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮设置 schema        #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=2,
    groups=[
        Group(
            "basic",
            "pearl.settings.basic",
            [
                Field("maxTnt", "pearl.field.maxTnt", "int", D["maxTnt"], 1, 100000, 10, unit="个"),
                Field("tntPerUnit", "pearl.field.tntPerUnit", "int", D["tntPerUnit"], 1, 4096, 10, unit="个/阵列"),
                Field("originX", "pearl.field.originX", "float", D["originX"], digits=4),
                Field("originZ", "pearl.field.originZ", "float", D["originZ"], digits=4),
                Field("ejectionAvailable", "pearl.field.ejectionAvailable", "bool", D["ejectionAvailable"]),
            ],
        ),
        Group(
            "flat",
            "pearl.settings.flat",
            [
                Field("flat.xzMotion", "pearl.field.flat.xzMotion", "float", D["flat"]["xzMotion"], digits=10),
                Field("flat.yMotion", "pearl.field.flat.yMotion", "float", D["flat"]["yMotion"], digits=10),
                Field("flat.yInitMotion", "pearl.field.flat.yInitMotion", "float", D["flat"]["yInitMotion"], digits=10),
                Field("flat.yInitPosition", "pearl.field.flat.yInitPosition", "float", D["flat"]["yInitPosition"], digits=4),
            ],
        ),
        Group(
            "eject",
            "pearl.settings.eject",
            [
                Field("eject.xzMotion", "pearl.field.eject.xzMotion", "float", D["eject"]["xzMotion"], digits=10),
                Field("eject.yMotion", "pearl.field.eject.yMotion", "float", D["eject"]["yMotion"], digits=10),
                Field("eject.yInitMotion", "pearl.field.eject.yInitMotion", "float", D["eject"]["yInitMotion"], digits=10),
                Field("eject.yInitPosition", "pearl.field.eject.yInitPosition", "float", D["eject"]["yInitPosition"], digits=4),
            ],
        ),
    ],
)
