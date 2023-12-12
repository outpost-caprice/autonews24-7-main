import functions_framework
import threading
import flask
from markupsafe import escape
import requests
import json
import os
from backoff import expo, on_exception
from bs4 import BeautifulSoup
import traceback
import langchain
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import CharacterTextSplitter
from langchain.docstore.document import Document
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64  
import logging  
from openai import OpenAI


def summarize_content(content):
    try:
        # テキストを分割するためのスプリッターを設定
        text_splitter = CharacterTextSplitter(
            chunk_size=5000,  # 分割するチャンクのサイズ
            chunk_overlap=100,  # チャンク間のオーバーラップ
            separator="\n"    # 文章を分割するためのセパレータ
        )
        texts = text_splitter.create_documents([content])

        # 要約チェーンを実行
        result = refine_chain({"input_documents": texts}, return_only_outputs=True)

        # 要約されたテキストを結合して返す
        return result["output_text"]
    except Exception as e:
        logging.error(f"要約処理中にエラーが発生しました: {e}")
        traceback.print_exc()
        return None
  
OPENAI_api_key = os.getenv('OPENAI_API_KEY')

# プロンプトテンプレートの定義
refine_first_template = """以下の文章は、長い記事をチャンクで分割したものの冒頭の文章です。それを留意し、次の文章の内容と結合することを留意したうえで以下の文章をテーマ毎にまとめて下さい。
------
{text}
------
"""


refine_template = """下記の文章は、長い記事をチャンクで分割したものの一部です。また、「{existing_answer}」の内容はこれまでの内容の要約である。そして、「{text}」はそれらに続く文章です。それを留意し、次の文章の内容と結合することを留意したうえで以下の文章をテーマ毎にまとめて下さい。できる限り多くの情報を残しながら日本語で要約して出力してください。
------
{existing_answer}
{text}
------
"""
refine_first_prompt = PromptTemplate(input_variables=["text"],template=refine_first_template)
refine_prompt = PromptTemplate(input_variables=["existing_answer", "text"],template=refine_template)
llm = ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo-16k")
# 要約チェーンの初期化
refine_chain = load_summarize_chain(
    llm=llm,
    chain_type="refine",
    question_prompt=refine_first_prompt,
    refine_prompt=refine_prompt
)


# OpenAI API呼び出し関数
def openai_api_call(model, temperature, messages, max_tokens, response_format):
    client = OpenAI(api_key=OPENAI_api_key)  # 非同期クライアントのインスタンス化
    try:
        # OpenAI API呼び出しを行う
        response = client.chat.completions.create(model=model, temperature=temperature, messages=messages, max_tokens=max_tokens, response_format=response_format)
        return response.choices[0].message.content  # 辞書型アクセスから属性アクセスへ変更
    except Exception as e:
        logging.error(f"OpenAI API呼び出し中にエラーが発生しました: {e}")
        raise

# URLからコンテンツを取得する関数
def fetch_content_from_url(url):
    try:
        logging.info(f"URLからコンテンツの取得を開始: {url}")

        # ユーザーエージェントを設定
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

        response = requests.get(url, headers=headers, timeout=100)
        content = response.text

        logging.info(f"URLからコンテンツの取得が成功: {url}")
        return content

    except Exception as e:
        logging.warning(f"URLからのコンテンツ取得中にエラーが発生しました: {e}")
        return None

#　コンテンツをパースする関数 
def parse_content(content):
    try:
        # HTMLコンテンツをBeautiful Soupでパース
        soup = BeautifulSoup(content, 'html.parser')

        # ヘッダーとフッターを削除（もし存在する場合）
        header = soup.find('header')
        if header:
            header.decompose()

        footer = soup.find('footer')
        if footer:
            footer.decompose()

        # JavaScriptとCSSを削除
        for script in soup(["script", "style"]):
            script.decompose()

        # HTMLタグを削除してテキストのみを取得
        text = soup.get_text()

        # 改行をスペースに置き換え
        parsed_text = ' '.join(text.split())

        # パースされたテキストの文字数を出力
        print(f"パースされたテキストの文字数: {len(parsed_text)}")

        return parsed_text

    except Exception as e:
        logging.warning(f"コンテンツのパース中にエラーが発生しました: {e}")
        return None

