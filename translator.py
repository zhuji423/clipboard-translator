from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from threading import Event, Lock
from typing import Any, Literal

import requests

from config import LlmConfig
from translation_context import TranslationContext

LANG_LABELS = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

_MAX_MESSAGES_CHARS = 80_000
SessionMode = Literal["translate", "answer"]


def _build_system_prompt(target_lang: str) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    return (
        "你是专业翻译引擎，专门服务于剪贴板即时翻译场景。"
        f"请自动识别用户输入的源语言，并将其准确翻译成{lang}。"
        "只输出译文正文：不要「译文：」前缀、不要引号包裹全文、不要逐句分析或点评；"
        "译文中不要重复粘贴原文单词或标识符（不要写成「elapsed（已用时）」或「has_children（是否有子项）」这种形式）。"
        "翻译原则：忠实原意，语句通顺自然，符合目标语言母语者的表达习惯；"
        f"专有名词、品牌名、人名地名：有通行{lang}译法时用通行译法；否则用极短{lang}说明其指代，仍不要回显原文。"
        "代码标识符、函数名、API 名称：必须给出含义，不得只回显原文。"
        f"若整段输入主要是单词/短语（而非完整句子），只输出{lang}短义；多义用分号分隔，不要写成长句词典。"
        f"若出现在完整句子或日志里，整句译成{lang}，把其中的标识符译成对应含义的自然语言，不要在译文里再贴一遍原文标识符。"
        "文件路径、URL、命令行里的裸参数、大段代码/堆栈：保持原样，不要逐符号翻译。"
        f"游戏术语、网络黑话、技术黑话优先采用通行的{lang}译法。"
        "标点与换行尽量跟随原文结构，不要擅自合并或删减段落。"
        "若原文已是目标语言，可做轻度润色使其更自然，但不要无故扩写或改变信息量。"
        "当用户消息提供结构化上下文时，previous 与 current 仅用于理解指代、术语和语气；"
        "只翻译 text_to_translate，绝对不要翻译、复述或输出上下文本身。"
        "下面会给出若干示范问答，请严格模仿其输出风格。"
    )


def _build_answer_system_prompt(target_lang: str) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    return (
        "你是剪贴板即时问答助手。请直接、准确地回答用户的问题，"
        f"默认使用{lang}，除非用户明确要求其他语言。"
        "不要把问题当成翻译任务，不要复述问题，也不要添加“回答：”之类的前缀。"
        "简单问题优先给出简洁结论；复杂问题按需要给出必要步骤、公式或代码。"
        "涉及不确定、时效性或缺少上下文的事实时必须明确说明，不得编造。"
        "后续用户消息可能是追问，应结合本次应用运行期间此前的问答上下文回答。"
    )


def _few_shot_messages(target_lang: str) -> list[dict[str, str]]:
    # 示范轮写入稳定前缀；目标语为中文时用中英互译示例，其它目标语仍用中文说明+对应译文风格。
    if target_lang == "zh":
        return [
            {
                "role": "user",
                "content": "elapsed",
            },
            {
                "role": "assistant",
                "content": "经过的；已用时",
            },
            {
                "role": "user",
                "content": "has_children",
            },
            {
                "role": "assistant",
                "content": "是否有子项",
            },
            {
                "role": "user",
                "content": "The patch notes mention a hotfix for the inventory sync race condition.",
            },
            {
                "role": "assistant",
                "content": "更新说明提到修复了物品栏同步竞态条件的热修复。",
            },
            {
                "role": "user",
                "content": "Connection reset by peer while calling GetUserProfile.",
            },
            {
                "role": "assistant",
                "content": "在调用获取用户资料时连接被对端重置。",
            },
        ]
    lang = LANG_LABELS.get(target_lang, target_lang)
    return [
        {
            "role": "user",
            "content": "更新说明提到修复了物品栏同步竞态条件的热修复。",
        },
        {
            "role": "assistant",
            "content": (
                "The patch notes mention a hotfix for the inventory sync race condition."
                if target_lang == "en"
                else f"[Translate previous Chinese sentence into {lang}.]"
            ),
        },
        {
            "role": "user",
            "content": "在调用 GetUserProfile 时连接被对端重置。",
        },
        {
            "role": "assistant",
            "content": (
                "Connection reset by peer while calling GetUserProfile."
                if target_lang == "en"
                else f"[Translate previous Chinese sentence into {lang}.]"
            ),
        },
    ]


