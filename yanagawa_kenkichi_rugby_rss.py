import os
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime


# ============================================================
# 設定
# ============================================================

SOURCE_URL = (
    "https://news.google.com/rss/search"
    "?q=%E6%A2%81%E5%B7%9D%E8%B3%A2%E5%90%89+%E3%83%A9%E3%82%B0%E3%83%93%E3%83%BC"
    "&hl=ja"
    "&gl=JP"
    "&ceid=JP%3Aja"
)

OUTPUT_FILE = "yanagawa_kenkichi_rugby.xml"

FEED_TITLE = "梁川賢吉 ラグビー ニュース"
FEED_LINK = SOURCE_URL
FEED_DESCRIPTION = (
    "Google News「梁川賢吉 ラグビー」検索結果を利用した独自RSS"
)

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml,application/xml,text/xml,"
        "text/html;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


# ============================================================
# Google News RSS取得
# ============================================================

def fetch_google_news(retries=3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            print(f"取得 {attempt}/{retries}: {SOURCE_URL}")

            response = requests.get(
                SOURCE_URL,
                headers=HEADERS,
                timeout=30,
            )

            print(f"HTTP: {response.status_code}")
            print(f"取得バイト数: {len(response.content)}")

            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall("./channel/item")

            print(f"Google News記事数: {len(items)}")

            return items

        except Exception as e:
            last_error = e
            print(f"取得失敗: {repr(e)}")

            if attempt < retries:
                print("10秒待って再試行します")
                time.sleep(10)

    raise RuntimeError(
        f"{retries}回とも取得に失敗しました: {last_error}"
    )


# ============================================================
# Google News item解析
# ============================================================

def parse_google_items(items):
    articles = []
    seen = set()

    for item in items:
        title = (
            item.findtext("title", "")
            or ""
        ).strip()

        link = (
            item.findtext("link", "")
            or ""
        ).strip()

        pub_date = (
            item.findtext("pubDate", "")
            or ""
        ).strip()

        description = (
            item.findtext("description", "")
            or ""
        ).strip()

        source_tag = item.find("source")

        source = ""

        if source_tag is not None:
            source = (
                source_tag.text or ""
            ).strip()

        guid = (
            item.findtext("guid", "")
            or ""
        ).strip()

        if not title or not link:
            continue

        # 完全に同一のURLだけ重複排除
        if link in seen:
            continue

        seen.add(link)

        try:
            dt = parsedate_to_datetime(pub_date)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

        except Exception:
            print(f"日付解析失敗のため除外: {title}")
            continue

        if not guid:
            guid = hashlib.sha256(
                link.encode("utf-8")
            ).hexdigest()

        articles.append(
            {
                "title": title,
                "link": link,
                "pubDate": format_datetime(dt),
                "datetime": dt,
                "description": description,
                "source": source,
                "guid": guid,
            }
        )

    articles.sort(
        key=lambda x: x["datetime"],
        reverse=True,
    )

    return articles


# ============================================================
# 既存RSS読み込み
# ============================================================

def load_existing_items():
    existing = {}

    if not os.path.exists(OUTPUT_FILE):
        return existing

    try:
        tree = ET.parse(OUTPUT_FILE)
        root = tree.getroot()

        for item in root.findall("./channel/item"):
            link = (
                item.findtext("link", "")
                or ""
            ).strip()

            if not link:
                continue

            title = (
                item.findtext("title", "")
                or ""
            ).strip()

            pub_date = (
                item.findtext("pubDate", "")
                or ""
            ).strip()

            description = (
                item.findtext("description", "")
                or ""
            ).strip()

            guid = (
                item.findtext("guid", "")
                or ""
            ).strip()

            source = (
                item.findtext("source", "")
                or ""
            ).strip()

            existing[link] = {
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "description": description,
                "source": source,
                "guid": guid,
            }

    except Exception as e:
        print(f"既存RSSの読み込みに失敗: {repr(e)}")

    return existing


# ============================================================
# GUID
# ============================================================

def make_guid(link):
    return hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()


# ============================================================
# RSS生成
# ============================================================

def build_rss(current_articles, existing_items):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title",
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link",
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description",
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language",
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(JST)
    )

    merged = {}

    # 過去に取得済みの記事を保持
    for link, item in existing_items.items():
        merged[link] = {
            "title": item["title"],
            "link": link,
            "pubDate": item["pubDate"],
            "description": item["description"],
            "source": item["source"],
            "guid": (
                item["guid"]
                or make_guid(link)
            ),
        }

    # 今回取得した記事を追加・更新
    for article in current_articles:
        link = article["link"]

        merged[link] = {
            "title": article["title"],
            "link": link,
            "pubDate": article["pubDate"],
            "description": article["description"],
            "source": article["source"],
            "guid": (
                article["guid"]
                or make_guid(link)
            ),
        }

    # 公開日時順
    def sort_key(item):
        try:
            dt = parsedate_to_datetime(
                item["pubDate"]
            )
            return dt.timestamp()

        except Exception:
            return 0

    sorted_items = sorted(
        merged.values(),
        key=sort_key,
        reverse=True,
    )

    # RSS item生成
    for article in sorted_items:
        item = ET.SubElement(
            channel,
            "item",
        )

        ET.SubElement(
            item,
            "title",
        ).text = article["title"]

        ET.SubElement(
            item,
            "link",
        ).text = article["link"]

        ET.SubElement(
            item,
            "description",
        ).text = article["description"]

        ET.SubElement(
            item,
            "pubDate",
        ).text = article["pubDate"]

        if article["source"]:
            ET.SubElement(
                item,
                "source",
            ).text = article["source"]

        guid = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false",
            },
        )

        guid.text = article["guid"]

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    return len(sorted_items)


# ============================================================
# メイン
# ============================================================

def main():
    print("=" * 70)
    print("梁川賢吉 ラグビー ニュース Google News RSS")
    print("=" * 70)

    existing_items = load_existing_items()

    print(f"既存RSS件数: {len(existing_items)}")

    try:
        google_items = fetch_google_news()

        current_articles = parse_google_items(
            google_items
        )

    except Exception as e:
        print()
        print(f"エラー: {repr(e)}")
        print(
            "RSSは更新せず、既存ファイルを保持します"
        )
        raise

    print()
    print(
        f"今回取得した記事数: {len(current_articles)}"
    )

    print()
    print("最新30件:")

    for i, article in enumerate(
        current_articles[:30],
        1,
    ):
        try:
            dt = parsedate_to_datetime(
                article["pubDate"]
            )

            date_text = dt.astimezone(
                JST
            ).strftime("%Y-%m-%d %H:%M")

        except Exception:
            date_text = article["pubDate"]

        print(
            f"{i:2d}. "
            f"{date_text} "
            f"{article['title']}"
        )

        if article["source"]:
            print(
                f"    配信元: {article['source']}"
            )

        print(
            f"    {article['link']}"
        )

    existing_links = set(
        existing_items.keys()
    )

    new_articles = [
        article
        for article in current_articles
        if article["link"] not in existing_links
    ]

    print()
    print(f"新規記事数: {len(new_articles)}")

    total = build_rss(
        current_articles,
        existing_items,
    )

    print(f"保存完了: {OUTPUT_FILE}")
    print(f"RSS総件数: {total}")


if __name__ == "__main__":
    main()