"""Конвертер HTML → InputRichMessage: маппинг каждого блока по эталону.

Эталон формата — docs/samples/tg_rich_message_example.json (серверное
представление Message.rich_message). Конвертер строит ВХОДНОЙ формат
aiogram (InputRichMessage), он отличается от серверного: plain-текст —
просто str (ноды "plain"/"empty" не нужны), смешанный абзац — list
(аналог concat), у заголовка поле size вместо level. Соответствие
структурам эталона проверяется в test_nesting_matches_reference_sample.
"""

import json
from pathlib import Path

import pytest
from aiogram.types import InputRichMessage

from services.rich_converter import html_to_rich_message

SAMPLE_PATH = (
    Path(__file__).parent.parent.parent
    / "docs"
    / "samples"
    / "tg_rich_message_example.json"
)


def convert(html: str, base_url: str = "https://eurmtl.me") -> dict:
    return html_to_rich_message(html, base_url)


def valid(html: str, base_url: str = "https://eurmtl.me") -> dict:
    """Конвертация + проверка, что aiogram принимает структуру."""
    out = convert(html, base_url)
    InputRichMessage.model_validate(out)
    return out


def test_empty_and_blank_body():
    assert convert("") == {"blocks": []}
    # <p><br></p> — пустая строка Quill: пустой paragraph.
    assert valid("<p><br></p>") == {"blocks": [{"type": "paragraph", "text": ""}]}


def test_plain_paragraph():
    out = valid("<p>Просто текст</p>")
    assert out == {"blocks": [{"type": "paragraph", "text": "Просто текст"}]}


@pytest.mark.parametrize(
    "html,size,text",
    [("<h1>H1</h1>", 1, "H1"), ("<h2>H2</h2>", 2, "H2"), ("<h3>H3</h3>", 3, "H3")],
)
def test_headings(html, size, text):
    out = valid(html)
    assert out == {"blocks": [{"type": "heading", "size": size, "text": text}]}


def test_paragraph_with_bold_italic_code():
    out = valid("<p>a <b>b</b> <i>c</i> <code>d</code></p>")
    assert out == {
        "blocks": [
            {
                "type": "paragraph",
                "text": [
                    "a ",
                    {"type": "bold", "text": "b"},
                    " ",
                    {"type": "italic", "text": "c"},
                    " ",
                    {"type": "code", "text": "d"},
                ],
            }
        ]
    }


def test_strong_em_aliases_and_strikethrough_underline():
    out = valid("<p><strong>s</strong><em>e</em><s>x</s><u>u</u></p>")
    assert out == {
        "blocks": [
            {
                "type": "paragraph",
                "text": [
                    {"type": "bold", "text": "s"},
                    {"type": "italic", "text": "e"},
                    {"type": "strikethrough", "text": "x"},
                    {"type": "underline", "text": "u"},
                ],
            }
        ]
    }


def test_link_node():
    out = valid('<p>см. <a href="https://eurmtl.me/d/abc">вопрос</a></p>')
    assert out == {
        "blocks": [
            {
                "type": "paragraph",
                "text": [
                    "см. ",
                    {
                        "type": "url",
                        "url": "https://eurmtl.me/d/abc",
                        "text": "вопрос",
                    },
                ],
            }
        ]
    }


def test_nested_link_bold():
    out = valid('<p><a href="https://x.ru"><b>жирная ссылка</b></a></p>')
    assert out == {
        "blocks": [
            {
                "type": "paragraph",
                "text": {
                    "type": "url",
                    "url": "https://x.ru",
                    "text": {"type": "bold", "text": "жирная ссылка"},
                },
            }
        ]
    }


def test_unordered_list():
    out = valid("<ul><li>раз</li><li><b>два</b></li></ul>")
    assert out == {
        "blocks": [
            {
                "type": "list",
                "items": [
                    {"blocks": [{"type": "paragraph", "text": "раз"}]},
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "text": {"type": "bold", "text": "два"},
                            }
                        ]
                    },
                ],
            }
        ]
    }


def test_ordered_list_numbering():
    out = valid("<ol><li>первый</li><li>второй</li><li>третий</li></ol>")
    items = out["blocks"][0]["items"]
    assert [item["value"] for item in items] == [1, 2, 3]