@dataclass(frozen=True)
class UsageInfo:
    hit: int = 0
    miss: int = 0
    completion: int = 0

    @property
    def summary(self) -> str:
        if self.hit == 0 and self.miss == 0 and self.completion == 0:
            return ""
        return (
            f"hit {_fmt_tokens(self.hit)} / miss {_fmt_tokens(self.miss)} "
            f"/ out {_fmt_tokens(self.completion)}"
        )


@dataclass(frozen=True)
class TranslateResult:
    text: str
    usage: UsageInfo = UsageInfo()

    @property
    def usage_summary(self) -> str:
        return self.usage.summary


class OpenAICompatTranslator:
    def __init__(
        self,
        cfg: LlmConfig,
        target_lang: str = "zh",
        mode: SessionMode = "translate",
    ) -> None:
        self._cfg = cfg
        self._target_lang = target_lang
        self._mode = mode
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            }
        )
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        self._lock = Lock()
        self._request_lock = Lock()
        self._day_key = ""
        self._messages: list[dict[str, str]] = []
        self._prefix_len = 0
        self._context_generation = 0
        self._reset_messages()

    def warm_up(self) -> None:
        try:
            self._session.get(
                self._cfg.base_url.rstrip("/"),
                timeout=min(3.0, self._cfg.timeout_s),
            )
        except requests.RequestException:
            pass

    def _reset_messages(self) -> None:
        self._day_key = date.today().isoformat()
        if self._mode == "answer":
            self._messages = [
                {
                    "role": "system",
                    "content": _build_answer_system_prompt(self._target_lang),
                }
            ]
        else:
            self._messages = [
                {
                    "role": "system",
                    "content": _build_system_prompt(self._target_lang),
                },
                *_few_shot_messages(self._target_lang),
            ]
        self._prefix_len = len(self._messages)
        self._context_generation += 1

    def reset_context(self) -> None:
        with self._lock:
            self._reset_messages()

    def _ensure_fresh(self, target_lang: str) -> None:
        today = date.today().isoformat()
        if target_lang != self._target_lang:
            self._target_lang = target_lang
            self._reset_messages()
            return
        if self._mode == "translate" and self._day_key != today:
            self._reset_messages()

    def _messages_char_len(self) -> int:
        return sum(len(m.get("content", "")) for m in self._messages)

    def _trim_if_needed(self) -> None:
        while (
            len(self._messages) > self._prefix_len + 1
            and self._messages_char_len() > _MAX_MESSAGES_CHARS
        ):
            # 删掉 few-shot 之后最早的一对 user/assistant
            del self._messages[self._prefix_len : self._prefix_len + 2]

    def translate_stream(
        self,
        text: str,
        target_lang: str,
        cancel_event: Event,
        on_delta: Callable[[str], None] | None = None,
        context: TranslationContext | None = None,
    ) -> TranslateResult:
        with self._request_lock:
            return self._stream_locked(
                text,
                target_lang,
                cancel_event,
                on_delta,
                context=context,
            )

    def answer_stream(
        self,
        text: str,
        target_lang: str,
        cancel_event: Event,
        on_delta: Callable[[str], None] | None = None,
    ) -> TranslateResult:
        with self._request_lock:
            return self._stream_locked(text, target_lang, cancel_event, on_delta)

    def _stream_locked(
        self,
        text: str,
        target_lang: str,
        cancel_event: Event,
        on_delta: Callable[[str], None] | None = None,
        context: TranslationContext | None = None,
    ) -> TranslateResult:
        with self._lock:
            self._ensure_fresh(target_lang)
            context_generation = self._context_generation
            persistent = self._mode == "answer"
            user_content = (
                text
                if persistent
                else _build_translation_user_content(text, context)
            )
            if persistent:
                self._trim_if_needed()
                self._messages.append({"role": "user", "content": user_content})
                # 拷贝快照发给 API，避免流式过程中被并发改动
                messages_payload = list(self._messages)
            else:
                messages_payload = [
                    *self._messages[: self._prefix_len],
                    {"role": "user", "content": user_content},
                ]

        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "stream": True,
            "temperature": 0.2,
            "messages": messages_payload,
            "stream_options": {"include_usage": True},
            # DeepSeek V4：默认 thinking=enabled，会先流式吐 reasoning_content 数秒
            "thinking": {
                "type": "enabled" if self._cfg.thinking else "disabled"
            },
        }

        usage_info = UsageInfo()
        try:
            with self._session.post(
                self._url,
                json=payload,
                stream=True,
                timeout=self._cfg.timeout_s,
            ) as resp:
                if resp.status_code >= 400:
                    body = resp.text[:300]
                    raise RuntimeError(f"HTTP {resp.status_code}: {body}")

                chunks: list[str] = []
                for piece, usage in self._iter_sse(resp, cancel_event):
                    if usage is not None:
                        usage_info = self._parse_usage(usage)
                        continue
                    if piece:
                        chunks.append(piece)
                        if on_delta:
                            on_delta(piece)

                if cancel_event.is_set():
                    if persistent:
                        with self._lock:
                            self._rollback_last_user(
                                user_content, context_generation
                            )
                    return TranslateResult(text="")

                result = "".join(chunks).strip()
                if persistent:
                    with self._lock:
                        # 确认末尾仍是本次 user，再追加 assistant
                        if (
                            self._context_generation == context_generation
                            and self._messages
                            and self._messages[-1].get("role") == "user"
                            and self._messages[-1].get("content") == user_content
                        ):
                            self._messages.append(
                                {"role": "assistant", "content": result}
                            )
                return TranslateResult(text=result, usage=usage_info)
        except Exception:
            if persistent:
                with self._lock:
                    if (
                        self._context_generation == context_generation
                        and self._messages
                        and self._messages[-1].get("role") == "user"
                        and self._messages[-1].get("content") == user_content
                    ):
                        self._rollback_last_user(
                            user_content, context_generation
                        )
            raise

    def _rollback_last_user(self, text: str, context_generation: int) -> None:
        if (
            self._context_generation == context_generation
            and self._messages
            and self._messages[-1].get("role") == "user"
            and self._messages[-1].get("content") == text
        ):
            self._messages.pop()

    @staticmethod
    def _parse_usage(usage: dict[str, Any]) -> UsageInfo:
        hit = int(usage.get("prompt_cache_hit_tokens") or 0)
        miss = int(usage.get("prompt_cache_miss_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        if completion == 0:
            # 部分实现把输出放在 completion_tokens_details / total - prompt
            prompt = int(usage.get("prompt_tokens") or 0)
            total = int(usage.get("total_tokens") or 0)
            if total > prompt:
                completion = total - prompt
        return UsageInfo(hit=hit, miss=miss, completion=completion)

    def _iter_sse(
        self, resp: requests.Response, cancel_event: Event
    ) -> Iterator[tuple[str | None, dict[str, Any] | None]]:
        for raw in resp.iter_lines(decode_unicode=True):
            if cancel_event.is_set():
                resp.close()
                return
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage")
            if usage:
                yield None, usage
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content, None


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        val = n / 1000
        if val == int(val):
            return f"{int(val)}k"
        return f"{val:.1f}k"
    return str(n)


def _build_translation_user_content(
    text: str, context: TranslationContext | None
) -> str:
    if context is None or context.is_empty:
        return text
    return json.dumps(
        {
            "context": {
                "source": context.source,
                "previous": list(context.previous),
                "current": context.current,
            },
            "text_to_translate": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
