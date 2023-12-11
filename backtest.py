import feedparser

# RSSフィードのURL
feed_url = "https://www.inoreader.com/stream/user/1005267007/tag/AI"

# フィードをパース
feed = feedparser.parse(feed_url)

# 最新の3件の記事のタイトルとURLを表示
for entry in feed.entries[:3]:
    print("タイトル:", entry.title)
    print("URL:", entry.link)
    print()
