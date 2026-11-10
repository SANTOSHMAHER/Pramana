const fs = require('node:fs');
const path = require('node:path');

const extensionDir = path.resolve(__dirname, '..');
const projectDir = path.resolve(extensionDir, '..');
const backendDir = path.join(extensionDir, 'backend');
const files = [
    'app.py',
    'config.py',
    'documents.py',
    'providers.py',
    'rag.py',
    'upload_jobs.py',
    'vector_store.py',
    'requirements.txt'
];

fs.mkdirSync(backendDir, { recursive: true });
for (const file of files) {
    fs.copyFileSync(path.join(projectDir, file), path.join(backendDir, file));
}
for (const directory of ['database', 'templates']) {
    fs.cpSync(
        path.join(projectDir, directory),
        path.join(backendDir, directory),
        { recursive: true, force: true }
    );
}
console.log(`Bundled Pramana backend source into ${backendDir}`);
