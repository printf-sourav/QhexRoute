import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const localPython = resolve('.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const candidates = [process.env.QHEXROUTE_PYTHON, existsSync(localPython) ? localPython : null,
  ...(process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'])].filter(Boolean);
const args = process.argv.slice(2);

function run(index) {
  if (index >= candidates.length) {
    console.error('Python 3 was not found. Install Python 3.11+ and retry.');
    process.exit(1);
  }
  const child = spawn(candidates[index], args, { stdio: 'inherit', shell: false });
  child.on('error', (error) => {
    if (error.code === 'ENOENT') run(index + 1);
    else {
      console.error(error);
      process.exit(1);
    }
  });
  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else if (code !== 0) process.exit(code ?? 1);
  });
}

run(0);
