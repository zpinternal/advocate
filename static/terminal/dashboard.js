const term = new Terminal({
  convertEol: true,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  cursorBlink: true,
  theme: { background: '#0b1324', foreground: '#e2e8f0' },
});
const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);
term.open(document.getElementById('terminalView'));
fitAddon.fit();
window.addEventListener('resize', () => fitAddon.fit());

const input = document.getElementById('commandInput');
const cwdInput = document.getElementById('cwdInput');
const timeoutInput = document.getElementById('timeoutInput');

function writeLine(text = '') {
  term.writeln(text);
}

function block(text) {
  return String(text || '').split('\n').forEach((line) => writeLine(line));
}

async function runCommand() {
  const command = input.value.trim();
  if (!command) {
    return;
  }
  const cwd = cwdInput.value.trim() || '.';
  const timeout = Number(timeoutInput.value || '20');
  writeLine(`$ ${command}`);

  const response = await fetch('/terminal/exec', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, cwd, timeout_seconds: timeout }),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) {
    block(`[error] ${body.error?.message || 'Request failed'}`);
    writeLine('');
    return;
  }

  const data = body.data;
  if (data.stdout) {
    block(data.stdout);
  }
  if (data.stderr) {
    block(`[stderr]\n${data.stderr}`);
  }
  writeLine(`[exit ${data.exit_code}] cwd=${data.cwd}`);
  writeLine('');
}

document.getElementById('runBtn').addEventListener('click', runCommand);
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    runCommand().catch((error) => writeLine(`[error] ${error}`));
  }
});
document.getElementById('clearBtn').addEventListener('click', () => term.clear());

writeLine('Advocate Terminal (xterm.js)');
writeLine('Type a command and press Enter.');
writeLine('');
