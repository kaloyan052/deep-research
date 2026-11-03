# 🔬 Deep Research Workspace

Папка, с която всеки AI агент (Antigravity, Claude Code, Codex, Cursor…) прави дълбоки
проучвания, които **издържат на проверка**: всяко твърдение има източник, който наистина го
казва; несигурността е казана честно; изводът е тестван срещу най-силните доводи против него.

Качеството се мери с това, което оцелява при проверка — не с дължина, диаграми или тон.

---

## Как се ползва

Кажете на агента: *„направи deep research за …“* / *„проучи подробно …“*.

Агентът чете `AGENTS.md` (Claude Code — `CLAUDE.md`) и следва протокола
[`.agents/skills/deep-research/SKILL.md`](.agents/skills/deep-research/SKILL.md):

1. **Обхват** — точен въпрос, решението, тезата на потребителя, 4–8 подвъпроса и
   **≥ 3 „убиващи хипотези“** (как тезата може да е грешна), написани *преди* търсенето → `plan.md`
2. **Доказателства** — търсачката дава само следи. Всяка страница се изтегля
   (`evidence.py fetch` → snapshot + SHA-256), а фактът се записва с **дословен цитат**
   (`evidence.py add`), който инструментът отказва, ако не е буквално в страницата.
   ≥ 30% от търсенията отиват за опит да се *потвърдят* убиващите хипотези.
   При много източници (100–500) агентът не чете страниците цели: `corpus.py` ги индексира
   (BM25) и дава подредени пасажи по всеки подвъпрос, плюс слепите петна и „изненадите“.
3. **Противоречия** — фактите влизат в регистър (`claims.py`), който сам открива конфликтите и
   оста им (обхват, време, метод, единица, авторитет, правило срещу практика). Всеки конфликт
   трябва да е в доклада с доказателства от двете страни.
4. **Доклад** — всяко изречение с число цитира `[E###]`; числото трябва да е в цитата
   (иначе `Calculation:`); всяко противоречащо доказателство трябва да е адресирано.
5. **Сляп одит** — независим проверител, който не е виждал проучването, проверява извадка от
   изреченията срещу цитатите (`audit.py`). Резултатът е горна граница на грешките
   („≤ X% при 95%“), не „100% сигурност“. Всяка открита грешка се поправя и се проверява наново.
6. **Пълнота** — всяко търсене записва какво е върнало (`candidates.jsonl`). `screening.py` проверява
   случайна извадка от неотворените следи и дава горна граница на изгубените релевантни
   източници; `corpus.py stats` оценява покритието (Chapman) и насищането.
7. **Гейт (задължителен)** — една команда:

```bash
.venv/Scripts/python.exe dr_engine/tools/gate.py research/<папка> --live 5 --scorecard --require-audit
```

| Инструмент | Какво прави |
| :-- | :-- |
| `next_step.py` | Казва единственото следващо действие с точната команда (exit 0 = готово, 1 = има действие, 2 = грешна папка). Агентът го пуска след всяка стъпка — така и по-слаб модел не прескача стъпки |
| `evidence.py` | `retract` (оттегля грешен запис, без ръчна редакция), `init`, `fetch` (snapshot), `import` (ръчно копие от браузър), `add` (отказва неточни цитати), `log-search`, `sources`, `show` |
| `gate.py` | Проверява целостта на snapshot-ите, цитатите, бюджета за убиващи хипотези, цитатите `[E###]`, числата срещу цитатите, адресирането на противоречия, липсата на самооценки; `--live N` изтегля N източника наново |
| `corpus.py` | Индекс на всички изтеглени страници (SQLite FTS5): `build`, `query` (пасажи — точни откъси от страницата), `triage` (ред на четене, слепи петна, изненади, един и същ текст на различни сайтове), `numbers`, `stats` (покритие по Chapman между независими канали и крива на насищане) |
| `discover.py` | Научни бази (OpenAlex, CrossRef, arXiv, EuropePMC) и `--snowball` по цитиранията в OpenAlex (назад: литературата на статията; напред: кой я цитира), с пауза ≥ 1 s между заявките |
| `parse_pdf.py` | PDF → snapshot; таблиците стават редове, които се цитират сами по себе си: `p3.t1 r2: Revenue \| 2025: 1,234 \| 2024: 1,100`, плюс ред с мерната единица. Сканиран PDF без текст се отказва |
| `screening.py` | Проверка на отхвърлените следи: `sample` (20–50, засята извадка), `record`, `bound` (граница на Clopper-Pearson) |
| `claims.py` | Регистър на твърденията: `add` (числото трябва да е в цитата), `conflicts` (конфликти и оси, вкл. конфликт на интереси и различна извадка), `table`, `keys` |
| `units.py` | Единици: bp↔%, RT↔на страна, годишна ставка → разход за задържане, нетно финансиране на long/short, bp → R; същите функции работят в `calc.py` |
| `aliases.json` | Речник на акроними и синоними (CySEC ↔ Cyprus Securities and Exchange Commission, КФН, БНБ, ...); всяко проучване може да има собствен |
| `audit.py` | Сляп одит: `sample` (извадка, засята от доклада), `record` (присъда), `bound` (горна граница на грешките) |
| `check_report.py` / `verify_citations.py` | За доклади извън процеса (напр. старите в `reports/`) |

