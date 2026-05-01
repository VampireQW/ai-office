"""
LLM Client — 统一的大模型调用接口
支持 OpenAI 格式的 API（GLM / GPT / Claude 等）
"""
import os
import asyncio
import aiohttp
import logging
import traceback
import re
import json
from dotenv import load_dotenv

# 加载 .env 文件（从项目根目录）
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_project_root, ".env")
load_dotenv(_env_path)

logger = logging.getLogger("LLMClient")


class LLMClient:
    """
    异步 LLM 客户端，兼容 OpenAI Chat Completions 格式。
    """

    @staticmethod
    def _load_config() -> dict:
        # 允许用户在运行中更换 .env 里的模型配置，下次请求立即生效。
        load_dotenv(_env_path, override=True)
        return {
            "api_key": os.getenv("LLM_API_KEY", ""),
            "base_url": os.getenv("LLM_BASE_URL", "").rstrip("/"),
            "model": os.getenv("LLM_MODEL", ""),
            "max_input_chars": int(os.getenv("LLM_MAX_INPUT_CHARS", "60000")),
            "max_output_tokens": int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096")),
            "timeout_seconds": int(os.getenv("LLM_TIMEOUT_SECONDS", "240")),
            "max_images": int(os.getenv("LLM_MAX_IMAGES", "4")),
        }

    @staticmethod
    def _trim_text(text: str, max_chars: int) -> str:
        if not text or len(text) <= max_chars:
            return text or ""
        head = max_chars // 2
        tail = max_chars - head
        return (
            text[:head]
            + "\n\n...[中间内容过长，系统已自动截断以保护模型调用]...\n\n"
            + text[-tail:]
        )

    @staticmethod
    def _extract_images(text: str, max_images: int = 4):
        images = []

        def repl(match):
            if len(images) < max_images:
                images.append({
                    "source": match.group(1),
                    "url": match.group(2),
                })
            return f"[图片已作为视觉输入发送给模型：{match.group(1)}]"

        cleaned = re.sub(
            r"\[\[AIKY_IMAGE:([^\]|]+)\|(data:image/[^;\]]+;base64,[A-Za-z0-9+/=\r\n]+)\]\]",
            repl,
            text or "",
            flags=re.IGNORECASE,
        )
        return cleaned, images

    @staticmethod
    def _build_user_content(user_prompt: str, config: dict = None):
        config = config or LLMClient._load_config()
        cleaned_prompt, images = LLMClient._extract_images(user_prompt, config["max_images"])
        trimmed = LLMClient._trim_text(cleaned_prompt, config["max_input_chars"])
        if not images:
            return trimmed, 0

        content = [{"type": "text", "text": trimmed}]
        for item in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": item["url"]},
            })
        return content, len(images)

    @staticmethod
    async def generate(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        config = LLMClient._load_config()
        api_key = config["api_key"]
        base_url = config["base_url"]
        model = config["model"]

        if not api_key or not base_url or not model:
            missing = []
            if not api_key: missing.append("LLM_API_KEY")
            if not base_url: missing.append("LLM_BASE_URL")
            if not model: missing.append("LLM_MODEL")
            msg = f"未配置 {', '.join(missing)}，请在 .env 文件中设置"
            logger.error(msg)
            return f"Error: {msg}"

        user_content, image_count = LLMClient._build_user_content(user_prompt, config)
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": LLMClient._trim_text(system_prompt, config["max_input_chars"] // 3)},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature,
            "max_tokens": config["max_output_tokens"],
            "stream": False
        }

        try:
            logger.info(f"Requesting {model} with {image_count} image(s)...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=config["timeout_seconds"])) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API Error ({response.status}): {error_text}")
                        if response.status in (400, 413):
                            return f"Error: AI input too long or invalid ({response.status})"
                        return f"Error: AI Service Unavailable ({response.status})"

                    data = await response.json()
                    return data["choices"][0]["message"]["content"]

        except (asyncio.TimeoutError, TimeoutError):
            logger.error("LLM request timed out")
            return "Error: Request timed out"
        except Exception as e:
            error_msg = f"LLM request exception: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            return f"Error: {error_msg}"

    @staticmethod
    async def generate_stream(system_prompt: str, user_prompt: str, temperature: float = 0.7, on_delta=None) -> str:
        config = LLMClient._load_config()
        api_key = config["api_key"]
        base_url = config["base_url"]
        model = config["model"]

        if not api_key or not base_url or not model:
            missing = []
            if not api_key: missing.append("LLM_API_KEY")
            if not base_url: missing.append("LLM_BASE_URL")
            if not model: missing.append("LLM_MODEL")
            msg = f"未配置 {', '.join(missing)}，请在 .env 文件中设置"
            logger.error(msg)
            return f"Error: {msg}"

        user_content, image_count = LLMClient._build_user_content(user_prompt, config)
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": LLMClient._trim_text(system_prompt, config["max_input_chars"] // 3)},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature,
            "max_tokens": config["max_output_tokens"],
            "stream": True
        }

        chunks = []
        try:
            logger.info(f"Streaming {model} with {image_count} image(s)...")
            timeout = aiohttp.ClientTimeout(total=config["timeout_seconds"], sock_read=90)
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API Stream Error ({response.status}): {error_text}")
                        if response.status in (400, 413):
                            return f"Error: AI input too long or invalid ({response.status})"
                        return f"Error: AI Service Unavailable ({response.status})"

                    async for raw in response.content:
                        text = raw.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data:"):
                                line = line[5:].strip()
                            if line == "[DONE]":
                                return "".join(chunks)
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            choice = (data.get("choices") or [{}])[0]
                            delta = choice.get("delta") or {}
                            piece = delta.get("content")
                            if piece is None:
                                message = choice.get("message") or {}
                                piece = message.get("content")
                            if isinstance(piece, list):
                                piece = "".join(
                                    part.get("text", "") if isinstance(part, dict) else str(part)
                                    for part in piece
                                )
                            if piece:
                                chunks.append(piece)
                                if on_delta:
                                    await on_delta(piece)

            return "".join(chunks)

        except (asyncio.TimeoutError, TimeoutError):
            logger.error("LLM stream request timed out")
            if chunks:
                return "".join(chunks)
            return "Error: Request timed out"
        except Exception as e:
            error_msg = f"LLM stream request exception: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            if chunks:
                return "".join(chunks)
            return f"Error: {error_msg}"


# 单例
llm_client = LLMClient()