# メインのタスクの部分
def heavy_task(article_title, article_url):
    try:
        # URLからコンテンツを取得し、パースする
        content = fetch_content_from_url(article_url)
        if content is None:
            logging.warning(f"コンテンツが見つからない: {article_url}")
            return

        parsed_content = parse_content(content)
        if parsed_content is None:
            logging.warning(f"コンテンツのパースに失敗: {article_url}")
            return

        # parsed_contentが10000文字以下なら直接OpenAIに渡す
        if len(parsed_content) <= 10000:
            final_summary = openai_api_call(
                "gpt-3.5-turbo-1106",
                0,
                [
                    {"role": "system", "content": "あなたは優秀な要約アシスタントです。提供された文章の内容を出来る限り残しつつ、日本語で要約してください。"},
                    {"role": "user", "content": parsed_content}
                ],
                4000,
                {"type": "text"}
            )
            logging.info(f"要約の洗練に成功: {article_url}")
            if not final_summary:
                logging.warning(f"要約の洗練に失敗: {article_url}")
                return None
        else:
            # 初期要約を生成
            preliminary_summary = summarize_content(parsed_content)
            if preliminary_summary is None:
                logging.warning(f"コンテンツの要約に失敗: {article_url}")
                return

            # OpenAIを使用してさらに要約を洗練
            final_summary = openai_api_call(
                "gpt-4-1106-preview",
                0,
                [
                    {"role": "system", "content": "あなたは優秀な要約アシスタントです。提供された文章の内容を出来る限り残しつつ、日本語で要約してください。テーマごとに分割してリスト形式にすることは行わないでください。"},
                    {"role": "user", "content": preliminary_summary}
                ],
                4000,
                {"type": "text"}
            )
            logging.info(f"要約の洗練に成功: {article_url}")

            if not final_summary:
                logging.warning(f"要約の洗練に失敗: {article_url}")
                return None
        
        # リード文生成のためのOpenAI API呼び出し
        try:
            lead_sentence = openai_api_call(
            "gpt-4",
            0,
            [
                {"role": "system", "content": "あなたは優秀なライターです。この要約のリード文を簡潔に1～2センテンス程度で新聞の見出しのような口調で作成してください。"},
                {"role": "user", "content": final_summary}
            ],
            80,  # リード文の最大トークン数を適宜設定
            {"type": "text"}
            )
            # 成功の際のログ出力
            logging.info(f"リード文の生成に成功: {article_url}")
            if not lead_sentence:
                logging.warning(f"リード文の生成に失敗: {article_url}")
                lead_sentence = "リード文の生成に失敗しました。"
        except Exception as e:
            logging.error(f"リード文生成中にエラーが発生: {e}")
            lead_sentence = "リード文の生成中にエラーが発生しました。"

        
        # IFTTT Webhooks URL
        YOUR_EVENT_NAME = os.getenv('YOUR_EVENT_NAME')
        YOUR_WEBHOOKS_KEY = os.getenv('YOUR_WEBHOOKS_KEY')
        ifttt_url = f"https://maker.ifttt.com/trigger/{YOUR_EVENT_NAME}/with/key/{YOUR_WEBHOOKS_KEY}"

            # 送信するデータ
        ifttt_data = {
        "value1": final_summary,
        "value2": lead_sentence,
        "value3": f"<p>from <a href=\"{article_url}\" target=\"_blank\">{article_title}</a>.</p>"
        }


            # POSTリクエストを送信
        try:
            response = requests.post(ifttt_url, json=ifttt_data)
            if response.status_code == 200:
                logging.info("IFTTTへのデータ送信に成功しました")
            else:
                logging.error(f"IFTTTへのデータ送信に失敗しました: ステータスコード {response.status_code}")
        except Exception as e:
                logging.error(f"IFTTTへのデータ送信中にエラーが発生しました: {e}")

    except Exception as e:
        logging.error(f"{article_url} の処理中にエラーが発生: {e}")
        traceback.print_exc()

@functions_framework.http
def process_inoreader_update(request):
    request_json = request.get_json()

    if request_json and 'items' in request_json:
        for item in request_json['items']:
            article_title = escape(item.get('title', ''))
            article_href = escape(item['canonical'][0]['href']) if 'canonical' in item and item['canonical'] else ''


            # news.google.comを含むURLをスキップする
            if 'news.google.com' in article_href:
                logging.info(f"news.google.comのURLはスキップされます: {article_href}")
                continue

            if article_title and article_href:
                # 重い処理を非同期で実行するために別のスレッドを起動
                thread = threading.Thread(target=heavy_task, args=(article_title, article_href))
                thread.start()
        # メインスレッドでは即座に応答を返す
        return '記事の更新を受け取りました', 200
    else:
        return '適切なデータがリクエストに含まれていません', 400
        
         