Дизайнът на v4 и измерванията зад него: [`docs/V4_ARCHITECTURE.md`](docs/V4_ARCHITECTURE.md).

Научни бази (работят без ключове):

```bash
.venv/Scripts/python.exe dr_engine/science/search_arxiv.py --query "ti:retrieval augmented generation" --max_results 10
```

```bash
.venv/Scripts/python.exe dr_engine/science/openalex_cli.py filter works --search "topic" --sort cited_by_count:desc --per-page 10
```

```bash
.venv/Scripts/python.exe dr_engine/science/pubmed_api.py out.json search_pubmed --query "metformin AND aging" --max_results 20
```

---

## Инсталиране (за приятели, които клонират репото)

Нужни са Python 3.10+, git и AI агент, който чете `AGENTS.md` (Claude Code, Codex, Cursor,
Antigravity, ...).

```bash
git clone https://github.com/<owner>/<repo>.git deep-research
cd deep-research
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest tests.test_report_tools
```

(На macOS/Linux: `.venv/bin/python` вместо `.venv/Scripts/python.exe`.)

После отворете папката с агента и кажете: *„направи deep research за …“*. Агентът следва
RUNBOOK-а в `SKILL.md` и след всяка стъпка пуска `next_step.py`, докато не отпечата `DONE`.

Незадължително:
- `OPENALEX_MAILTO=you@example.com` в средата — OpenAlex ви слага в по-бързия „polite pool“.
  Адресът се взима само от тази променлива, никъде не е записан в кода.
- Допълнителни умения от skills.sh (чужди, със собствени лицензи):
  `npx skills add wshobson/agents -s session-guard -y` (срещу отклонение при дълги сесии),
  `npx skills add wshobson/agents -s grounded-vault -y` (база знания с проследими източници),
  `npx skills add tradermonty/claude-trading-skills -s backtest-expert -y` (за трейдинг проучвания).
- `evidence.py fetch` никога не праща адреси към външни „reader“ услуги, освен ако изрично не
  подадете `--jina` (r.jina.ai вижда адреса).

## Структура на репото

```
├── AGENTS.md / CLAUDE.md          # Входна точка за всеки AI агент
├── .agents/
│   ├── rules/deep-research.md     # Кратки винаги-активни правила
│   └── skills/
│       ├── deep-research/         # Протоколът: SKILL.md (RUNBOOK), templates/, references/
│       ├── doubt-driven-development/
│       └── source-driven-development/
├── .claude/skills/deep-research/  # Указател към протокола за Claude Code
├── dr_engine/
│   ├── tools/                     # evidence, discover, corpus, claims, calc, units, audit,
│   │                              # screening, formula, gate, next_step, parse_pdf, ...
│   ├── science/                   # arXiv, OpenAlex, PubMed (Apache-2.0, google-deepmind/science-skills)
│   ├── evals/                     # 32 епистемични теста за гейтовете
│   └── quant/                     # alpha_miner.py
├── docs/V4_ARCHITECTURE.md        # Дизайнът на протокола и измерванията зад него
├── research/                      # Тук се създават вашите проучвания (не се качват в git)
├── reports/                       # Тук отиват финалните доклади (не се качват в git)
└── tests/test_report_tools.py     # .venv/Scripts/python.exe -m unittest tests.test_report_tools
```

`research/` и `reports/` са в `.gitignore`: проучванията ви остават локални, освен ако
сами не решите да ги споделите.

## Произход на идеите

Рекурсивно търсене с широчина/дълбочина — [`dzhng/deep-research`](https://github.com/dzhng/deep-research);
разделение на роли — [`temporalio/edu-deep-research-tutorial-template`](https://github.com/temporalio/edu-deep-research-tutorial-template);
скеле преди писане, триангулация, рубрика — [`aws-samples/sample-agentcore-deep-research`](https://github.com/aws-samples/sample-agentcore-deep-research);
научни инструменти — [`google-deepmind/science-skills`](https://github.com/google-deepmind/science-skills).
