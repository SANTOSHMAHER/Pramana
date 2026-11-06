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

FAQ_DATA_PATH = configured_path("GARI_FAQ_DATA_PATH", "database/test.json")
LOCAL_DATA_PATH = configured_path(
    "GARI_LOCAL_DATA_PATH", "database/data_address.json"
)
OLLAMA_URL = os.environ.get("GARI_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CHAT_MODEL = os.environ.get("GARI_CHAT_MODEL", "qwen2.5:1.5b")
EMBEDDING_MODEL = os.environ.get("GARI_EMBEDDING_MODEL", "all-minilm")
OLLAMA_TIMEOUT = int(os.environ.get("GARI_OLLAMA_TIMEOUT", "120"))
APP_HOST = os.environ.get("GARI_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("GARI_PORT", "5001"))
BOT_NAME = os.environ.get("GARI_BOT_NAME", "Pramana")
BOT_TAGLINE = os.environ.get("GARI_BOT_TAGLINE", "Evidence-grounded local AI")
