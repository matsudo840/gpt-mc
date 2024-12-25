import datetime
import logging
import os
import sys

import yaml
from mistletoe import Document
from mistletoe.block_token import CodeFence
from openai import OpenAI

from mcpi import minecraft

logging.basicConfig(filename='mcgpt.log', level=logging.INFO)


def load_config():
    """
    Loads the configuration from the 'config.yaml' file and sets the global variables accordingly.

    If the 'GENERATE_MODEL' key in the configuration is set to 'gpt-4', it forces the use of 'gpt-4-turbo-preview'
    as the value for the 'GENERATE_MODEL' key, since 'gpt-4' no longer supports json modes.

    Returns:
        None
    """
    with open("config.yaml", "r", encoding='utf-8') as conf:
        config_content = yaml.safe_load(conf)
        for key, value in config_content.items():
            globals()[key] = value


def askgpt(system_prompt: str, user_prompt: str, model_name: str, image_url: str = None, extra_messages=[]):
    """
    Interacts with ChatGPT using the specified prompts.

    Args:
        system_prompt (str): The system prompt.
        user_prompt (str): The user prompt.
        model_name (str): The model name to use.
        image_url (str, optional): The URL of the image to include in the prompt. Defaults to None.
        extra_messages (list, optional): List of previous messages to maintain the conversation context. Defaults to [].

    Returns:
        tuple: A tuple containing the response from ChatGPT and the updated list of messages.
    """
    client = OpenAI()

    logging.info("Initialized the OpenAI client.")

    # Define the messages for the conversation
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(extra_messages)

    if image_url is not None:
        messages.append({"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]})
    else:
        messages.append({"role": "user", "content": user_prompt})

    logging.info(f"askgpt: system {system_prompt}")
    logging.info(f"askgpt: user {user_prompt}")

    # Create a chat completion
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        timeout=120
    )

    logging.info(f"askgpt: response {response}")

    # Extract the assistant's reply
    assistant_reply = response.choices[0].message.content
    logging.info(f"askgpt: extracted reply {assistant_reply}")
    return assistant_reply, messages + [{"role": "assistant", "content": assistant_reply}]


def ask_dall_e(description: str):
    """
    Generates a design image using the DALL-E API.

    Args:
        description (str): The prompt or description for generating the image.

    Returns:
        str: The URL of the generated image.
    """
    client = OpenAI()

    logging.info("ask_dall_e: Generating design image using DALL-E API.")
    logging.info(f"dall_e description: {description}")

    response = client.images.generate(
        model="dall-e-3",
        prompt=description,
        size="1024x1024",
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url

    logging.info(f"ask_dall_e: Generated image URL {image_url}")

    return image_url


def get_code_blocks(text: str):
    """
    Extracts code blocks from the given text.

    Args:
        text (str): The input text containing code blocks.

    Returns:
        list: A list of code blocks extracted from the text.
    """
    # Parse the text as a Markdown document
    doc = Document(text)
    code_blocks = []
    # Extract code blocks from the document
    for token in doc.children:
        if isinstance(token, CodeFence):
            code_blocks.append(token.children[0].content)
    return "\n\n".join(code_blocks)


def main():

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"{current_time=}, session start")

    load_config()

    mc = minecraft.Minecraft.create()
    OpenAI.api_key = os.getenv('OPENAI_API_KEY')

    # Get the prompt from command line arguments
    prompt = sys.argv[1]
    mc.postToChat(f"Prompt: {prompt}")
    logging.info(f"Prompt: {prompt}")

    # Step 1: 詳細な説明を生成
    detailed_prompt, _ = askgpt(STEP1_SYS, STEP1_USER.replace(
        "%DESCRIPTION%", prompt), "gpt-4o-mini")
    mc.postToChat(f"Step1 done (1/4)")
    logging.info(f"detailed_prompt: {detailed_prompt}")

    # Step 2: DALL-Eに入力するためのimageタグを生成
    image_tag, _ = askgpt(STEP2_SYS, STEP2_USER.replace(
        "%STEP1_RESULT%", detailed_prompt), "gpt-4o-mini")
    mc.postToChat(f"Step2 done (2/4)")
    logging.info(f"image_tag: {image_tag}")

    # Step 3: 画像を生成
    image_tag = " Structures that can be realized with about 30 block cubes in Minecraft." + image_tag.replace(
        "\"", "")
    image_url = ask_dall_e(image_tag)
    mc.postToChat(f"Step3 done (3/4)")
    logging.info(f"image_url: {image_url}")

    # Step 4: mcpiで実行するためのPythonプログラムを生成
    response, _ = askgpt(STEP4_SYS, STEP4_USER.replace(
        "%STEP1_RESULT%", detailed_prompt), "gpt-4o", )

    # APIの出力結果からコード部分をテキストで抽出
    python_code = get_code_blocks(response)

    mc.postToChat(f"Step4 done (4/4), waiting for building...")
    logging.info(f"python_code:\n{python_code}")

    # 実行するためのPythonコードをファイルに保存
    with open("python_code.py", "w") as f:
        f.write(python_code)

    # 生成されたPythonコードを実行
    exec(python_code, globals())

    mc.postToChat("Success!")


main()
