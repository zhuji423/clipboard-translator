from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from threading import Event, Lock
from typing import Any

import requests

from config import LlmConfig

LANG_LABELS = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

# system + 2 轮 few-shot 占用的 message 条数（不可裁剪）
_PREFIX_LEN = 5  # 1 system + 4 few-shot
_MAX_MESSAGES_CHARS = 80_000


def _build_system_prompt(target_lang: str) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    return (
        "你是专业翻译引擎，专门服务于剪贴板即时翻译场景。"
        f"请自动识别用户输入的源语言，并将其准确翻译成{lang}。"
        "输出要求极其严格：只输出译文正文本身，不要输出任何解释、备注、前后缀、引号、"
        "也不要写「译文：」「翻译如下」之类的提示语；不要进行逐句分析或点评。"
        "翻译原则：忠实原意，语句通顺自然，符合目标语言母语者的表达习惯；"
        "专有名词、品牌名、人名地名在约定俗成或无明确译法时保留原文；"
        "代码标识符、函数名、API 名称、文件路径、命令行参数一般保留不译；"
        "游戏术语、网络黑话、技术黑话优先采用中文玩家/开发者通用译法，没有通行译法时保留原文并保证可读；"
        "标点与换行尽量跟随原文结构，不要擅自合并或删减段落。"
        "若原文已是目标语言，可做轻度润色使其更自然，但不要无故扩写或改变信息量。"
        "下面会给出若干示范问答，请严格模仿其「只给译文」的输出风格。"
    )


def _few_shot_messages(target_lang: str) -> list[dict[str, str]]:
    # 示范轮写入稳定前缀；目标语为中文时用中英互译示例，其它目标语仍用中文说明+对应译文风格。
    if target_lang == "zh":
        return [
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
                "content": "把这段日志里的 error 含义讲清楚：Connection reset by peer while calling GetUserProfile.",
            },
            {
                "role": "assistant",
                "content": "在调用 GetUserProfile 时连接被对端重置。",
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
    def __init__(self, cfg: LlmConfig, target_lang: str = "zh") -> None:
        self._cfg = cfg
        self._target_lang = target_lang
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            }
        )
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        self._lock = Lock()
        self._day_key = ""
        self._messages: list[dict[str, str]] = []
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
        self._messages = [
            {"role": "system", "content": _build_system_prompt(self._target_lang)},
            *_few_shot_messages(self._target_lang),
        ]

    def _ensure_fresh(self, target_lang: str) -> None:
        today = date.today().isoformat()
        if target_lang != self._target_lang:
            self._target_lang = target_lang
            self._reset_messages()
            return
        if self._day_key != today:
            self._reset_messages()

    def _messages_char_len(self) -> int:
        return sum(len(m.get("content", "")) for m in self._messages)

    def _trim_if_needed(self) -> None:
        while (
            len(self._messages) > _PREFIX_LEN + 1
            and self._messages_char_len() > _MAX_MESSAGES_CHARS
        ):
            # 删掉 few-shot 之后最早的一对 user/assistant
            del self._messages[_PREFIX_LEN : _PREFIX_LEN + 2]

    def translate_stream(
        self,
        text: str,
        target_lang: str,
        cancel_event: Event,
        on_delta: Callable[[str], None] | None = None,
    ) -> TranslateResult:
        with self._lock:
            self._ensure_fresh(target_lang)
            self._trim_if_needed()
            self._messages.append({"role": "user", "content": text})
            # 拷贝快照发给 API，避免流式过程中被并发改动
            messages_payload = list(self._messages)

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
                    with self._lock:
                        self._rollback_last_user()
                    return TranslateResult(text="")

                result = "".join(chunks).strip()
                with self._lock:
                    # 确认末尾仍是本次 user，再追加 assistant
                    if (
                        self._messages
                        and self._messages[-1].get("role") == "user"
                        and self._messages[-1].get("content") == text
                    ):
                        self._messages.append(
                            {"role": "assistant", "content": result}
                        )
                    else:
                        # 已被更新的会话打断，不污染历史
                        pass
                return TranslateResult(text=result, usage=usage_info)
        except Exception:
            with self._lock:
                if (
                    self._messages
                    and self._messages[-1].get("role") == "user"
                    and self._messages[-1].get("content") == text
                ):
                    self._rollback_last_user()
            raise

    def _rollback_last_user(self) -> None:
        if self._messages and self._messages[-1].get("role") == "user":
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
