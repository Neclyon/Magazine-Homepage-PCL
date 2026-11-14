"""中文 Minecraft Wiki 特色条目数据源"""
import json
from html import escape
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

from homepagebuilder.interfaces import script

WIKI_API_URL = "https://zh.minecraft.wiki/api.php"
BASE_WIKI_URL = "https://zh.minecraft.wiki"
FEATURED_ARTICLE_SELECTOR = "div.mp-inline-sections > div.mp-left > div:nth-child(5)"
FEATURED_IMAGE_SELECTOR = "div.mp-featured-img img"
USER_AGENT = "PCL2MagazineHomepageBot/3.0"

_fields: Dict[str, str] = {}


def _extract_links(html: str) -> Dict[str, str]:
    """提取 HTML 中所有带 title 的站内链接"""
    import re

    links = {}
    pattern = r'<a href="(?P<url>.*?)" title="(?P<text>.*?)"'
    for match in re.finditer(pattern, html):
        links[match.group("text")] = BASE_WIKI_URL + match.group("url")
    return links


def _link_xaml(text: str, url: str) -> str:
    return (
        '<Underline><local:MyTextButton EventType="打开网页" '
        f'EventData="{escape(url, quote=True)}" Margin="0,0,0,-8">{escape(text)}</local:MyTextButton></Underline>'
    )


def _list_items(article) -> List[str]:
    """把特色条目正文拆成一句一条的 ListItem"""
    raw_text = article.text.lstrip("\n特色条目").strip()
    sentences = [s.strip() for s in raw_text.split("。") if s.strip()]
    # 长词优先，避免「铜箱子」被「箱子」先替换掉
    links = sorted(
        _extract_links(str(article)).items(), key=lambda kv: len(kv[0]), reverse=True
    )

    items = []
    for sentence in sentences:
        # 片段列表：先整句当文本，再逐条链接切开，避免嵌套标签
        parts: List[Tuple[str, str]] = [("text", sentence + "。")]
        for link_text, link_url in links:
            hyperlink = _link_xaml(link_text, link_url)
            new_parts: List[Tuple[str, str]] = []
            for kind, content in parts:
                if kind != "text":
                    new_parts.append((kind, content))
                    continue
                pieces = content.split(link_text)
                for index, piece in enumerate(pieces):
                    if piece:
                        new_parts.append(("text", piece))
                    if index < len(pieces) - 1:
                        new_parts.append(("xaml", hyperlink))
            parts = new_parts

        body = "".join(
            content if kind == "xaml" else escape(content) for kind, content in parts
        )
        items.append(
            f'<ListItem><Paragraph Foreground="{{DynamicResource ColorBrush1}}">{body}</Paragraph></ListItem>'
        )

    # 最后一句是「阅读更多」，去掉
    if items:
        items.pop()
    return items


def _load() -> Dict[str, str]:
    if _fields:
        return _fields
    print("正在从 Minecraft Wiki API 获取数据...")
    response = requests.get(
        WIKI_API_URL,
        params={"action": "parse", "format": "json", "page": "Minecraft_Wiki"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    dom = BeautifulSoup(json.loads(response.text)["parse"]["text"]["*"], "html.parser")

    article = dom.select_one(FEATURED_ARTICLE_SELECTOR)
    if article is None:
        raise ValueError("无法在 Wiki 页面中找到特色条目元素，选择器可能已失效")

    items = _list_items(article)
    links = _extract_links(str(article))
    topic, link = next(iter(links.items())) if links else ("未知主题", BASE_WIKI_URL)

    image = ""
    image_tag = dom.select_one(FEATURED_IMAGE_SELECTOR)
    if image_tag and image_tag.get("src"):
        image = (BASE_WIKI_URL + image_tag["src"]).replace("&", "&amp;")

    _fields.update(
        topic=escape(topic),
        image=image,
        link=escape(link, quote=True),
        intro=items[0] if len(items) > 0 else "",
        intro_2=items[1] if len(items) > 1 else "",
        body="\n".join(items[2:]) if len(items) > 2 else "",
    )
    return _fields


@script("Wiki")
def wiki_field(field, context=None, **kwargs):
    """取特色条目的某个字段：topic / image / link / intro / intro_2 / body"""
    try:
        return _load().get(field, "")
    except Exception as error:  # 抓取失败时留空，不要中断整个构建
        print(f"[WARN] Wiki 数据获取失败: {error}")
        return ""
