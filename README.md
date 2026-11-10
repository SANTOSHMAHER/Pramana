# Pramana

Pramana is an evidence-grounded chatbot for Python 3.14.3. Its name is inspired
by *pramāṇa*, a Sanskrit philosophical term for a valid means of knowledge.
Choose local Ollama, Google Gemini, or OpenAI GPT for answer generation. Ollama
creates local embeddings, and FAISS stores and searches the FAQ and uploaded
document vectors on this computer.

## Requirements

- Windows
- Python 3.14.3
- Ollama installed and running at `http://127.0.0.1:11434` for local chat and
  for document/FAQ embeddings (required for retrieval)
- Ollama models `qwen2.5:1.5b` and `all-minilm`, unless using other model names

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
PRAMANA_DEFAULT_PROVIDER=ollama
# Optional; use VS Code SecretStorage for keys when using the extension.
PRAMANA_GEMINI_API_KEY=
PRAMANA_OPENAI_API_KEY=
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
| `PRAMANA_DEFAULT_PROVIDER` | `ollama` | Default provider: `ollama`, `gemini`, or `openai` |
| `PRAMANA_GEMINI_API_KEY` / `PRAMANA_GEMINI_MODEL` | empty / `gemini-2.5-flash` | Optional Google Gemini setup |
| `PRAMANA_OPENAI_API_KEY` / `PRAMANA_OPENAI_MODEL` | empty / `gpt-4.1-mini` | Optional OpenAI GPT setup |
| `PRAMANA_VECTOR_INDEX_DIR` | `.pramana/index` | Persistent local FAISS vectors and metadata |
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

Model answers can be inaccurate; verify important information. Embeddings are
created by Ollama and persisted in a local FAISS index. The first semantic
request embeds new FAQ patterns. If the embedding model changes, delete the
configured vector-index directory so Pramana can rebuild it. Online models
receive your question, chat history, and retrieved document excerpts; avoid
sending sensitive data to them.

## Upload documents

Use **Add documents** in the web chat, or the upload command in the VS Code
extension. Each request accepts at most five documents, each no larger than
2 MB. The backend extracts text, splits it into overlapping chunks, embeds the
chunks locally, and adds them to FAISS with each source document kept separate.
Uploads run as background jobs and expose a status endpoint. The app allows up
to five upload requests per minute per client. Uploaded files are not copied
into the project; their searchable text and source metadata are stored in the
FAISS metadata file under `.pramana/index`.

Supported formats: PDF, DOCX, TXT, Markdown, PNG, JPEG, WEBP, BMP, TIFF,
PPT/PPTX, and XLS/XLSX. OCR for images requires the Tesseract executable to be
installed. Legacy `.ppt` conversion requires LibreOffice. Image-only PDFs may
not contain extractable text. Unsupported or unreadable files are reported per
document.

## VS Code extension

The extension bundles the backend source and bootstraps its dependencies into
VS Code global storage on first launch. Python 3.14 must already be installed;
the extension does not bundle a Python runtime. On Windows it uses `py -3.14`;
on macOS/Linux configure `pramana.pythonPath` to `python3.14`. Ollama remains
necessary for embeddings and local inference.

From `vscode-extension`, install dependencies and build the installable VSIX:

```powershell
npm.cmd install
npm.cmd run package
```

Install the resulting `pramana-chatbot-0.1.0.vsix` in VS Code. Run
**Pramana: Configure Providers** to store Gemini/OpenAI keys in VS Code
SecretStorage and set model names; run **Pramana: Open Chat** to start the
local backend and open the integrated panel. Uploaded documents and FAISS
index files are stored in VS Code global storage. The default local server port
is `5031`; configure `pramana.port` if it is occupied.

## Project layout

```text
.env                    Local paths, model, port, and display-name settings
.env.example            Template for creating/editing .env
.gitignore              Excludes local environment and configuration
run.bat                 Creates the local environment and starts the app
config.py               Reads .env and resolves settings and data paths
app.py                  Flask routes, FAQ retrieval, chat, and upload APIs
providers.py            Ollama, Gemini, and OpenAI provider integration
rag.py                  FAQ and document embedding/indexing operations
documents.py            Supported document extraction and chunking
vector_store.py          Persistent FAISS vectors and document metadata
upload_jobs.py           Background upload job lifecycle
.venv/                  Local Python environment created by run.bat
.pramana/               Local FAISS index, excluded from version control
database/
  test.json             Curated FAQ; used for exact answers and retrieval
  data_address.json     Older FAQ and source-verified local listings
templates/
  index.html            Chat interface
tests/
  test_app.py           Provider, route, upload, dataset, and retrieval tests
vscode-extension/        TypeScript VS Code extension and VSIX packaging
requirements.txt        Python runtime and document extraction dependencies
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