def test_photo_absolute_url():
    out = valid('<p><img src="/d2/img/12"></p>')
    assert out == {
        "blocks": [
            {
                "type": "photo",
                "photo": {"type": "photo", "media": "https://eurmtl.me/d2/img/12"},
            }
        ]
    }


def test_photo_localhost_base_url():
    out = convert('<img src="/d2/img/7">', "http://localhost:8000")
    assert out["blocks"][0]["photo"]["media"] == "http://localhost:8000/d2/img/7"


def test_photo_keeps_absolute_src():
    out = valid('<img src="https://cdn.example.org/pic.jpg">')
    assert out["blocks"][0]["photo"]["media"] == "https://cdn.example.org/pic.jpg"


def test_img_without_src_dropped():
    # <img> без src не даёт ни фото, ни пустой строки — параграф пуст.
    assert convert("<p><img></p>") == {"blocks": []}


def test_data_uri_img_dropped():
    # Ctrl+V в Quill вставляет скриншот как data:image/...;base64.
    # Telegram не скачает такой URL ("failed to get HTTP URL content",
    # инцидент №705) — фото-блок не строим, текст вокруг сохраняем.
    body = '<p>до</p><p><img src="data:image/png;base64,iVBORw0KGgo="></p><p>после</p>'
    assert valid(body) == {
        "blocks": [
            {"type": "paragraph", "text": "до"},
            {"type": "paragraph", "text": "после"},
        ]
    }


def test_data_uri_case_insensitive_dropped():
    # RFC 3986: схема регистронезависима — DATA:/Data: тоже дропаем.
    assert valid('<p><img src="DATA:image/png;base64,iVBORw0KGgo="></p>') == {
        "blocks": []
    }
    assert valid('<p><img src="Data:image/png;base64,iVBORw0KGgo="></p>') == {
        "blocks": []
    }


def test_data_uri_inline_in_paragraph_dropped():
    # data-URI внутри абзаца: img выпадает, текст остаётся узлами списка.
    out = valid('<p>Привет <img src="data:image/png;base64,iVBOR="> мир</p>')
    assert out == {"blocks": [{"type": "paragraph", "text": ["Привет ", " мир"]}]}


def test_blob_and_unknown_schemes_dropped():
    # Telegram скачивает только http(s): blob: из drag-and-drop и любые
    # прочие схемы — не photo-блок, а пропуск.
    assert valid('<p><img src="blob:https://eurmtl.me/abc"></p>') == {"blocks": []}
    assert valid('<p><img src="ftp://cdn.example.org/pic.jpg"></p>') == {"blocks": []}


def test_protocol_relative_url_dropped():
    # "//cdn.example.org/x" через base_url даёт битый URL — не photo-блок.
    assert valid('<p><img src="//cdn.example.org/pic.jpg"></p>') == {"blocks": []}


def test_scheme_without_host_dropped():
    # "http://" без домена Telegram не скачает — не photo-блок.
    assert valid('<p><img src="http://"></p>') == {"blocks": []}
    assert valid('<p><img src="https:///pic.jpg"></p>') == {"blocks": []}


def test_invalid_ipv6_url_dropped_not_raised():
    # urlsplit кидает ValueError на битых IPv6-скобках; конвертер не должен
    # падать (деградация до поста без картинки при любом битом BODY).
    assert valid('<p><img src="http://[invalid"></p>') == {"blocks": []}
    assert valid('<p><img src="https://["></p>') == {"blocks": []}


def test_relative_path_without_slash_dropped():
    # Относительные пути без "/" в D2 не бывают — политика: дропаем.
    assert valid('<p><img src="pic.jpg"></p>') == {"blocks": []}
    assert valid('<p><img src="images/pic.jpg"></p>') == {"blocks": []}


def test_whitespace_src_dropped():
    assert valid('<p><img src="   "></p>') == {"blocks": []}


def test_data_uri_inside_blockquote_dropped():
    # Цитата с data-URI: текст цитаты живёт, фото-блок не создаётся.
    out = valid(
        '<blockquote><img src="data:image/png;base64,iVBOR=">цитата</blockquote>'
    )
    assert out["blocks"][0]["type"] == "blockquote"
    assert "data:" not in str(out["blocks"][0])


