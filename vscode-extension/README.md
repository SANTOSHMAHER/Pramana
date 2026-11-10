# Pramana for VS Code

Pramana is an evidence-grounded chatbot that runs its Python backend locally and
offers local Ollama, Google Gemini, and OpenAI GPT models. The extension includes
the backend source in its VSIX and bootstraps dependencies into VS Code's global
storage on first launch.

## Requirements

- VS Code 1.95 or newer
- Python 3.14 (the extension uses `py -3.14` on Windows by default)
- Ollama and its configured chat and embedding models for local chat and FAISS
  indexing
- Internet access for the initial Python dependency installation and for online
  providers

The extension does not bundle a Python runtime. If the Python launcher differs
on your system, set `pramana.pythonPath` to the Python launcher or interpreter.
On Windows, the default is `py`; on macOS/Linux, set it to `python3.14`.

## Configure providers

Run **Pramana: Configure Providers** from the Command Palette to store Gemini or
OpenAI API keys in VS Code SecretStorage. Provider keys are not written to
workspace settings or the extension's `.env`. Choose the default provider,
model names, and Ollama settings through VS Code's `pramana.*` settings.

The extension starts a loopback-only backend on port `5031` by default. Change
`pramana.port` if that port is in use. Uploaded documents and FAISS vectors are
stored in VS Code global storage, not in the workspace.

## Use

Run **Pramana: Open Chat**. The panel supports model selection, questions,
document uploads, and removing indexed documents. Uploads are limited to five
files per request and 2 MB per file. Supported formats are PDF, DOCX, TXT,
Markdown, common image formats, PPT/PPTX, and XLS/XLSX. Image OCR needs the
Tesseract executable installed; legacy `.ppt` conversion needs LibreOffice.

When Gemini or OpenAI is selected, the question and retrieved document excerpts
are sent to that provider. Avoid uploading sensitive documents when using an
online model. Local FAISS vectors and uploaded-document metadata stay on the
computer.

## Build the VSIX

From this directory:

```powershell
npm install
npm run package
```

The backend files are copied into `backend/` during packaging; generated
backend files are not maintained as a second source tree.
