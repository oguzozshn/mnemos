"""Tiny Turkish / English detector. Good enough for chat messages; no model needed."""

from __future__ import annotations

import re

_TR_CHARS = set("çğıöşü")
_TR_STOP = {
    "ve", "bir", "bu", "şu", "için", "ne", "mi", "mı", "mu", "mü", "da", "de", "ben", "sen",
    "çok", "nasıl", "olarak", "gibi", "ama", "ile", "var", "yok", "daha", "sonra", "şimdi",
    "neden", "niye", "evet", "hayır", "tamam", "olur", "bence", "sence", "benim", "senin",
    "kadar", "her", "hiç", "nerde", "nerede", "yap", "yapalım", "abi", "peki", "yani", "değil",
    "ki", "o", "en", "ya", "veya", "hem", "bi", "şey",
}
_EN_STOP = {
    "the", "and", "is", "are", "to", "of", "i", "you", "what", "how", "it", "for", "in",
    "this", "that", "with", "can", "do", "does", "my", "me", "be", "on", "not", "why",
    "please", "should", "would", "could", "have", "has", "was", "will", "an", "a", "if",
    "or", "but", "so", "about", "there", "they", "we", "your",
}
_WORD = re.compile(r"[a-zçğıöşüâîû]+")


def detect_lang(text: str) -> str | None:
    """Return 'tr', 'en', 'mixed', or None when there is too little signal."""
    words = _WORD.findall(text.lower())
    tr = sum(1 for w in words if w in _TR_STOP or _TR_CHARS & set(w))
    en = sum(1 for w in words if w in _EN_STOP)
    if tr + en < 2:
        if tr + en == 1:
            return "tr" if tr else "en"
        return None
    share = tr / (tr + en)
    if share >= 0.7:
        return "tr"
    if share <= 0.3:
        return "en"
    return "mixed"
