import openai
from openai import AsyncOpenAI
import logging
import random
import os
import asyncio

OPENAI_api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(OPENAI_api_key)

async def openai_api_call_async(model, temperature, messages, max_tokens, response_format):
    try:
        response = await client.chat.completions.create(model=model, temperature=temperature, messages=messages, max_tokens=max_tokens, response_format=response_format)
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI API呼び出し中にエラーが発生しました: {e}")
        raise

def select_random_persona(personas):
    random_number = random.randint(1, 10)
    return personas[random_number]

async def generate_opinion_async(content):
    try:
        personas = {
            # ここに既存のペルソナの辞書を入れます
        }
        # ランダムに3つのペルソナを選択
        selected_personas = [select_random_persona(personas) for _ in range(3)]

        opinions = []
        for full_persona in selected_personas:
            persona_name = full_persona.split(" - ")[0]
            opinion = await openai_api_call_async(
                "gpt-3.5-turbo-1106",
                0.6,
                [
                    {"role": "system", "content": f'あなたは"""{full_persona}"""です。提供された文章の内容に対し日本語で意見を生成してください。'},
                    {"role": "user", "content": content}
                ],
                2000,
                {"type": "text"}
            )
            opinions.append(f'{persona_name}: {opinion}')
        return opinions
    except Exception as e:
        logging.error(f"意見生成中にエラーが発生: {e}")
        return [f"エラーが発生しました: {e}"]

# 非同期メイン関数を呼び出す。Function設定
async def main():
    content = "ここに意見を求める内容を入れます"
    opinions = await generate_opinion_async(content)
    for opinion in opinions:
        print(opinion)

# 非同期処理の実行
asyncio.run(main())