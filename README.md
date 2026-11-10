# Pramana

Pramana is a local Flask chatbot for Python 3.14.3. Its name is inspired by
*pramāṇa*, a Sanskrit philosophical term for a valid means of knowledge. The
assistant prioritizes evidence-backed answers and identifies its verified
local sources. It uses Ollama for a local language model and local semantic
search. It does not send questions or FAQ content to a hosted AI provider.

## Requirements

- Windows
- Python 3.14.3
- Ollama installed and running at `http://127.0.0.1:11434`
- Ollama models `qwen2.5:1.5b` and `all-minilm`

Install Ollama and its models if they are not installed:

```powershell
winget install --id Ollama.Ollama
ollama pull qwen2.5:1.5b
ollama pull all-minilm
```

## Run the application on Windows

Keep this project folder together when moving or copying the app. Double-click
`run.bat`, or run it from Command Prompt. It creates `.env` from `.env.example`
if needed, creates a project-local `.venv`, installs the requirements, and
starts the chatbot:

```bat
run.bat
```

On the first run, edit `.env` before launching if your data files or Ollama
server are not at their default locations. Paths may be absolute Windows paths
or relative to this project folder. Use forward slashes or escaped backslashes
for absolute paths, for example:

```dotenv
PRAMANA_FAQ_DATA_PATH=C:/Chatbot/data/test.json
PRAMANA_LOCAL_DATA_PATH=C:/Chatbot/data/data_address.json
PRAMANA_OLLAMA_URL=http://127.0.0.1:11434
PRAMANA_PORT=5001
```

`.env` is local configuration and is excluded from version control. The
`.env.example` file documents all supported options. Keep `database/` and
`templates/` alongside `app.py` unless you update the corresponding data paths
in `.env`.

| Setting | Default | Purpose |
|---|---|---|
| `PRAMANA_FAQ_DATA_PATH` | `database/test.json` | FAQ JSON path |
| `PRAMANA_LOCAL_DATA_PATH` | `database/data_address.json` | Legacy FAQ and verified local listings path |
| `PRAMANA_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server URL |
| `PRAMANA_CHAT_MODEL` | `qwen2.5:1.5b` | Ollama response model |
| `PRAMANA_EMBEDDING_MODEL` | `all-minilm` | Ollama embedding model |
| `PRAMANA_OLLAMA_TIMEOUT` | `120` | Ollama request timeout in seconds |
| `PRAMANA_HOST` / `PRAMANA_PORT` | `127.0.0.1` / `5001` | Flask bind address |
| `PRAMANA_BOT_NAME` | `Pramana` | Name shown in the UI and model instructions |
| `PRAMANA_BOT_TAGLINE` | `Evidence-grounded local AI` | Bot description shown in the UI |

Open [http://127.0.0.1:5001](http://127.0.0.1:5001) (or the configured port).
To stop the server, press Ctrl+C in its terminal. Keep Ollama running while
chatting.

The local Python environment is stored inside the project at `.venv/`; you do
not need a separate environment in a parent folder. It is generated locally
and should not be copied as part of project distribution.

## How answers are produced

1. The current chat is kept in this browser tab and restored if the page is
   refreshed. Separate tabs and the **New chat** button start isolated
   conversations. Up to the 40 most recent messages (20 exchanges), within
   a 7,500-character context budget, are sent with each request so follow-up
   questions can use earlier context.
2. The app checks for an exact, case- and punctuation-normalized question in
   the curated FAQ. If it finds one, it returns the stored answer.
3. Otherwise, `all-minilm` embeds the question and FAQ patterns. For a
   follow-up, it also uses recent user questions to keep retrieval anchored to
   the active topic. The app retrieves up to four semantically related entries
   and passes those entries and conversation messages to `qwen2.5:1.5b` to
   compose a response.
4. If an exact curated question has only a template/placeholder answer, the app
   abstains rather than filling it in.
5. General educational questions can use the local model's general knowledge.
   Local business, office, address, contact, and other local/current questions
   are answered only when matching FAQ context is available. The model is told
   not to guess unsupported local details.

The local model can still produce inaccurate general information. Verify
important answers. The first semantic-search request after app startup embeds
the FAQ patterns; those vectors are cached in memory until the app restarts.

## Project layout

```text
.env                    Local paths, model, port, and display-name settings
.env.example            Template for creating/editing .env
.gitignore              Excludes local environment and configuration
run.bat                 Creates the local environment and starts the app
config.py               Reads .env and resolves settings and data paths
app.py                  Flask routes, FAQ retrieval, and local Ollama calls
.venv/                  Local Python environment created by run.bat
database/
  test.json             Curated FAQ; used for exact answers and retrieval
  data_address.json     Older FAQ and source-verified local listings
templates/
  index.html            Chat interface
tests/
  test_app.py           Route, dataset, retrieval, and fallback tests
requirements.txt        Python runtime dependencies (Flask)
.python-version         Python version target
README.md               Setup and application overview
DATASET_GUIDE.md        Dataset schema, maintenance, and validation details
```

The older TensorFlow/TFLearn training notebooks, checkpoints, and Python 3.11
environment have been removed from this runtime-focused project. The current
chatbot uses retrieval-augmented generation; it does not retrain the Ollama
language model.

## Update the knowledge base

Read [DATASET_GUIDE.md](DATASET_GUIDE.md) before editing the JSON files. Add
reviewed questions and answers to the configured FAQ file. For local
businesses, addresses, office details, or other time-sensitive facts, use and
record a trusted, current source. Restart the Flask app after changing the
data.

## Run tests

```bat
python -m unittest discover -s tests -v
```
