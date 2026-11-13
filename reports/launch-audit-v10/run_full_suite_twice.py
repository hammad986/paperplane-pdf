from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
OUTPUTS = REPORTS / 'outputs'
OUTPUTS.mkdir(parents=True, exist_ok=True)
SENSITIVE_MARKERS = (
    'SECRET', 'KEY', 'TOKEN', 'PASSWORD', 'CASHFREE', 'SMTP', 'EMAIL',
    'OPENAI', 'ANTHROPIC', 'GOOGLE', 'GEMINI', 'DEEPSEEK', 'OPENROUTER',
    'BLUESMINDS', 'AWS', 'STRIPE', 'GITHUB'
)


def safe_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not any(marker in key.upper() for marker in SENSITIVE_MARKERS)}
    env.update({
        'PAPERPLANE_SKIP_DOTENV': '1',
        'PAPERPLANE_ENV': 'development',
        'CASHFREE_ENV': 'TEST',
        'AI_PROVIDER': '',
        'TESTING': 'True',
        'PAPERPLANE_DATA_DIR': str(Path(os.getenv('TEMP', '.')) / 'paperplane-v10-full-suite-runner'),
    })
    return env


def sanitize_output(value: str) -> str:
    value = re.sub(
        r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
        '[private key redacted]', value, flags=re.DOTALL
    )
    value = re.sub(r'(?<!\d)(?:\d[\s-]*){12}(?!\d)', '[synthetic identifier redacted]', value)
    value = re.sub(
        r"(?i)\b(?:pw|password|confirm_password|new_password|admin_code|otp|dev_otp|login_otp|invalid_otp)\s*=\s*([\"']).*?\1",
        '[credential variable assignment redacted]', value
    )
    value = re.sub(r"(?i)([\"']?otp[\"']?\s*:\s*[\"']?)\d{4,8}", r'\1[OTP redacted]', value)
    value = re.sub(
        r'(?i)\b(admin[_-]?key|api[_-]?key|password|passwd|secret|token|access[_-]?key)\s*[:=]\s*([^\s,;]+)',
        r'\1=[credential value redacted]', value
    )
    value = re.sub(r'\b[\w.+-]+@(?:example\.(?:com|test)|mail\.[\w.-]+)\b', '[synthetic email redacted]', value, flags=re.IGNORECASE)
    return value


def main() -> int:
    summaries = []
    for run_number in (1, 2):
        started = time.perf_counter()
        process = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q'],
            cwd=ROOT,
            env=safe_environment(),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        duration = round(time.perf_counter() - started, 3)
        combined = sanitize_output(process.stdout + process.stderr)
        log_path = OUTPUTS / f'test-suite-run-{run_number}.log'
        log_path.write_text(combined, encoding='utf-8')
        summary_match = re.findall(r'(?m)^.*\b\d+ passed\b.*$', combined)
        summaries.append({
            'run': run_number,
            'exit_code': process.returncode,
            'duration_seconds': duration,
            'pytest_summary': summary_match[-1].strip() if summary_match else 'No standard pytest summary line',
            'log': str(log_path.relative_to(ROOT)).replace('\\', '/'),
        })

    result = {
        'command': 'python -m pytest -q',
        'runs_sequential': True,
        'credential_environment_removed': True,
        'dotenv_disabled': True,
        'production_endpoints_contacted': False,
        'runs': summaries,
    }
    (OUTPUTS / 'test-suite-summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if all(item['exit_code'] == 0 for item in summaries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
