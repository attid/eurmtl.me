"""Юнит-тесты билдеров d2-поста: подвал чтений (self-link исключён,
ссылки одной строкой через « | ») и принцип 1:1 (никаких авто-добавлений
текста в prefix-формате MTLA/RELY). Решения владельца 2026-11-04."""

import pytest

from routers.decision import _d2_rich_blocks, get_full_text

LINKS = (
    ("https://t.me/c/a/1",),
    ("https://t.me/c/b/2",),
    ("https://t.me/c/c/3",),
)


def _texts(blocks):
    """Строковое представление блоков: параграф-строка, dict-узел — его
    текст, список узлов — склейка (кейс «ссылка | ссылка»)."""
    out = []
    for block in blocks:
        t = block.get("text")
        if isinstance(t, list):
            out.append(
                "".join(
                    node.get("text", "") if isinstance(node, dict) else node
                    for node in t
                )
            )
        elif isinstance(t, dict):
            out.append(t.get("text", ""))
        else:
            out.append(t)
    return out


def test_rich_footer_one_line_no_self_link():
    """Пост чтения 2: подвал — ОДНА строка «Первое чтение | Третье
    чтение», ссылки на само чтение нет («мы же там находимся»)."""
    blocks = _d2_rich_blocks(
        "❗️ #active",
        "<p>Тело</p>",
        org="PFM",
        reading=2,
        links_url=LINKS,
        uuid_url="abc",
        username="@u",
    )
    texts = _texts(blocks)
    assert "Первое чтение | Третье чтение" in texts
    assert "Второе чтение" not in texts
    # Ни одной отдельной строки со ссылкой чтения — только склейка.
    assert "Первое чтение" not in texts


def test_rich_footer_symmetry_reading_1_and_3():
    """Фильтр симметричен: r1 оставляет «Второе | Третье», r3 —
    «Первое | Второе» (ревью аги: покрытие только r2)."""
    cases = {
        1: "Второе чтение | Третье чтение",
        3: "Первое чтение | Второе чтение",
    }
    for reading, expected in cases.items():
        blocks = _d2_rich_blocks(
            "❗️ #active", "<p>Тело</p>", org="PFM", reading=reading, links_url=LINKS
        )
        texts = _texts(blocks)
        assert expected in texts, (reading, texts)


def test_rich_footer_single_link_no_separator():
    """Единственная соседняя ссылка — без « | » (ревью аги: промежуточный
    кейс между «все ссылки» и «ссылок нет»)."""
    blocks = _d2_rich_blocks(
        "❗️ #active",
        "<p>Тело</p>",
        org="PFM",
        reading=1,
        links_url=(None, LINKS[1], None),
    )
    texts = _texts(blocks)
    assert "Второе чтение" in texts
    assert all(" | " not in t for t in texts)


def test_rich_footer_urls_in_nodes():
    """Строка чтений — один параграф-список узлов; url узлов точные, а не
    только тексты (ревью аги: _texts терял атрибут url)."""
    blocks = _d2_rich_blocks(
        "❗️ #active", "<p>Тело</p>", org="PFM", reading=3, links_url=LINKS
    )
    line_blocks = [b for b in blocks if isinstance(b.get("text"), list)]
    assert len(line_blocks) == 1
    nodes = line_blocks[0]["text"]
    assert nodes == [
        {"type": "url", "url": "https://t.me/c/a/1", "text": "Первое чтение"},
        " | ",
        {"type": "url", "url": "https://t.me/c/b/2", "text": "Второе чтение"},
    ]


def test_rich_footer_no_links_no_line():
    """Единственное чтение (ссылка только на себя): строки чтений в
    подвале нет вовсе, служебные ---/- остаются."""
    blocks = _d2_rich_blocks(
        "❗️ #active",
        "<p>Тело</p>",
        org="PFM",
        reading=1,
        links_url=(LINKS[0], None, None),
        uuid_url="abc",
        username="@u",
    )
    texts = _texts(blocks)
    assert "---" in texts and "-" in texts
    assert "Первое чтение" not in texts


def test_rich_prefix_no_auto_topic_line():
    """1:1 (MTLA/RELY): тег чтения в статус-строке — управляющая штука,
    остаётся; авто-строки «Вопрос N: Тема» в посте НЕТ — тело как в
    редакторе."""
    for org in ("MTLA", "RELY"):
        blocks = _d2_rich_blocks(
            "❗️ #active",
            "<p>Тело как в редакторе</p>",
            org=org,
            reading=1,
        )
        texts = _texts(blocks)
        assert texts[0] == "❗️ #active #first_reading", org
        assert "Тело как в редакторе" in texts
        assert all("Вопрос" not in t for t in texts)


@pytest.mark.parametrize(
    "reading,tag",
    [(2, "#second_reading"), (3, "#third_reading")],
)
def test_rich_prefix_reading_tags(reading, tag):
    """Тег чтения в prefix-формате для чтений 2/3 (ревью аги, круг 3)."""
    blocks = _d2_rich_blocks("❗️ #active", "<p>Тело</p>", org="MTLA", reading=reading)
    assert _texts(blocks)[0] == f"❗️ #active {tag}"


def test_legacy_footer_one_line_no_self_link():
    text = get_full_text(
        "❗️ #active",
        "<p>Тело</p>",
        LINKS,
        "abc",
        "@u",
        2,
    )
    lines = text.split("<br>")
    assert (
        '<a href="https://t.me/c/a/1">Первое чтение</a> | '
        '<a href="https://t.me/c/c/3">Третье чтение</a>'
    ) in lines
    assert "Второе чтение" not in text


def test_legacy_footer_no_links_no_line():
    """Ссылок (после фильтра self-link) нет — между --- и - пусто."""
    text = get_full_text(
        "❗️ #active",
        "<p>Тело</p>",
        (LINKS[0], None, None),
        "abc",
        "@u",
        1,
    )
    lines = text.split("<br>")
    assert lines[2] == "---" and lines[3] == "-"
    assert "Первое чтение" not in text


def test_legacy_footer_single_link_no_separator():
    """Единственная соседняя ссылка — без « | » (ревью аги, круг 2)."""
    text = get_full_text(
        "❗️ #active", "<p>Тело</p>", (None, LINKS[1], None), "abc", "@u", 1
    )
    assert '<a href="https://t.me/c/b/2">Второе чтение</a>' in text.split("<br>")
    assert " | " not in text


def test_legacy_footer_reading_default_keeps_all_links():
    """Дефолтный reading=0 — фильтр self-link не активируется (обратная
    совместимость вызовов без reading; ревью аги, круг 2)."""
    text = get_full_text("❗️ #active", "<p>Тело</p>", LINKS, "abc", "@u")
    assert "Первое чтение" in text
    assert "Второе чтение" in text
    assert "Третье чтение" in text
