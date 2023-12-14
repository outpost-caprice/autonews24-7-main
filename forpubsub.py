from google.cloud import pubsub_v1
from flask import escape
import json
import os
import functions_framework

# Pub/Subクライアントの初期化
publisher = pubsub_v1.PublisherClient()
# トピックの指定（プロジェクトIDとトピック名を適切に設定してください）
topic_name = 'projects/your-project-id/topics/your-topic-name'

@functions_framework.http
async def process_inoreader_update(request):
    request_json = request.get_json()

    if request_json and 'items' in request_json:
        for item in request_json['items']:
            article_content = escape(item.get('content', ''))
            article_url = escape(item.get('url', ''))
            article_tags = item.get('tags', [])

            # Pub/Subにパブリッシュするためのメッセージを作成
            message = json.dumps({
                'content': article_content,
                'url': article_url,
                'tags': article_tags
            })

            # メッセージをパブリッシュ
            publisher.publish(topic_name, message.encode('utf-8'))

        return '記事の更新を受け取りました', 200
    else:
        return '適切なデータがリクエストに含まれていません', 400
