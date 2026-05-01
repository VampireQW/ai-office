"""
Context loader for AIky office commands.

It extracts URL and file references from a user instruction, reads what is
allowed, and appends a compact context block for downstream agents.
"""
import os
import re
import html
import base64
import mimetypes
import urllib.request
from dataclasses import dataclass
from typing import List


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QODER_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))
AIKY_ROOT = os.path.abspath(os.path.join(QODER_ROOT, "AIky"))
WORKSPACE_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, "workspace"))
INBOX_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, "inbox"))

ALLOWED_FILE_ROOTS = [QODER_ROOT, PROJECT_ROOT, WORKSPACE_ROOT, INBOX_ROOT, AIKY_ROOT]
MAX_CONTEXT_CHARS = int(os.getenv("AIKY_CONTEXT_MAX_CHARS", "24000"))
MAX_ITEM_CHARS = int(os.getenv("AIKY_CONTEXT_ITEM_MAX_CHARS", "8000"))
MAX_IMAGE_BYTES = int(os.getenv("AIKY_CONTEXT_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
TEXT_EXTENSIONS = "md|txt|json|yaml|yml|csv|html|py|js|ts|tsx|jsx|css"
IMAGE_EXTENSIONS = "png|jpg|jpeg|webp|gif"
READABLE_EXTENSIONS = f"{TEXT_EXTENSIONS}|{IMAGE_EXTENSIONS}"


@dataclass
class ContextItem:
    kind: str
    source: str
    content: str
    error: str = ""


def _is_allowed_file(path: str) -> bool:
    full = os.path.abspath(path)
    return any(full == root or full.startswith(root + os.sep) for root in ALLOWED_FILE_ROOTS if root)


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas).*?</\1>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)</h[1-6]\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_urls(text: str) -> List[str]:
    urls = re.findall(r"https?://[^\s，。；;、）)】\]]+", text or "", flags=re.IGNORECASE)
    return list(dict.fromkeys(url.rstrip(".,，。;；") for url in urls))


def _candidate_file_refs(text: str) -> List[str]:
    refs = []

    explicit_patterns = [
        r"(?:文件|图片|图像|截图|读取文件|读取图片|基于文件|基于图片|打开文件|file|path|image)\s*[:：]?\s*(.+?)(?=$|\n|，|。|；|;)",
        rf"`([^`]+\.(?:{READABLE_EXTENSIONS}))`",
    ]
    for pattern in explicit_patterns:
        refs.extend(m.strip().strip("\"'") for m in re.findall(pattern, text or "", flags=re.IGNORECASE))

    path_pattern = (
        rf"([A-Za-z]:\\[^\n\r\"'<>|?*]+?\.(?:{READABLE_EXTENSIONS}))"
        rf"|((?:\.{{1,2}}[\\/]|workspace[\\/]|AIky[\\/]|inbox[\\/])[^\n\r\"'<>|?*]+?\.(?:{READABLE_EXTENSIONS}))"
    )
    for m in re.findall(path_pattern, text or "", flags=re.IGNORECASE):
        refs.extend(part.strip() for part in m if part.strip())

    cleaned = []
    for ref in refs:
        ref = ref.strip().strip(".,，。;；")
        ext_match = re.match(rf"(.+?\.(?:{READABLE_EXTENSIONS}))", ref, flags=re.IGNORECASE)
        if ext_match:
            ref = ext_match.group(1)
        if ref and ref not in cleaned:
            cleaned.append(ref)
    return cleaned


def _resolve_file_ref(ref: str) -> str:
    ref = ref.strip().strip("\"'")
    if re.match(r"^[A-Za-z]:\\", ref):
        return os.path.abspath(ref)
    normalized = ref.replace("/", os.sep).replace("\\", os.sep)
    if normalized.lower().startswith("aiky" + os.sep):
        return os.path.abspath(os.path.join(QODER_ROOT, normalized))
    return os.path.abspath(os.path.join(PROJECT_ROOT, normalized))


