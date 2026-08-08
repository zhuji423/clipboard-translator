from __future__ import annotations

from dataclasses import dataclass

import requests

from config import LlmConfig


@dataclass(frozen=True)
class BalanceInfo:
    total_yuan: float
    currency: str
    is_available: bool


class BalanceError(Exception):
    """Raised when the balance endpoint cannot be queried or parsed."""


def balance_url(base_url: str) -> str:
    root = (base_url or "").rstrip("/")
    if root.lower().endswith("/v1"):
        root = root[:-3].rstrip("/")
    return f"{root}/user/balance"


def fetch_balance(cfg: LlmConfig, *, timeout_s: float | None = None) -> BalanceInfo:
    """GET DeepSeek-compatible /user/balance; prefer CNY total_balance."""
    if not cfg.api_key:
        raise BalanceError("未配置 api_key")
    url = balance_url(cfg.base_url)
    timeout = timeout_s if timeout_s is not None else min(10.0, float(cfg.timeout_s))
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise BalanceError(f"余额请求失败: {exc}") from exc
    except ValueError as exc:
        raise BalanceError("余额响应不是合法 JSON") from exc

    infos = data.get("balance_infos") or []
    if not isinstance(infos, list) or not infos:
        raise BalanceError("余额响应缺少 balance_infos")

    chosen = None
    for item in infos:
        if isinstance(item, dict) and str(item.get("currency", "")).upper() == "CNY":
            chosen = item
            break
    if chosen is None:
        first = infos[0]
        if not isinstance(first, dict):
            raise BalanceError("余额条目格式无效")
        chosen = first

    try:
        total = float(chosen.get("total_balance", "0") or 0)
    except (TypeError, ValueError) as exc:
        raise BalanceError("total_balance 无法解析") from exc

    currency = str(chosen.get("currency") or "CNY")
    is_available = bool(data.get("is_available", True))
    return BalanceInfo(total_yuan=total, currency=currency, is_available=is_available)
