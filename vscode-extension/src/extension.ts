import { ChildProcess, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import * as vscode from 'vscode';

const SECRET_GEMINI = 'pramana.geminiApiKey';
const SECRET_OPENAI = 'pramana.openaiApiKey';
const MAX_WAIT_MS = 180_000;

class PramanaRuntime {
    private process: ChildProcess | undefined;
    private port = 0;
    private output: vscode.OutputChannel;

    constructor(private readonly context: vscode.ExtensionContext) {
        this.output = vscode.window.createOutputChannel('Pramana');
        context.subscriptions.push(this.output);
    }

    get baseUrl(): string {
        return `http://127.0.0.1:${this.port}`;
    }

    async start(): Promise<string> {
        if (this.process && this.port) {
            try {
                const response = await fetch(`${this.baseUrl}/api/providers`);
                if (response.ok) return this.baseUrl;
            } catch {
                this.process?.kill();
                this.process = undefined;
                this.port = 0;
            }
        }

        const backend = this.findBackend();
        const settings = vscode.workspace.getConfiguration('pramana');
        const pythonCommand = settings.get<string>('pythonPath', 'py');
        const pythonArgs = process.platform === 'win32' && pythonCommand === 'py'
            ? ['-3.14']
            : [];
        const storage = this.context.globalStorageUri.fsPath;
        const environmentPath = join(storage, 'python-env');
        const python = this.pythonInEnvironment(environmentPath);
        mkdirSync(storage, { recursive: true });

        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'Starting Pramana',
                cancellable: false
            },
            async progress => {
                if (!existsSync(python)) {
                    progress.report({ message: 'Creating Python 3.14 environment...' });
                    await this.run(pythonCommand, [
                        ...pythonArgs,
                        '-m',
                        'venv',
                        environmentPath
                    ]);
                    const staleMarker = join(
                        environmentPath,
                        'pramana-dependencies-installed'
                    );
                    if (existsSync(staleMarker)) unlinkSync(staleMarker);
                }
                const marker = join(environmentPath, 'pramana-dependencies-installed');
                const requirementsPath = join(backend, 'requirements.txt');
                const requirementsHash = createHash('sha256')
                    .update(readFileSync(requirementsPath))
                    .digest('hex');
                const installedHash = existsSync(marker)
                    ? readFileSync(marker, 'utf8')
                    : '';
                if (installedHash !== requirementsHash) {
                    progress.report({ message: 'Installing local backend dependencies...' });
                    await this.run(python, [
                        '-m',
                        'pip',
                        'install',
                        '--disable-pip-version-check',
                        '-r',
                        requirementsPath
                    ]);
                    writeFileSync(marker, requirementsHash, 'utf8');
                }
                progress.report({ message: 'Starting local server...' });
                await this.launch(python, backend, settings);
            }
        );
        return this.baseUrl;
    }

    stop(): void {
        if (this.process && !this.process.killed) this.process.kill();
        this.process = undefined;
        this.port = 0;
    }

    private findBackend(): string {
        const bundled = join(this.context.extensionPath, 'backend');
        if (existsSync(join(bundled, 'app.py'))) return bundled;
        const source = resolve(this.context.extensionPath, '..');
        if (existsSync(join(source, 'app.py'))) return source;
        throw new Error(
            'Pramana backend files are missing. Run the extension package script and reinstall the VSIX.'
        );
    }

    private pythonInEnvironment(environmentPath: string): string {
        return process.platform === 'win32'
            ? join(environmentPath, 'Scripts', 'python.exe')
            : join(environmentPath, 'bin', 'python');
    }

    private run(command: string, args: string[]): Promise<void> {
        return new Promise((resolvePromise, rejectPromise) => {
            const child = spawn(command, args, { windowsHide: true });
            let output = '';
            child.stdout.on('data', chunk => {
                output += chunk.toString();
                this.output.append(chunk.toString());
            });
            child.stderr.on('data', chunk => {
                output += chunk.toString();
                this.output.append(chunk.toString());
            });
            child.on('error', rejectPromise);
            child.on('close', code => {
                if (code === 0) resolvePromise();
                else rejectPromise(new Error(output || `${command} exited with code ${code}.`));
            });
        });
    }

    private async launch(
        python: string,
        backend: string,
        settings: vscode.WorkspaceConfiguration
    ): Promise<void> {
        const configuredPort = settings.get<number>('port', 5031);
        this.port = configuredPort;
        const env: NodeJS.ProcessEnv = {
            ...process.env,
            PRAMANA_HOST: '127.0.0.1',
            PRAMANA_PORT: String(configuredPort),
            PRAMANA_DEFAULT_PROVIDER: settings.get<string>('defaultProvider', 'ollama'),
            PRAMANA_OLLAMA_URL: settings.get<string>(
                'ollamaUrl',
                'http://127.0.0.1:11434'
            ),
            PRAMANA_CHAT_MODEL: settings.get<string>(
                'ollamaModel',
                'qwen2.5:1.5b'
            ),
            PRAMANA_EMBEDDING_MODEL: settings.get<string>(
                'embeddingModel',
                'all-minilm'
            ),
            PRAMANA_GEMINI_MODEL: settings.get<string>(
                'geminiModel',
                'gemini-2.5-flash'
            ),
            PRAMANA_OPENAI_MODEL: settings.get<string>(
                'openaiModel',
                'gpt-4.1-mini'
            ),
            PRAMANA_VECTOR_INDEX_DIR: join(
                this.context.globalStorageUri.fsPath,
                'index'
            ),
            PRAMANA_GEMINI_API_KEY:
                (await this.context.secrets.get(SECRET_GEMINI)) || '',
            PRAMANA_OPENAI_API_KEY:
                (await this.context.secrets.get(SECRET_OPENAI)) || ''
        };
        this.process = spawn(python, ['app.py'], {
            cwd: backend,
            env,
            windowsHide: true,
            stdio: ['ignore', 'pipe', 'pipe']
        });
        this.process.stdout?.on('data', chunk => this.output.append(chunk.toString()));
        this.process.stderr?.on('data', chunk => this.output.append(chunk.toString()));
        this.process.on('error', error => {
            this.output.appendLine(`Backend process error: ${error.message}`);
            this.process = undefined;
            this.port = 0;
        });
        this.process.on('close', code => {
            this.output.appendLine(`Backend stopped (exit code ${code ?? 'unknown'}).`);
            this.process = undefined;
            this.port = 0;
        });

        const startedAt = Date.now();
        while (Date.now() - startedAt < MAX_WAIT_MS) {
            if (!this.process || this.process.exitCode !== null) {
                throw new Error(
                    `Pramana backend exited during startup. Check the Pramana output channel.`
                );
            }
            try {
                const response = await fetch(`${this.baseUrl}/api/providers`);
                if (response.ok) return;
            } catch {
                await new Promise(resolvePromise => setTimeout(resolvePromise, 300));
                continue;
            }
            await new Promise(resolvePromise => setTimeout(resolvePromise, 300));
        }
        this.stop();
        throw new Error(
            `Pramana did not start on port ${configuredPort} within ${MAX_WAIT_MS / 1000} seconds.`
        );
    }
}

