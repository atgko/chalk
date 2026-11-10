"""The web pages Chalk links to, read from one file instead of the code,
so they can be kept current after the handover (sponsor, Nov 9).

`resources/links.json` lists every link with what it's for. An instructor
can change one for their own computer under Settings → More settings;
those changes are saved in "Chalk links.json" in their courses folder
(chalk.locations), which survives installing a new version of Chalk, and
win over the bundled file.

Looked up by key, e.g. `url_for("class_schedule")`. A key missing from
both files is a programming error and raises KeyError.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from chalk.errors import ChalkError
from chalk.locations import APP_ROOT, default_projects_dir

LINKS_FILE = APP_ROOT / "resources" / "links.json"
OVERRIDES_FILE_NAME = "Chalk links.json"


@dataclass(frozen=True)
class Link:
    key: str
    label: str
    url: str
    used_for: str
    is_changed: bool = False  # set on this computer, not the bundled default


def overrides_path() -> Path:
    return default_projects_dir() / OVERRIDES_FILE_NAME


def load_links(defaults: Path | None = None, overrides: Path | None = None) -> list[Link]:
    """Every link, in the bundled file's order, with this computer's changes."""
    defaults = defaults or LINKS_FILE
    changed = _read_overrides(overrides or overrides_path())
    links = []
    for entry in json.loads(defaults.read_text(encoding="utf-8"))["links"]:
        url = changed.get(entry["key"], entry["url"])
        links.append(Link(entry["key"], entry["label"], url, entry["used_for"], url != entry["url"]))
    return links


def bundled_urls(defaults: Path | None = None) -> dict[str, str]:
    """Each link's address as Chalk ships it, before this computer's changes."""
    entries = json.loads((defaults or LINKS_FILE).read_text(encoding="utf-8"))["links"]
    return {entry["key"]: entry["url"] for entry in entries}


def url_for(key: str, *, defaults: Path | None = None, overrides: Path | None = None) -> str:
    for link in load_links(defaults, overrides):
        if link.key == key:
            return link.url
    raise KeyError(key)


def check_url(text: str) -> str:
    """`text` as a web address, or ChalkError saying what's wrong with it."""
    url = text.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ChalkError(f"“{url or '(blank)'}” isn't a web address. It should start with https://")
    return url


def save_links(urls: dict[str, str], *, defaults: Path | None = None, overrides: Path | None = None) -> list[str]:
    """Save `urls` (key -> address) for this computer, keeping only the
    ones that differ from the bundled file, so a later fix to a bundled
    link still reaches links left as they were. Checks every address
    first and saves nothing if one is wrong. Returns the keys now changed."""
    defaults = defaults or LINKS_FILE
    overrides = overrides or overrides_path()
    bundled = bundled_urls(defaults)
    checked = {key: check_url(url) for key, url in urls.items() if key in bundled}
    changed = {key: url for key, url in checked.items() if url != bundled[key]}
    if not changed:
        overrides.unlink(missing_ok=True)
        return []
    overrides.parent.mkdir(parents=True, exist_ok=True)
    overrides.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
    return sorted(changed)


def _read_overrides(path: Path) -> dict[str, str]:
    """This computer's changed links; a missing or damaged file means none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: url for key, url in data.items() if isinstance(key, str) and isinstance(url, str)}
