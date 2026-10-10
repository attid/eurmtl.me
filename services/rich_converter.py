"""Конвертер HTML тела d2-вопроса → InputRichMessage (Telegram Bot API 10.x).

Вход — HTML-строка QUESTION_DATA.BODY (Quill 2), выход — dict вида
``{"blocks": [...]}``, готовый для ``InputRichMessage.model_validate`` и
``sendRichMessage``/``editMessageText(rich_message=...)`` в aiogram 3.31.

Формат — входные схемы aiogram (Input*), а не серверное представление
выгрузки 64Gram: plain-текст — просто str, смешанное содержимое абзаца —
list[узлов] (concat), заголовок — блок "heading" с полем size (не level),
картинка — блок "photo" c InputMediaPhoto(media=URL). Серверный эталон:
docs/samples/tg_rich_message_example.json.

Всё непонятное не роняет конвертацию: неизвестный тег рекурсивно
раскрывается в детей (span/font → содержимое), незнакомый блочный тег
(table/blockquote/pre) — его текст абзацами. Полный отказ конвертации →
фолбэк на sendMessage+SULGUK в вызывающем коде.
"""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

# <h1>-<h3> → заголовок размера 1-3; крупнее — тоже heading, size без cap
# сверх 6 (Bot API не ограничивает, эталон содержит level 4).
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

_WRAP_TAGS = {
    "strong": "bold",
    "b": "bold",
    "em": "italic",
    "i": "italic",
    "code": "code",
    "s": "strikethrough",
    "strike": "strikethrough",
    "del": "strikethrough",
    "u": "underline",
}


