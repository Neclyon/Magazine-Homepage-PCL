"""历史上的今天，数据取自百度百科"""
import json
import re
from datetime import datetime
from html import escape

import requests

from homepagebuilder.interfaces import script

HTTP_OK = range(200, 300)
DEFAULT_LOGO = "pack://application:,,,/images/Blocks/RedstoneLampOn.png"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _strip_html(text: str) -> str:
    return re.sub("<[^<]+?>", "", text)


def _grab(lang: str = "zh-CN"):
    now = datetime.now()
    month = f"{now.month:02d}"
    day = f"{now.day:02d}"
    response = requests.get(
        url=f"https://baike.baidu.com/cms/home/eventsOnHistory/{month}.json",
        headers={
            "referer": "https://www.baidu.com",
            "User-Agent": USER_AGENT,
            "Accept-Language": lang,
            "Accept": "text/html",
        },
        timeout=15,
    )
    if response.status_code not in HTTP_OK:
        raise KeyError(f"远程服务器返回错误:{response.status_code}")
    meta = json.loads(response.content.decode("utf-8"))
    data = meta[month][f"{month}{day}"]
    for item in data:
        item["title"] = _strip_html(item["title"])
        item["desc"] = _strip_html(item["desc"])
    return data


@script("HistoryItems")
def history_items(context=None, **kwargs):
    try:
        days = _grab()
    except Exception as error:
        print(f"[WARN] 历史上的今天获取失败: {error}")
        return ""

    code = ""
    for day in days:
        card = {
            "title": escape(day["title"]),
            "info": escape(day["desc"]),
            "link": escape(day.get("link", ""), quote=True),
            # 有封面图就用封面缩略图，没有就用固定的灯，避免灯亮灭看着像有含义
            "logo": escape(day.get("pic_calendar") or DEFAULT_LOGO, quote=True)
            if day.get("cover")
            else DEFAULT_LOGO,
        }
        code += context.components["HistoryItem"].toxaml(card, context)
    return code
