import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"


def load_env_file(path=ENV_FILE):
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            raise ValueError(f"Invalid setting in {path} on line {line_number}.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def configured_path(setting, default):
    value = Path(os.environ.get(setting, default)).expanduser()
    if not value.is_absolute():
        value = PROJECT_DIR / value
    return value.resolve()


load_env_file()

FAQ_DATA_PATH = configured_path("PRAMANA_FAQ_DATA_PATH", "database/test.json")
LOCAL_DATA_PATH = configured_path(
    "PRAMANA_LOCAL_DATA_PATH", "database/data_address.json"
)
OLLAMA_URL = os.environ.get("PRAMANA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CHAT_MODEL = os.environ.get("PRAMANA_CHAT_MODEL", "qwen2.5:1.5b")
EMBEDDING_MODEL = os.environ.get("PRAMANA_EMBEDDING_MODEL", "all-minilm")
OLLAMA_TIMEOUT = int(os.environ.get("PRAMANA_OLLAMA_TIMEOUT", "120"))
APP_HOST = os.environ.get("PRAMANA_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("PRAMANA_PORT", "5001"))
BOT_NAME = os.environ.get("PRAMANA_BOT_NAME", "Pramana")
BOT_TAGLINE = os.environ.get("PRAMANA_BOT_TAGLINE", "Evidence-grounded local AI")
DEFAULT_PROVIDER = os.environ.get("PRAMANA_DEFAULT_PROVIDER", "ollama").casefold()
if DEFAULT_PROVIDER not in {"ollama", "gemini", "openai"}:
    raise ValueError("PRAMANA_DEFAULT_PROVIDER must be ollama, gemini, or openai.")
GEMINI_API_KEY = os.environ.get("PRAMANA_GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("PRAMANA_GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_API_KEY = os.environ.get("PRAMANA_OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("PRAMANA_OPENAI_MODEL", "gpt-4.1-mini")
VECTOR_INDEX_DIR = configured_path("PRAMANA_VECTOR_INDEX_DIR", ".pramana/index")
MAX_UPLOAD_FILE_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_FILES = 5
UPLOAD_RATE_LIMIT = 5
UPLOAD_RATE_WINDOW_SECONDS = 60
