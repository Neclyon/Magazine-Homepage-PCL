"""最新版本新闻卡片的数据源"""
import requests

from homepagebuilder.interfaces import script

NEWS_API_URL = "https://news.bugjump.net/apis/versions/latest-card"


def _with_margin(xaml: str, margin: str = "0,5") -> str:
    """新闻卡片由 API 直接给出，根元素没有 Margin 时补一个，和相邻卡片隔开"""
    head, sep, rest = xaml.partition(">")
    if not sep or "Margin=" in head:
        return xaml
    return f'{head.rstrip()} Margin="{margin}"{sep}{rest}'


@script("NewsCard")
def news_card(context=None, **kwargs):
    print("正在请求新闻主页 API...")
    try:
        response = requests.get(NEWS_API_URL, timeout=10)
        print(f"新闻 API 状态码: {response.status_code}")
        if response.ok and response.text.strip():
            return _with_margin(response.text.strip())
    except requests.exceptions.RequestException as error:
        print(f"[WARN] 新闻 API 请求异常: {error}")
    return context.components["NewsError"].toxaml({}, context)
