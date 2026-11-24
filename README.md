# research-cli

A personal research assistant for the terminal. Ask a question, and it searches the web, reads the sources and writes a Markdown report where every claim is cited.

[Leer en español](README.es.md)

![tests](https://github.com/alejandro-orbis/research-cli/actions/workflows/tests.yml/badge.svg)

```
$ python research.py "What are the advantages of n8n over Make?"
🧠 Planning searches...
🌐 Searching sources...
  🔎 n8n vs Make advantages and differences
  🔎 n8n self hosting vs Make
  🔎 n8n vs Make pricing and limitations
   8 unique sources
✍️  Writing report...
💾 Saved to reports/20261122-1504-what-are-the-advantages-of-n8n-over-make.md
```

📄 **[See a full example report](examples/n8n-vs-make.md)**

## How it works

```
question ──► 1. Plan ──► 2. Search ──► 3. Synthesize ──► 4. Save
             (Gemini)    (Tavily)      (Gemini)          reports/*.md
```

1. **Plan** – Gemini splits your question into several focused web searches.
2. **Search** – Tavily runs each search and returns the full page content, not just links. Duplicate URLs are removed.
3. **Synthesize** – Gemini writes a report using **only** those sources, citing each claim as `[n]`.
4. **Save** – The report is stored as a timestamped Markdown file, followed by the list of sources it actually cites.

Keeping search and writing as separate steps, and grounding the answer in retrieved sources, makes the output easier to verify than asking a chatbot directly.

## Features

- **Cited answers** – every claim points to a numbered source.
- **Bias awareness** – sources published by a vendor about its own product are flagged, and independent sources are preferred when they disagree.
- **Contradiction detection** – when sources disagree, the report says so instead of picking one silently.
- **Clean source list** – only sources actually cited in the report are listed, keeping their original numbers so every `[n]` still matches.
- **Resilient to API outages**:
  - Temporary server errors (5xx) are retried with exponential backoff.
  - If a model stays unavailable, it falls back to the next one in your list.
  - Every request has a 60-second timeout, so the CLI never hangs silently.
  - Client errors (bad key, unknown model) fail fast with a clear message.
  - Requests that time out switch straight to the next model.
- **Bilingual reports** – English or Spanish with `--lang`.
- **Deep mode** – with `--deep`, the assistant reviews its own draft, searches for gaps (missing info, single-source claims, disagreements) and rewrites the report with the new sources.

## Requirements

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier available)
- A [Tavily API key](https://app.tavily.com) (free tier available)

## Installation

```bash
git clone https://github.com/<your-user>/research-cli.git
cd research-cli
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Then open `.env` and add your API keys.

## Usage

```bash
python research.py "What are the trade-offs of n8n vs Make for enterprises?"
```

| Option | Description | Default |
|---|---|---|
| `--lang en\|es` | Report language | `en` |
| `--searches N` | Number of web searches | `3` |
| `--results N` | Results per search | `3` |
| `--no-save` | Print the report without saving it | off |
| `--exclude a.com,b.com` | Skip these domains | none |
| `--include a.com,b.com` | Only search these domains | all |
| `--deep` | Review the draft, search for missing information and rewrite | off |

Examples:

```bash
# Deeper research, report in Spanish
python research.py "Impact of the EU AI Act on small businesses" --searches 5 --lang es

# Quick look, don't save
python research.py "Latest stable Python version" --searches 1 --no-save
```

Reports are saved to `reports/` (ignored by git).

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | yes | Google Gemini API key |
| `TAVILY_API_KEY` | yes | Tavily search API key |
| `GEMINI_MODEL` | no | Comma-separated list of models, tried in order |
| `EXCLUDE_DOMAINS` | no | Domains to always skip, comma-separated (overridden by `--exclude`) |

Default model order:

```
GEMINI_MODEL=gemini-3.5-flash,gemini-3.7-flash,gemini-3.5-flash-lite
```

The first model is used for quality; the `-lite` model at the end acts as a safety net, since it is rarely overloaded. Variables can be set in `.env` or exported in your shell.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Missing environment variable` | `.env` missing or misnamed variable | Check `.env` is next to `research.py` |
| `404 NOT_FOUND` (model) | Model renamed or retired by Google | Update `GEMINI_MODEL` (list available models with `client.models.list()`) |
| `503 UNAVAILABLE` | Model overloaded | Handled automatically; if all models fail, try again later |
| `InvalidAPIKeyError` | Wrong Tavily key | Keys start with `tvly-`; no quotes or spaces |

## Roadmap

- [x] Unit tests with pytest + GitHub Actions
- [x] Parallel web searches
- [x] Deep mode (`--deep`): detect gaps and run a second round of searches
- [x] Include/exclude domains (e.g. skip video sites and forums)
- [ ] Follow-up questions on an existing report (`--chat`)
- [ ] Local history of past reports (SQLite)

## About

Built with AI assistance, then tested, debugged and extended by me as a learning and portfolio project.

## License

[MIT](LICENSE)
