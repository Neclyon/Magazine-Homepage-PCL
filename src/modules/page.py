"""页面级脚本：卡片渲染、版本号与更新时间"""
import datetime
import hashlib
import os
import struct
import time
from pathlib import Path
from typing import Dict

from homepagebuilder.interfaces import script

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ICON_DIR = ASSETS_DIR / "icons"
_icons: Dict[str, str] = {}


def make_version_id() -> str:
    """按 日期:时间戳哈希前7位 生成版本号"""
    date = datetime.datetime.now().strftime("%y%m%d")
    digest = hashlib.md5(struct.pack("<f", time.time())).hexdigest()
    return f"{date}:{digest[:7]}"


@script("Card")
def render_card(card_ref, context=None, **kwargs):
    """按名称渲染卡片库中的另一张卡片"""
    project = getattr(context, "project", None)
    if project is None or project.base_library is None:
        print("[WARN] 工程未就绪，无法渲染卡片")
        return ""
    try:
        card = project.base_library.get_card(card_ref, False)
    except KeyError:
        print(f"[WARN] 卡片 {card_ref} 不存在")
        return ""
    return context.builder.template_manager.build(card, context)


@script("VersionID")
def version_id(context=None, **kwargs):
    """主页版本号，构建脚本会通过环境变量传入，以便写进 ini"""
    return os.environ.get("MAGAZINE_VERSION_ID") or make_version_id()


@script("UpdatedAt")
def updated_at(context=None, **kwargs):
    return f"最后更新：{datetime.datetime.now():%Y-%m-%d}"


@script("Icon")
def icon(name, context=None, **kwargs):
    """读取 assets/icons/<name>.path 里的图标路径数据"""
    if name in _icons:
        return _icons[name]
    try:
        data = (ICON_DIR / f"{name}.path").read_text(encoding="utf-8").strip()
    except OSError as error:
        print(f"[WARN] 图标 {name} 读取失败: {error}")
        data = ""
    _icons[name] = data
    return data


@script("Text")
def text(name, context=None, **kwargs):
    """读取 assets/<name>.txt，换行转成 &#10; 才能放进 XAML 属性"""
    try:
        data = (ASSETS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip("\n")
    except OSError as error:
        print(f"[WARN] 文本 {name} 读取失败: {error}")
        return ""
    return data.replace("\n", "&#10;")