function chatHtml(nonce: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'; connect-src 'none';">
<title>Pramana</title>
<style>
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:16px;max-width:850px;margin:auto}
header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--vscode-panel-border);padding-bottom:10px}
h1{font-size:18px;margin:0}small,.privacy{color:var(--vscode-descriptionForeground)}
#messages{display:flex;flex-direction:column;gap:12px;padding:18px 0}
.message{white-space:pre-wrap;overflow-wrap:anywhere;padding:10px 12px;border-radius:8px;background:var(--vscode-textBlockQuote-background)}
.user{border-left:3px solid var(--vscode-button-background)}.assistant{border-left:3px solid var(--vscode-focusBorder)}
form,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
textarea{width:100%;min-height:70px;resize:vertical;margin:10px 0;padding:9px;color:var(--vscode-input-foreground);background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);font:inherit}
input,select,button{padding:7px;color:var(--vscode-input-foreground);background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);font:inherit}
button{cursor:pointer;color:var(--vscode-button-foreground);background:var(--vscode-button-background);border:0}
button:disabled{opacity:.55;cursor:default}
.document{display:flex;gap:8px;align-items:center;font-size:12px;padding:4px 0}.status{min-height:22px;color:var(--vscode-descriptionForeground)}
.privacy{font-size:11px;margin-top:12px}
</style>
</head>
<body>
<header><div><h1>Pramana</h1><small>Evidence-grounded local AI</small></div><button id="configure">Configure providers</button></header>
<div class="controls">
<label for="provider">Provider</label><select id="provider"></select>
<label for="model">Model</label><input id="model" maxlength="120">
</div>
<div id="messages" aria-live="polite"></div>
<form id="chat-form"><textarea id="question" maxlength="2000" placeholder="Ask Pramana..." required></textarea><button id="send">Send</button></form>
<section>
<h2>Knowledge documents</h2>
<button id="upload">Upload (up to 5 files, 2 MB each)</button>
<div id="upload-status" class="status" role="status"></div><div id="documents"></div>
</section>
<p class="privacy">Online providers receive your question and retrieved document excerpts. Uploaded files and FAISS vectors are stored locally.</p>
<script nonce="${nonce}">
const vscode=acquireVsCodeApi();
const messages=[];
const providerSelect=document.getElementById('provider');
const modelInput=document.getElementById('model');
const messageBox=document.getElementById('messages');
const statusBox=document.getElementById('upload-status');
const pending=new Map();
let busy=false;
let requestNumber=0;
function apiFetch(path,options={}){const id=String(Date.now())+'-'+String(requestNumber++);return new Promise(resolve=>{pending.set(id,resolve);vscode.postMessage({type:'api',id,path,options})})}
window.addEventListener('message',event=>{const message=event.data;if(message.type==='api-response'){const resolve=pending.get(message.id);if(resolve){pending.delete(message.id);resolve({ok:message.ok,json:async()=>message.data})}}else if(message.type==='upload-status'){statusBox.textContent=message.text;refreshDocuments().catch(error=>{statusBox.textContent=error.message})}});
function addMessage(role,text){const item=document.createElement('div');item.className='message '+role;item.textContent=text;messageBox.appendChild(item)}
async function loadProviders(){const response=await apiFetch('/api/providers');const data=await response.json();if(!response.ok)throw new Error(data.error||'Cannot load providers');providerSelect.replaceChildren();for(const provider of data.providers){const option=document.createElement('option');option.value=provider.id;option.textContent=provider.label+(provider.available?'':' (API key not configured)');option.disabled=!provider.available;option.dataset.model=provider.model;providerSelect.appendChild(option)}providerSelect.value=data.default;if(providerSelect.selectedOptions.length)modelInput.value=providerSelect.selectedOptions[0].dataset.model}
providerSelect.addEventListener('change',()=>{modelInput.value=providerSelect.selectedOptions[0].dataset.model});
document.getElementById('configure').addEventListener('click',()=>vscode.postMessage({type:'configure'}));
document.getElementById('chat-form').addEventListener('submit',async event=>{event.preventDefault();if(busy)return;const input=document.getElementById('question');const question=input.value.trim();if(!question)return;busy=true;document.getElementById('send').disabled=true;input.value='';addMessage('user',question);try{const response=await apiFetch('/get_response',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_input:question,conversation_history:messages.slice(-40),provider:providerSelect.value,model:modelInput.value.trim()})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Chat request failed');const answer=data.bot_response;addMessage('assistant',answer);messages.push({role:'user',content:question},{role:'assistant',content:answer})}catch(error){addMessage('assistant',error instanceof Error?error.message:'Chat request failed')}finally{busy=false;document.getElementById('send').disabled=false}});
async function refreshDocuments(){const response=await apiFetch('/api/documents');const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not list documents');const list=document.getElementById('documents');list.replaceChildren();for(const document of data.documents){const row=document.createElement('div');row.className='document';const name=document.createElement('span');name.textContent=document.filename+' ('+document.chunks+' chunks)';const remove=document.createElement('button');remove.textContent='Remove';remove.addEventListener('click',async()=>{try{const result=await apiFetch('/api/documents/'+encodeURIComponent(document.document_id),{method:'DELETE'});const body=await result.json();if(!result.ok)throw new Error(body.error||'Could not remove document');await refreshDocuments()}catch(error){statusBox.textContent=error instanceof Error?error.message:'Could not remove document'}});row.append(name,remove);list.appendChild(row)}}
document.getElementById('upload').addEventListener('click',()=>{vscode.postMessage({type:'upload'})});
loadProviders().catch(error=>{statusBox.textContent=error instanceof Error?error.message:'Could not load providers'});refreshDocuments().catch(error=>{statusBox.textContent=error instanceof Error?error.message:'Could not list documents'});
</script>
</body>
</html>`;
}

async function apiRequest(
    baseUrl: string,
    path: string,
    options: RequestInit = {}
): Promise<{ ok: boolean; data: unknown }> {
    if (!path.startsWith('/api/') && path !== '/get_response') {
        throw new Error('Unsupported Pramana API request.');
    }
    const response = await fetch(`${baseUrl}${path}`, options);
    const data: unknown = await response.json();
    return { ok: response.ok, data };
}

async function uploadDocuments(
    panel: vscode.WebviewPanel,
    baseUrl: string
): Promise<void> {
    const selected = await vscode.window.showOpenDialog({
        canSelectMany: true,
        openLabel: 'Upload to Pramana',
        filters: {
            Documents: [
                'pdf', 'docx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp',
                'bmp', 'tif', 'tiff', 'ppt', 'pptx', 'xls', 'xlsx'
            ]
        }
    });
    if (!selected?.length) return;
    if (selected.length > 5) throw new Error('Select at most 5 documents at a time.');
    const form = new FormData();
    for (const uri of selected) {
        const stat = await vscode.workspace.fs.stat(uri);
        if (stat.size > 2 * 1024 * 1024) {
            throw new Error(`${uri.fsPath} exceeds the 2 MB per-file limit.`);
        }
        const content = await vscode.workspace.fs.readFile(uri);
        form.append(
            'files',
            new Blob([new Uint8Array(content)]),
            uri.fsPath.split(/[\\/]/).pop() || 'document'
        );
    }
    const started = await fetch(`${baseUrl}/api/uploads`, {
        method: 'POST',
        body: form
    });
    const job = await started.json() as { job_id?: string; error?: string };
    if (!started.ok || !job.job_id) {
        throw new Error(job.error || 'Upload could not start.');
    }
    let status = 'queued';
    let result: { imported?: unknown[]; errors?: Array<{ filename: string; error: string }> } = {};
    while (status === 'queued' || status === 'processing') {
        await new Promise(resolvePromise => setTimeout(resolvePromise, 600));
        const response = await fetch(
            `${baseUrl}/api/uploads/${encodeURIComponent(job.job_id)}`
        );
        const progress = await response.json() as {
            status?: string;
            error?: string;
            result?: typeof result;
        };
        if (!response.ok) throw new Error(progress.error || 'Could not check upload status.');
        status = progress.status || 'failed';
        result = progress.result || {};
        panel.webview.postMessage({
            type: 'upload-status',
            text: `Indexing documents: ${status}...`
        });
        if (status === 'failed') throw new Error(progress.error || 'Document indexing failed.');
    }
    const failures = (result.errors || [])
        .map(item => `${item.filename}: ${item.error}`)
        .join('; ');
    panel.webview.postMessage({
        type: 'upload-status',
        text: `${result.imported?.length || 0} document(s) indexed.${failures ? ` Errors: ${failures}` : ''}`
    });
}

async function configureProviders(
    context: vscode.ExtensionContext,
    runtime: PramanaRuntime
): Promise<void> {
    type ConfigureOption =
        | { label: string; type: 'secret'; key: string }
        | { label: string; type: 'setting'; setting: string };
    const options: ConfigureOption[] = [
        { label: 'Set Gemini API key', type: 'secret', key: SECRET_GEMINI },
        { label: 'Set OpenAI API key', type: 'secret', key: SECRET_OPENAI },
        { label: 'Set default provider', type: 'setting', setting: 'defaultProvider' },
        { label: 'Set Gemini model', type: 'setting', setting: 'geminiModel' },
        { label: 'Set OpenAI model', type: 'setting', setting: 'openaiModel' },
        { label: 'Set Ollama model', type: 'setting', setting: 'ollamaModel' },
        { label: 'Set embedding model', type: 'setting', setting: 'embeddingModel' }
    ];
    const action = await vscode.window.showQuickPick<ConfigureOption>(
        options,
        { placeHolder: 'Choose a Pramana setting' }
    );
    if (!action) return;
    if (action.type === 'secret') {
        const key = await vscode.window.showInputBox({
            prompt: action.label,
            password: true,
            ignoreFocusOut: true,
            placeHolder: 'API key is stored in VS Code SecretStorage'
        });
        if (key === undefined) return;
        if (key.trim()) await context.secrets.store(action.key, key.trim());
        else await context.secrets.delete(action.key);
        runtime.stop();
        vscode.window.showInformationMessage(
            `${action.label} saved securely. Restart Pramana to apply it.`
        );
        return;
    }
    const defaults: Record<string, string> = {
        defaultProvider: 'ollama',
        geminiModel: 'gemini-2.5-flash',
        openaiModel: 'gpt-4.1-mini',
        ollamaModel: 'qwen2.5:1.5b',
        embeddingModel: 'all-minilm'
    };
    const value = await vscode.window.showInputBox({
        prompt: action.label,
        value: vscode.workspace
            .getConfiguration('pramana')
            .get<string>(action.setting, defaults[action.setting]),
        ignoreFocusOut: true
    });
    if (value === undefined || !value.trim()) return;
    await vscode.workspace
        .getConfiguration('pramana')
        .update(action.setting, value.trim(), vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(
        `${action.label} saved. Restart Pramana to apply it.`
    );
    runtime.stop();
}

export function activate(context: vscode.ExtensionContext): void {
    const runtime = new PramanaRuntime(context);
    activeRuntime = runtime;
    context.subscriptions.push(
        vscode.commands.registerCommand('pramana.configure', async () => {
            await configureProviders(context, runtime);
        }),
        vscode.commands.registerCommand('pramana.stopServer', () => {
            runtime.stop();
            vscode.window.showInformationMessage('Pramana local server stopped.');
        }),
        vscode.commands.registerCommand('pramana.openChat', async () => {
            try {
                const baseUrl = await runtime.start();
                const panel = vscode.window.createWebviewPanel(
                    'pramana.chat',
                    'Pramana Chat',
                    vscode.ViewColumn.One,
                    { enableScripts: true, retainContextWhenHidden: true }
                );
                const nonce = Buffer.from(
                    `${Date.now()}-${Math.random()}`
                ).toString('base64');
                panel.webview.html = chatHtml(nonce);
                context.subscriptions.push(panel.webview.onDidReceiveMessage(async message => {
                    if (message?.type === 'configure') {
                        await configureProviders(context, runtime);
                        panel.webview.postMessage({
                            type: 'upload-status',
                            text: 'Configuration saved. Run Pramana: Open Chat again to restart with the new settings.'
                        });
                    } else if (message?.type === 'api') {
                        try {
                            const result = await apiRequest(
                                baseUrl,
                                String(message.path),
                                message.options as RequestInit
                            );
                            panel.webview.postMessage({
                                type: 'api-response',
                                id: String(message.id),
                                ...result
                            });
                        } catch (error) {
                            panel.webview.postMessage({
                                type: 'api-response',
                                id: String(message.id),
                                ok: false,
                                data: {
                                    error: error instanceof Error
                                        ? error.message
                                        : String(error)
                                }
                            });
                        }
                    } else if (message?.type === 'upload') {
                        try {
                            await uploadDocuments(panel, baseUrl);
                        } catch (error) {
                            panel.webview.postMessage({
                                type: 'upload-status',
                                text: error instanceof Error
                                    ? error.message
                                    : String(error)
                            });
                        }
                    }
                }));
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                vscode.window.showErrorMessage(`Pramana could not start: ${message}`);
            }
        })
    );
}

let activeRuntime: PramanaRuntime | undefined;

export function deactivate(): void {
    activeRuntime?.stop();
}