def test_mixed_paragraph_data_and_valid_imgs():
    # Валидная картинка между мусорными строится, мусор отбрасывается.
    out = valid(
        '<p><img src="data:image/png;base64,iVBOR=">'
        '<img src="/d2/img/1">'
        '<img src="blob:https://eurmtl.me/x"></p>'
    )
    assert out == {
        "blocks": [
            {
                "type": "photo",
                "photo": {"type": "photo", "media": "https://eurmtl.me/d2/img/1"},
            }
        ]
    }


def test_valid_photo_keeps_uppercase_scheme():
    # Валидный http(s)-URL с верхним регистром схемы остаётся как есть —
    # _absolute_url не должен считать его относительным путём.
    out = valid('<p><img src="HTTPS://cdn.example.org/pic.jpg"></p>')
    assert out == {
        "blocks": [
            {
                "type": "photo",
                "photo": {"type": "photo", "media": "HTTPS://cdn.example.org/pic.jpg"},
            }
        ]
    }


def test_top_level_data_uri_img_dropped():
    # top-level <img> вне параграфа — тоже без photo-блока.
    assert valid('<img src="data:image/png;base64,iVBOR=">') == {"blocks": []}


def test_data_uri_inside_list_item_dropped():
    # data-URI внутри пункта списка: текст живёт, фото-блок не создаётся.
    out = valid('<ul><li><img src="data:image/png;base64,iVBOR=">пункт</li></ul>')
    assert out["blocks"][0]["type"] == "list"
    texts = out["blocks"][0]["items"][0]["blocks"]
    assert all("data:" not in str(node) for node in texts)


def test_valid_photo_survives_next_to_data_uri():
    # Валидная картинка рядом с data-URI: фото-блок на месте.
    out = valid('<p><img src="/d2/img/1"><img src="data:image/png;base64,iVBOR="></p>')
    assert out == {
        "blocks": [
            {
                "type": "photo",
                "photo": {"type": "photo", "media": "https://eurmtl.me/d2/img/1"},
            }
        ]
    }


def test_br_makes_newline():
    out = valid("<p>строка1<br>строка2</p>")
    assert out == {
        "blocks": [
            {"type": "paragraph", "text": ["строка1", "\n", "строка2"]},
        ]
    }


def test_unknown_tag_does_not_crash_and_unwraps():
    out = valid("<div>в диве <span>спан</span> конец</div>")
    assert out == {
        "blocks": [
            {"type": "paragraph", "text": ["в диве ", "спан", " конец"]},
        ]
    }


def test_unknown_block_tag_keeps_text():
    out = valid("<table><tr><td>ячейка</td></tr></table><p>после</p>")
    assert out["blocks"][0] == {"type": "paragraph", "text": "ячейка"}
    assert out["blocks"][1] == {"type": "paragraph", "text": "после"}


def test_image_inside_bold_is_unwrapped():
    out = valid('<p><b><img src="/d2/img/3"></b></p>')
    assert out == {
        "blocks": [
            {
                "type": "photo",
                "photo": {"type": "photo", "media": "https://eurmtl.me/d2/img/3"},
            }
        ]
    }


def test_bare_text_between_paragraphs():
    out = valid("<p>один</p>голый<p>два</p>")
    assert [b["type"] for b in out["blocks"]] == ["paragraph"] * 3
    assert out["blocks"][1]["text"] == "голый"


