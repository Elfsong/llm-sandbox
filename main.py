# code: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-01-20

import sys
sys.path.append('/home/nus_cisco_wp1/Projects/llm-sandbox')

import threading
from typing import Union
from fastapi import FastAPI
from llm_sandbox import SandboxSession

app = FastAPI()

def run_with_timeout(func, timeout, *args, **kwargs):
    """Runs a function with a timeout."""
    result = {'output': None, 'error': None}

    def target():
        try:
            result['output'] = func(*args, **kwargs)
        except Exception as e:
            result['error'] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        thread.join(0)  # Clean up the thread
        result["error"] = 'Timeout Reached.'
    return result

@app.get("/run")
def execute(lang: str, code: str, libs: Union[str, None] = None):
    with SandboxSession(lang=lang, verbose=True) as session:
        session.setup(libraries=libs)
        response = run_with_timeout(session.run, 60, code=code, run_memory_profile=True)
    if response['output']['stderr']:
        response['error'] = "failed"
    return {"lang": lang, "code": code, "libs": libs, "status": response}