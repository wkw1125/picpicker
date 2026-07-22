"""应用版本信息。"""

try:
    from picpicker._build_version import VERSION
except ImportError:
    VERSION = "开发版本"

__all__ = ["VERSION"]
