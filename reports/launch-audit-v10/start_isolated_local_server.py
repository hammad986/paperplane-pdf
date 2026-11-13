import os
import sys
from pathlib import Path

SENSITIVE_ENV_MARKERS = (
    'SECRET', 'KEY', 'TOKEN', 'PASSWORD', 'CASHFREE', 'SMTP', 'EMAIL',
    'OPENAI', 'ANTHROPIC', 'GOOGLE', 'GEMINI', 'DEEPSEEK', 'OPENROUTER', 'BLUESMINDS'
)
for name in list(os.environ):
    if any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS):
        os.environ.pop(name, None)

os.environ.update({
    'PAPERPLANE_SKIP_DOTENV': '1',
    'PAPERPLANE_ENV': 'development',
    'CASHFREE_ENV': 'TEST',
    'AI_PROVIDER': '',
    'PAPERPLANE_DATA_DIR': sys.argv[1],
})
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn

uvicorn.run('server:app', host='127.0.0.1', port=8501, workers=1, log_level='warning')