def html_to_rich_message(html: str, base_url: str) -> dict:
    """HTML тела вопроса → {"blocks": [...]} для InputRichMessage.

    base_url — Origin сайта (например "https://eurmtl.me" или
    "http://localhost:8000"), из него строятся абсолютные URL картинок:
    Telegram скачивает /d2/img/<id> сам, относительный путь не годится.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    return {"blocks": _blocks_from_children(soup.children, base_url)}


def _clean_ws(text: str) -> str:
    """HTML переводы строк/табуляции внутри текста — пробелы; \n оставляем
    (наш способ явных переводов строки из <br>)."""
    return text.replace("\r", "").replace("\t", " ")


def _collapse_ws(text: str) -> str:
    """Пробельные прогоны (кроме \n от <br>, который не проходит сюда) —
    в один пробел: '  a\\n  b ' → ' a b '."""
    return re.sub(r"[^\S\n]+", " ", text)


def _blocks_from_children(children, base_url: str) -> list[dict]:
    """Блоки из потока узлов. Блочные теги дают блоки, inline-текст между
    ними сгребается в абзацы (голый текст вне <p> — норма для Quill)."""
    blocks: list[dict] = []
    inline_run: list = []

    def flush_inline():
        if not inline_run:
            return
        text_node, embedded = _merge_nodes(inline_run)
        inline_run.clear()
        if text_node is not None:
            blocks.append({"type": "paragraph", "text": text_node})
        blocks.extend(embedded)

    for child in children:
        if isinstance(child, NavigableString):
            text = _clean_ws(str(child))
            if text.strip() or (text and blocks and inline_run):
                # значимый текст, либо пробел между двумя inline-узлами
                if text.strip():
                    inline_run.append(text)
        elif isinstance(child, Tag):
            name = child.name.lower()
            if name == "br":
                inline_run.append("\n")
            elif name in _HEADING_TAGS:
                flush_inline()
                blocks.append(_heading_block(child, base_url))
            elif name in ("p", "div"):
                flush_inline()
                blocks.extend(_paragraph_blocks(child, base_url))
            elif name in ("ul", "ol"):
                flush_inline()
                blocks.append(_list_block(child, base_url))
            elif name == "img":
                flush_inline()
                block = _photo_block(child, base_url)
                if block is not None:
                    blocks.append(block)
            elif name in ("table", "blockquote", "pre"):
                flush_inline()
                blocks.extend(_fallback_text_blocks(child, base_url))
            else:
                # inline-тег (strong/a/span/...) — в текущий абзац.
                inline_run.extend(_inline_from_tag(child, base_url))
    flush_inline()
    return blocks


def _heading_block(tag: Tag, base_url: str) -> dict:
    size = _HEADING_TAGS.get(tag.name.lower(), 3)
    node, _ = _merge_nodes(_inline_from_children(tag, base_url))
    return {
        "type": "heading",
        "size": size,
        "text": node if node is not None else "",
    }


def _paragraph_blocks(tag: Tag, base_url: str) -> list[dict]:
    """<p>/<div> → [paragraph]; <p><br></p> (пустая строка Quill) →
    paragraph с текстом ""; картинки/списки внутри — отдельными блоками
    после абзаца. Пустой контейнер без единого узла → [] (кроме явно
    пустого <p>, он значим как пустая строка)."""
    nodes = _inline_from_children(tag, base_url)
    if not nodes:
        has_children = any(isinstance(c, Tag) for c in tag.children)
        # <p></p> — пустая строка; <p><img/></p> (без src, дети ничего не
        # дали) — не строка, а пустота: не создаём фантомный абзац.
        if tag.name.lower() == "p" and not has_children:
            return [{"type": "paragraph", "text": ""}]
        return []
    text_node, embedded = _merge_nodes(nodes)
    blocks: list[dict] = []
    if text_node is None or text_node == "" or text_node == "\n":
        if embedded:
            # <p><img></p>: только блок(и) без текста — пустая строка не нужна
            blocks.extend(embedded)
            return blocks
        # пустая строка (Quill: <p><br></p>) — значима, не выбрасываем
        blocks.append({"type": "paragraph", "text": ""})
    else:
        blocks.append({"type": "paragraph", "text": text_node})
    blocks.extend(embedded)
    return blocks


def _list_block(tag: Tag, base_url: str) -> dict:
    items = []
    ordered = tag.name.lower() == "ol"
    index = 0
    for li in (c for c in tag.children if isinstance(c, Tag)):
        if li.name.lower() != "li":
            continue
        index += 1
        nodes = _inline_from_children(li, base_url)
        item_blocks: list[dict] = []
        if nodes:
            text_node, embedded = _merge_nodes(nodes)
            if text_node is not None:
                item_blocks.append({"type": "paragraph", "text": text_node})
            item_blocks.extend(embedded)
        if not item_blocks:
            item_blocks = [{"type": "paragraph", "text": ""}]
        item: dict = {"blocks": item_blocks}
        if ordered:
            item["value"] = index
        items.append(item)
    return {"type": "list", "items": items}


def _photo_block(tag: Tag, base_url: str) -> dict | None:
    src = (tag.get("src") or "").strip()
    if not src:
        return None
    return {
        "type": "photo",
        "photo": {"type": "photo", "media": _absolute_url(src, base_url)},
    }


def _absolute_url(src: str, base_url: str) -> str:
    if src.startswith(("http://", "https://")):
        return src
    if not base_url.endswith("/"):
        base_url += "/"
    return base_url + src.lstrip("/")


def _fallback_text_blocks(tag: Tag, base_url: str) -> list[dict]:
    """Незнакомый блочный тег: дети как блоки; нет блоков — весь текст
    одним абзацем (контент не теряем)."""
    blocks = _blocks_from_children(tag.children, base_url)
    if not blocks:
        text = tag.get_text().strip()
        if text:
            blocks = [{"type": "paragraph", "text": text}]
    return blocks


def _inline_from_children(tag: Tag, base_url: str) -> list:
    """Плоский список RichText-узлов детей inline-контейнера (p, h*, li,
    обёртки). Встроенные блоки (img/списки внутри p) приходят как
    ("__block__", block) — разбирает _merge_nodes."""
    nodes: list = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            text = _clean_ws(str(child))
            if text.strip():
                # внутренние пробельные прогоны — в один пробел, края
                # сохраняем ("a <b>b</b>" не должно терять пробел)
                nodes.append(_collapse_ws(text))
            elif nodes and not (isinstance(nodes[-1], str) and nodes[-1] == " "):
                # пробел между двумя узлами ("<b>a</b> <i>b</i>")
                nodes.append(" ")
        elif isinstance(child, Tag):
            nodes.extend(_inline_from_tag(child, base_url))
    return nodes


def _inline_from_tag(tag: Tag, base_url: str) -> list:
    """RichText-узлы inline-тега (обычно 0..1; <br> даёт "\\n")."""
    name = tag.name.lower()

    if name == "br":
        return ["\n"]
    if name == "img":
        block = _photo_block(tag, base_url)
        return [("__block__", block)] if block is not None else []
    if name == "a":
        href = (tag.get("href") or "").strip()
        inner = _inline_from_children(tag, base_url)
        if not href:
            return inner
        node, embedded = _merge_nodes(inner)
        # <a><img></a>: ссылка-картинка не выражается — фото рядом, ссылкой
        # остаётся только текст (если есть).
        result = []
        if node is not None:
            result.append(
                {"type": "url", "url": href, "text": node if node is not None else ""}
            )
        result.extend(_as_block_nodes(embedded))
        return result
    if name in _WRAP_TAGS:
        inner = _inline_from_children(tag, base_url)
        if not inner:
            return []
        node, embedded = _merge_nodes(inner)
        # <b><img></b> — картинка не может быть «жирной», выносим блок.
        result = []
        if node is not None:
            result.append({"type": _WRAP_TAGS[name], "text": node})
        result.extend(_as_block_nodes(embedded))
        return result
    if name in _HEADING_TAGS:
        return [("__block__", _heading_block(tag, base_url))]
    if name in ("ul", "ol"):
        return [("__block__", _list_block(tag, base_url))]
    if name in ("p", "div"):
        return [("__blocks__", _paragraph_blocks(tag, base_url))]
    if name in ("table", "pre", "blockquote"):
        return [("__blocks__", _fallback_text_blocks(tag, base_url))]
    # Неизвестный тег (span, font, ...) — рекурсивно содержимое.
    return _inline_from_children(tag, base_url)


def _as_block_nodes(blocks: list) -> list:
    """Блоки, вынесенные из обёрток, обратно в узловую форму ("__block__"),
    чтобы их разобрал _merge_nodes на верхнем уровне."""
    return [("__block__", block) for block in blocks]


def _merge_nodes(nodes: list):
    """Список RichText-узлов → (text_node, embedded_blocks).

    text_node: str — единственный голый текст; dict — единственная
    обёртка (bold/url/...); list — смешанное содержимое (concat);
    None — текста нет. embedded_blocks — фото/списки/прочие блоки,
    встраиваемые в текст, они идут отдельными блоками после абзаца.
    """
    texts: list = []
    embedded: list = []
    for node in nodes:
        if isinstance(node, tuple) and node[0] == "__block__":
            if node[1] is not None:
                embedded.append(node[1])
        elif isinstance(node, tuple) and node[0] == "__blocks__":
            for block in node[1]:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    # абзац внутри абзаца — склеиваем переводом строки
                    joined = _paragraph_as_text(block["text"])
                    if joined:
                        texts.append(joined + "\n")
                else:
                    embedded.append(block)
        else:
            texts.append(node)
    # хвостовой \n от склейки вложенных абзацев не нужен; "\n" от <br>
    # (пустая строка <p><br></p>) — не трогаем.
    if (
        texts
        and isinstance(texts[-1], str)
        and texts[-1].endswith("\n")
        and len(texts[-1]) > 1
    ):
        texts[-1] = texts[-1].rstrip("\n")
        if not texts[-1]:
            texts.pop()
    if not texts:
        return None, embedded
    if len(texts) == 1:
        return texts[0], embedded
    return texts, embedded


def _paragraph_as_text(node) -> str:
    """Плоский текст абзаца (для склейки вложенных p): без разметки."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return _paragraph_as_text(node.get("text", ""))
    if isinstance(node, list):
        return "".join(_paragraph_as_text(n) for n in node)
    return ""
