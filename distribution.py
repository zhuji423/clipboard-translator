"""Public distribution URLs and Native Messaging constants.

正式分发仅走 Microsoft Edge Add-ons（免费）。不上架 Chrome Web Store。
上架后把 EDGE_ADDON_URL 换成正式商品链接。
EXTENSION_*_ID 须与已发布（或公钥固定）的扩展 ID 一致，供 NM allowed_origins 使用。
"""

from __future__ import annotations

# GitHub Pages：仓库 Settings → Pages → Deploy from branch，目录选 /docs
ONBOARDING_URL = "https://zhuji423.github.io/clipboard-translator/onboarding/"

# Edge Add-ons 上架前指向引导页；上架后替换为 microsoftedge.microsoft.com 商品 URL
EDGE_ADDON_URL = ONBOARDING_URL

NATIVE_HOST_NAME = "com.clipboard_translator.bridge"
NATIVE_HOST_DESCRIPTION = "Clipboard Translator bridge credentials"
# Windows binary name (kept for older callers / docs).
NATIVE_HOST_EXE_NAME = "ClipboardTranslatorNmHost.exe"
NATIVE_HOST_BIN_STEM = "ClipboardTranslatorNmHost"


def native_host_bin_name() -> str:
    """Platform-specific Native Messaging host executable filename."""
    import sys

    if sys.platform == "win32":
        return NATIVE_HOST_EXE_NAME
    return NATIVE_HOST_BIN_STEM

# Stable ID from extension/keys (public key embedded in extension build).
# Replace with Edge store-assigned ID if different after listing.
EXTENSION_EDGE_ID = "oekjpiafgkdjacgpgacclehegnbaokmo"
# 兼容旧常量名；未上架 Chrome，与 Edge ID 相同即可
EXTENSION_CHROME_ID = EXTENSION_EDGE_ID

# Manifest "key" field (SPKI DER, base64) — pins unpacked / pre-store ID.
EXTENSION_PUBLIC_KEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAr7KUU3FDDEtfi3HuU/2jqSjlp3tfl0L+"
    "y1OIBCG19NuAZ/WCpIZKc4JZSn9Bgd2YGmPRD046Quzz8rCN5yMNmuQisBEl3FXDRGj8Wk/HPDVI"
    "OtMlhw5Z96YDtqFGn0U5Ma5atzXduv6EAH8g3R54JvMwNd6a9/aBXmkhQD4qLZ/0C414134iAi/"
    "zevMAJpcXQnqFn5vc3L0Rr1HzZAWG+UN9ajzKaHejknaSy8zuhqJ7zVB/vG8PH/LTeyxVj2JBfa"
    "4AJuKyVUVxDv+kln/6FNHZDNfPB1pucw1Ii1pB2GPM1iUfMTTzcM2qAixNADlt4Sxa03q91ICsj"
    "WrPPXwBsQIDAQAB"
)


def extension_allowed_origins() -> list[str]:
    origins: list[str] = []
    for ext_id in (EXTENSION_EDGE_ID, EXTENSION_CHROME_ID):
        ext_id = (ext_id or "").strip()
        if not ext_id:
            continue
        origin = f"chrome-extension://{ext_id}/"
        if origin not in origins:
            origins.append(origin)
    return origins


def preferred_extension_install_url() -> str:
    """Best URL for 'Install browser extension' actions (Edge Add-ons first)."""
    edge = (EDGE_ADDON_URL or "").strip()
    if edge:
        return edge
    return ONBOARDING_URL
