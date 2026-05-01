# Agent Discovery And Skill Publishing

## Контекст
Сайт уже начал публиковать машинные entrypoints через `GET /llms.txt` и `GET /robots.txt`, но для agent discovery все еще не хватает стандартных ресурсов: `sitemap.xml`, `/.well-known/api-catalog`, discovery `Link` headers на homepage и web-published `SKILL.md` с индексом `/.well-known/agent-skills/index.json`.

## План изменений
1. [ ] Добавить red-phase тесты для `sitemap.xml`, `api-catalog`, homepage `Link` headers и agent-skills discovery.
2. [ ] Расширить `robots.txt`: добавить `Sitemap:` и явные AI crawler groups без изменения действующих служебных disallow правил.
3. [ ] Опубликовать `GET /sitemap.xml` с каноническими публичными URL.
4. [ ] Опубликовать `GET /.well-known/api-catalog` в формате `application/linkset+json`.
5. [ ] Добавить `Link` response headers на `GET /`, указывающие на `api-catalog`, `llms.txt` и agent-skills index.
6. [ ] Опубликовать `GET /.well-known/agent-skills/index.json` и `GET /.well-known/agent-skills/eurmtl-http/SKILL.md`.
7. [ ] Сократить `llms.txt` до overview + ссылок на discovery resources и published skill.
8. [ ] Прогнать фокусные тесты и `check-changed`.

## Риски и открытые вопросы
- Не публиковать фиктивные OAuth/MCP/WebMCP endpoints без реальной серверной поддержки.
- Не включить в `sitemap.xml` нестабильные или параметризованные URL, которые не являются каноническими.
- Держать `llms.txt` и `SKILL.md` в разных ролях: overview против procedural guidance.

## Верификация
- `uv run --extra dev pytest tests/routers/test_index.py --no-cov -q`
- `just check-changed`