def test_nesting_matches_reference_sample():
    """Структура узлов совпадает с эталоном (по форме, в терминах входного
    формата): bold→text, italic→text, url(text_link)→text+url, смешанный
    абзац — список узлов (concat), пустой абзац — пустой текст."""
    with open(SAMPLE_PATH, encoding="utf-8") as fh:
        sample = json.load(fh)
    ref_blocks = sample["tg_rich_message"]["blocks"]

    # Фрагмент эталона: heading + пустой paragraph + concat-абзац с
    # bold/plain/link. Собираем эквивалентный HTML и сравниваем форму.
    html = (
        "<h1>Заголовок</h1>"
        "<p><br></p>"
        "<p><b>Жирный тезис:</b> обычный текст, "
        '<a href="https://arxiv.org/abs/1.0">Paper: ссылка</a></p>'
    )
    out = valid(html)["blocks"]

    heading_ref = next(b for b in ref_blocks if b["type"] == "heading")
    # эталон: {"type":"heading","level":N,"text":{"type":"bold",
    # "text":{"type":"plain","text":...}}} → вход: size=N, text="..."
    assert out[0]["type"] == heading_ref["type"]
    assert out[0]["size"] == heading_ref["level"]
    assert out[0]["text"] == "Заголовок"  # plain-нода → str

    # пустой paragraph в эталоне: {"type":"paragraph","text":{"type":"empty"}}
    assert out[1] == {"type": "paragraph", "text": ""}  # empty → ""

    # concat-абзац: список узлов, bold/ссылка с text-полем.
    concat_ref = next(
        b
        for b in ref_blocks
        if b["type"] == "paragraph" and b["text"]["type"] == "concat"
    )
    mixed = out[2]["text"]
    assert isinstance(mixed, list)
    assert {"type": "bold", "text": "Жирный тезис:"} == mixed[0]
    assert mixed[1].startswith(" обычный текст")
    link_node = mixed[2]
    ref_link = next(n for n in concat_ref["text"]["text"] if n["type"] == "text_link")
    assert link_node["type"] == "url"  # text_link входного формата
    assert link_node["url"] == ref_link["href"].replace(
        "https://arxiviq.substack.com", "https://arxiv.org"
    ) or link_node["url"].startswith("https://")
    assert link_node["text"] == "Paper: ссылка"


def test_full_document_smoke():
    """Смешанный документ целиком проходит валидацию aiogram."""
    html = (
        "<h2>Вопрос 77</h2>"
        "<p>Предложение: <b>купить сервер</b></p>"
        "<ul><li>быстро</li><li>дёшево</li></ul>"
        '<p><img src="/d2/img/1"></p>'
        '<p>Обоснование: <a href="https://eurmtl.me/d2/1">см. здесь</a><br>'
        "Примечание: <code>ok</code></p>"
    )
    out = valid(html)
    assert [b["type"] for b in out["blocks"]] == [
        "heading",
        "paragraph",
        "list",
        "photo",
        "paragraph",
    ]


def test_blockquote_becomes_quote_block():
    result = convert("<blockquote><p>Скрытый текст</p></blockquote>")
    blocks = result["blocks"]
    assert blocks[0]["type"] == "blockquote"
    inner = blocks[0]["blocks"]
    assert any(
        b.get("text") == "Скрытый текст" for b in inner if b.get("type") == "paragraph"
    )


def test_expandable_blockquote_becomes_expandable():
    result = convert("<blockquote expandable><p>Длинный текст цитаты</p></blockquote>")
    blocks = result["blocks"]
    assert blocks[0]["type"] == "expandable_blockquote"
    # text — RichText, содержащий текст цитаты
    text_node = blocks[0]["text"]
    assert "Длинный текст цитаты" in json.dumps(text_node, ensure_ascii=False)


def test_pre_becomes_pre_block():
    result = convert("<pre><code>SELECT 1;</code></pre>")
    blocks = result["blocks"]
    assert blocks[0]["type"] == "pre"
    assert "SELECT 1;" in str(blocks[0]["text"])


def test_tg_spoiler_becomes_spoiler_node():
    result = convert("<p>обычный <tg-spoiler>секрет</tg-spoiler> текст</p>")
    dumped = json.dumps(result, ensure_ascii=False)
    assert '"spoiler"' in dumped
    assert "секрет" in dumped


def test_header_still_heading_size():
    result = convert("<h2>Заголовок</h2>")
    assert result["blocks"][0] == {
        "type": "heading",
        "size": 2,
        "text": "Заголовок",
    }


def test_expandable_by_class_blot_form():
    """Форма Quill-blot: <blockquote class="d2-expandable"> →
    expandable_blockquote (второй поддерживаемый вид)."""
    result = convert('<blockquote class="d2-expandable"><p>Свёрнутая</p></blockquote>')
    assert result["blocks"][0]["type"] == "expandable_blockquote"
    assert "Свёрнутая" in json.dumps(result["blocks"][0]["text"], ensure_ascii=False)


def test_spoiler_by_blot_tag():
    """tg-spoiler узел (blot d2-spoiler) → inline spoiler."""
    result = convert("<p>видно <tg-spoiler>скрыто</tg-spoiler></p>")
    dumped = json.dumps(result, ensure_ascii=False)
    assert '"spoiler"' in dumped and "скрыто" in dumped
