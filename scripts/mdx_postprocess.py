"""en→X 翻译产物的确定性后处理（translate_mdx_en2{id,ms,ja}.py 共用）。

- localize_internal_links：内链补语言前缀（/mail/x → /id/mail/x），仅当目标语言文件存在时改写
- find_untranslated_attrs：找出译文中与英文原文完全相同的可见文本 props（Step/Tab/Card/Accordion 的 title、img 的 alt）
- apply_attr_translations：按映射表回填这些 props
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LINK_RE = re.compile(r'(\]\(|href=")/([^)"#?\s]+)')
TEXT_ATTR_RE = re.compile(
    r'(<(?:Step|Tab|Card|Accordion)\b[^>]*?\btitle="|<img\b[^>]*?\balt=")([^"]*)(")'
)


def _target_exists(lang: str, path: str) -> bool:
    base = REPO_ROOT / lang / path.rstrip("/")
    return base.with_suffix(".mdx").exists() or (base / "index.mdx").exists()


def localize_internal_links(text: str, lang: str) -> str:
    def repl(m: re.Match) -> str:
        path = m.group(2)
        if path.startswith(f"{lang}/") or not _target_exists(lang, path):
            return m.group(0)
        return f"{m.group(1)}/{lang}/{path}"

    return LINK_RE.sub(repl, text)


def _is_translatable(value: str) -> bool:
    # 纯品牌词 / 无字母的值（如 "DingTalk"、"API"）不算漏译
    return bool(re.search(r"[A-Za-z]{3,}\s+[A-Za-z]", value))


def find_untranslated_attrs(source: str, target: str) -> list[str]:
    src_values = {m.group(2) for m in TEXT_ATTR_RE.finditer(source)}
    found = {
        m.group(2)
        for m in TEXT_ATTR_RE.finditer(target)
        if m.group(2) in src_values and _is_translatable(m.group(2))
    }
    return sorted(found)


def apply_attr_translations(text: str, mapping: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        value = mapping.get(m.group(2), m.group(2)).replace('"', "“")
        return f"{m.group(1)}{value}{m.group(3)}"

    return TEXT_ATTR_RE.sub(repl, text)
