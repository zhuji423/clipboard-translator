from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceTable:
    hit_per_m: float
    miss_per_m: float
    out_per_m: float


# 官方人民币 / 百万 tokens（DeepSeek V4）
_FLASH = PriceTable(hit_per_m=0.02, miss_per_m=1.0, out_per_m=2.0)
_PRO = PriceTable(hit_per_m=0.025, miss_per_m=3.0, out_per_m=6.0)


@dataclass(frozen=True)
class CostBreakdown:
    hit: int
    miss: int
    completion: int
    cost_yuan: float
    no_cache_yuan: float
    saved_yuan: float
    saved_pct: float

    @property
    def has_usage(self) -> bool:
        return (self.hit + self.miss + self.completion) > 0


def price_table_for_model(model: str) -> PriceTable:
    name = (model or "").lower()
    if "pro" in name:
        return _PRO
    return _FLASH


def estimate_cost(
    model: str,
    hit: int,
    miss: int,
    completion: int,
) -> CostBreakdown:
    table = price_table_for_model(model)
    hit_i = max(0, int(hit))
    miss_i = max(0, int(miss))
    out_i = max(0, int(completion))
    cost = (
        hit_i / 1e6 * table.hit_per_m
        + miss_i / 1e6 * table.miss_per_m
        + out_i / 1e6 * table.out_per_m
    )
    no_cache = (hit_i + miss_i) / 1e6 * table.miss_per_m + out_i / 1e6 * table.out_per_m
    saved = max(0.0, no_cache - cost)
    saved_pct = (saved / no_cache * 100.0) if no_cache > 0 else 0.0
    return CostBreakdown(
        hit=hit_i,
        miss=miss_i,
        completion=out_i,
        cost_yuan=cost,
        no_cache_yuan=no_cache,
        saved_yuan=saved,
        saved_pct=saved_pct,
    )


def fmt_tokens(n: int) -> str:
    if n >= 1000:
        val = n / 1000
        if val == int(val):
            return f"{int(val)}k"
        return f"{val:.1f}k"
    return str(n)


def _trim_float(value: float, max_decimals: int = 3) -> str:
    text = f"{value:.{max_decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def fmt_money(amount_yuan: float) -> str:
    """展示用：>=1 元用元，否则用分（×100），便于阅读。"""
    if amount_yuan == 0:
        return "0分"
    if abs(amount_yuan) >= 1:
        return f"{_trim_float(amount_yuan, 2)}元"
    fen = amount_yuan * 100
    return f"{_trim_float(fen, 3)}分"


# 兼容旧调用名
fmt_yuan = fmt_money


def format_status_lines(cost: CostBreakdown, *, local_cache: bool = False) -> str:
    if local_cache:
        return "本地缓存 · 0分（未请求 API）"
    if not cost.has_usage:
        return "完成"
    tokens = (
        f"完成 · hit {fmt_tokens(cost.hit)} / miss {fmt_tokens(cost.miss)} "
        f"/ out {fmt_tokens(cost.completion)}"
    )
    # 用不间断空格粘住易被 Qt 从中间拆开的片段
    nbsp = "\u00a0"
    if cost.hit > 0 and cost.saved_yuan > 0:
        money = (
            f"{fmt_money(cost.cost_yuan)}（若无缓存约{nbsp}{fmt_money(cost.no_cache_yuan)}"
            f"{nbsp}·{nbsp}省{nbsp}{cost.saved_pct:.0f}%）"
        )
    else:
        money = f"{fmt_money(cost.cost_yuan)}（本次无缓存命中）"
    tokens = tokens.replace(" / ", f"{nbsp}/{nbsp}")
    return f"{tokens}{nbsp}·{nbsp}{money}"


def format_billing_line(
    used_yuan: float,
    remaining_yuan: float | None,
    *,
    error: str | None = None,
) -> str:
    used = max(0.0, float(used_yuan))
    used_part = f"今日已用 {fmt_money(used)}"
    if remaining_yuan is None:
        hint = error or "余额暂不可用"
        return f"{used_part} · {hint}"
    remaining = max(0.0, float(remaining_yuan))
    return f"{used_part} · 剩余 {fmt_money(remaining)}"