def load_url(url: str) -> ContextItem:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AIky-System/1.0 (+local office assistant)",
                "Accept": "text/html,text/plain;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read(2_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        content = _strip_html(text)
        return ContextItem("url", url, content[:MAX_ITEM_CHARS])
    except Exception as exc:
        return ContextItem("url", url, "", str(exc))


def load_file(ref: str) -> ContextItem:
    path = _resolve_file_ref(ref)
    if not _is_allowed_file(path):
        return ContextItem("file", ref, "", f"路径不在允许读取范围内：{path}")
    if not os.path.exists(path) or not os.path.isfile(path):
        return ContextItem("file", ref, "", f"文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in IMAGE_EXTENSIONS.split("|"):
        return load_image(ref)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(MAX_ITEM_CHARS)
        return ContextItem("file", path, content)
    except Exception as exc:
        return ContextItem("file", ref, "", str(exc))


def load_image(ref: str) -> ContextItem:
    path = _resolve_file_ref(ref)
    if not _is_allowed_file(path):
        return ContextItem("image", ref, "", f"路径不在允许读取范围内：{path}")
    if not os.path.exists(path) or not os.path.isfile(path):
        return ContextItem("image", ref, "", f"图片不存在：{path}")
    try:
        size = os.path.getsize(path)
        if size > MAX_IMAGE_BYTES:
            mb = MAX_IMAGE_BYTES / 1024 / 1024
            return ContextItem("image", path, "", f"图片过大：{size} bytes，当前上限 {mb:.1f}MB")

        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        data_url = f"data:{mime};base64,{encoded}"
        return ContextItem("image", path, data_url)
    except Exception as exc:
        return ContextItem("image", ref, "", str(exc))


def build_context(user_input: str) -> dict:
    items = []
    for url in extract_urls(user_input):
        items.append(load_url(url))
    for ref in _candidate_file_refs(user_input):
        items.append(load_file(ref))

    loaded = [item for item in items if item.content]
    failed = [item for item in items if item.error]
    if not loaded and not failed:
        return {"text": user_input, "items": [], "failed": [], "summary": ""}

    blocks = []
    image_markers = []
    for idx, item in enumerate(loaded, 1):
        if item.kind == "image":
            blocks.append(
                f"### 上下文 {idx}: image - {item.source}\n"
                f"系统已读取这张图片，并会以视觉输入发送给模型。请结合图片内容完成任务。"
            )
            image_markers.append(f"[[AIKY_IMAGE:{item.source}|{item.content}]]")
        else:
            blocks.append(
                f"### 上下文 {idx}: {item.kind} - {item.source}\n"
                f"{item.content.strip()}"
            )
    if failed:
        blocks.append("### 未能读取的上下文\n" + "\n".join(f"- {i.kind}: {i.source} ({i.error})" for i in failed))

    context = "\n\n".join(blocks)[:MAX_CONTEXT_CHARS]
    image_payload = "\n".join(image_markers)
    enriched = f"{user_input.strip()}\n\n---\n以下是系统已读取到的上下文，请优先基于这些内容完成任务：\n\n{context}"
    if image_payload:
        enriched += f"\n\n---\n以下图片将作为视觉输入发送给模型，请直接观察图片内容：\n{image_payload}"
    image_count = len([item for item in loaded if item.kind == "image"])
    text_count = len(loaded) - image_count
    summary_parts = []
    if image_count:
        summary_parts.append(f"{image_count} 张图片")
    if text_count:
        summary_parts.append(f"{text_count} 个文本/网页上下文")
    if summary_parts:
        summary_parts.insert(0, f"已读取 {len(loaded)} 个上下文")
    if failed:
        summary_parts.append(f"{len(failed)} 个读取失败")
    return {
        "text": enriched,
        "items": [item.__dict__ for item in loaded],
        "failed": [item.__dict__ for item in failed],
        "summary": "，".join(summary_parts),
    }
