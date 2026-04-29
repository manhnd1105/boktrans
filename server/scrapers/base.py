import html as html_module
import re
import time
from pathlib import Path

import requests

REQUEST_DELAY = 1.0
USER_AGENT = "Mozilla/5.0"


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def html_clean(text: str) -> str:
    return html_module.unescape(re.sub(r'<[^>]+>', '', text)).strip()


def write_chapter(num: int, title: str, body: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"ch_{num:03d}.md"
    out.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    return out


def polite_get(session: requests.Session, url: str, timeout: int = 20) -> requests.Response:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp
