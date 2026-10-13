"""Atomically save prepared runtime files with bounded lock retries."""
import os
import time

def save(path, text):
    pending = path.with_name(path.name + '.pending')
    for attempt in range(4):
        try:
            pending.write_text(text, encoding='utf-8')
            os.replace(pending, path)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.25 * (attempt + 1))
