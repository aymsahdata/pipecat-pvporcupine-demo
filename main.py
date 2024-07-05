from concurrent.futures import ThreadPoolExecutor
from pipe import call_pipecat
from __init__ import asyncio, os
import subprocess

def run_http_server():
    command = ["bash", "-c", "cd server && python3 -m http.server"]
    subprocess.run(command)

if __name__ == "__main__":
    with ThreadPoolExecutor() as executor:
        executor.submit(run_http_server)
        asyncio.run(call_pipecat("PorcupineDemoId"))