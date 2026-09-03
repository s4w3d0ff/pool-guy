import re
import sys
import pathlib
from urllib.request import urlopen, Request

DOCS_URL = "https://dev.twitch.tw/docs/eventsub/eventsub-subscription-types/"
TARGET_FILE = pathlib.Path(__file__).resolve().parent.parent / "poolguy" / "twitchapi.py"


def fetch_docs(url):
    request = Request(url, headers={"User-Agent": "pool-guy dev tool"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def version_rank(version):
    if version.isdigit():
        return int(version)
    return 0


def parse_versions(html):
    h1_pattern = r'<h1 id="subscription-types">Subscription Types</h1>'
    tbody_pattern = r'<tbody>(.*?)</tbody>'
    match = re.search(f'{h1_pattern}.*?{tbody_pattern}', html, re.S)
    if not match:
        raise ValueError("Could not locate the <tbody> section under Subscription Types.")
    rows = re.findall(r'<tr>(.*?)</tr>', match.group(1), re.S)
    latest = {}
    for row in rows:
        codes = [c.strip() for c in re.findall(r'<code[^>]*>(.*?)</code>', row, re.S)]
        if len(codes) < 2:
            continue
        name, version = codes[0], codes[1]
        if "." not in name or not re.fullmatch(r'[a-z0-9]+', version):
            continue
        current = latest.get(name)
        if current is None or version_rank(version) > version_rank(current):
            latest[name] = version
    if not latest:
        raise ValueError("No valid subscription types found in page.")
    return latest


def render_map(versions):
    lines = ["EVENTSUB_VERSIONS = {"]
    for name in sorted(versions):
        lines.append(f'    "{name}": "{versions[name]}",')
    lines.append("}")
    return "\n".join(lines)


def update_target_file(map_text, dry_run=False):
    original = TARGET_FILE.read_text()
    new_text, count = re.subn(
        r"EVENTSUB_VERSIONS = \{.*?\n\}",
        map_text.replace("\\", r"\\"),
        original,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("Could not locate EVENTSUB_VERSIONS block in twitchapi.py.")
    if new_text == original:
        print(f"No changes needed. {TARGET_FILE} is up to date.")
        return False
    if dry_run:
        print(new_text)
        return True
    TARGET_FILE.write_text(new_text)
    print(f"Updated {TARGET_FILE}")
    return True


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    html = fetch_docs(DOCS_URL)
    versions = parse_versions(html)
    print(f"Parsed {len(versions)} event types from docs.")
    update_target_file(render_map(versions), dry_run=dry_run)


if __name__ == "__main__":
    main()
