#!/usr/bin/env python3
"""Validate Spotlight actions and emit records for the shell UI."""

import os
from pathlib import Path
import sys
if sys.version_info < (3, 11):
    sys.exit("Spotlight requires Python 3.11 or newer; upgrade python3 before launching it.")
import tomllib
import hashlib
import re
import tempfile


PLACEHOLDER = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")
CACHE_VERSION = 2


def parse_cheat(text, source_name):
    """Adapt the basic Navi syntax; reject constructs we cannot preserve."""
    actions = []
    tags, variables = [], {}
    title = None
    pending = False
    namespace = hashlib.sha256(str(Path(source_name).resolve()).encode()).hexdigest()[:16]

    def fail(number, message):
        raise ValueError(f"{source_name}:{number}: {message}")

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith(("%", "#", "$")) and pending:
            fail(number, "description has no command")
        if line.startswith("%"):
            tags = [tag.strip() for tag in line[1:].split(",") if tag.strip()]
            if not tags:
                fail(number, "empty Navi tags")
            variables = {}
            title = None
        elif line.startswith("#"):
            title = line[1:].strip()
            if not title:
                fail(number, "empty Navi description")
            pending = True
        elif line.startswith("$"):
            match = re.fullmatch(r"\$\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.+)", line)
            if not match or "---" in line:
                fail(number, "unsupported Navi variable definition or picker options")
            name, command = match.groups()
            if name in variables:
                fail(number, f"duplicate Navi variable: {name}")
            variables[name] = {"source": command}
        else:
            if line.startswith(("@", "```")):
                fail(number, "Navi inheritance and Markdown snippets are not supported")
            if not tags or not pending:
                fail(number, "expected tags and description; multiline commands are not supported")
            if line.endswith("\\"):
                fail(number, "multiline commands are not supported")
            for placeholder in re.finditer(r"<([^<>\s]+)>", line):
                if not PLACEHOLDER.fullmatch(placeholder.group()):
                    fail(number, "unsupported Navi placeholder name")
            # ponytail: basic imports only; shell-aware quoted substitution needs
            # a separate resolver before quoted/escaped placeholders can work.
            quote, escaped = None, False
            for index, char in enumerate(line):
                if PLACEHOLDER.match(line, index) and (quote or escaped):
                    fail(number, "quoted or escaped Navi placeholders are not supported")
                if escaped:
                    escaped = False
                elif char == "\\" and quote != "'":
                    escaped = True
                elif char == quote:
                    quote = None
                elif quote is None and char in "\"'`":
                    quote = char
            identity = hashlib.sha256(repr((tags, title, line)).encode()).hexdigest()[:16]
            actions.append({"id": f"navi.{namespace}.{identity}", "title": title,
                            "category": tags[0], "keywords": list(tags), "command": line,
                            "parameters": {}, "_variables": variables, "_line": number})
            pending = False
    if pending:
        fail(len(text.splitlines()), "description has no command")
    for action in actions:
        variables = action.pop("_variables")
        number = action.pop("_line")
        for variable in variables.values():
            command = variable["source"]
            if PLACEHOLDER.search(command) or any(
                    re.search(r"\$(?:" + re.escape(name) + r"\b|\{" + re.escape(name) + r"\})", command)
                    for name in variables):
                fail(number, "dependent Navi variables are not supported")
        action["parameters"] = {name: dict(variables.get(name, {}))
                                for name in dict.fromkeys(PLACEHOLDER.findall(action["command"]))}
    return actions


def parse_actions(text, source_name):
    if str(source_name).endswith(".cheat"):
        return parse_cheat(text, source_name)
    return tomllib.loads(text).get("actions", [])


def load_actions(path):
    return parse_actions(Path(path).read_text(encoding="utf-8"), path)


def config_actions_dir():
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "spotlight/actions"


def action_sources():
    sources = os.environ.get("SPOTLIGHT_ACTION_PATH")
    if sources is None:
        sources = f"{Path(__file__).resolve().parent.parent / 'actions'}:{config_actions_dir()}"
    extra = os.environ.get("SPOTLIGHT_EXTRA_ACTION_PATH", "")
    return sources + (":" + extra if extra else "")


def cache_path():
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    sources = ":".join(os.path.abspath(os.path.expanduser(source))
                       for source in action_sources().split(":") if source)
    key = hashlib.sha256(f"{CACHE_VERSION}:{sources}".encode()).hexdigest()[:16]
    return cache_home / "spotlight" / f"actions-{key}.tsv"


def cached_records(refresh=False):
    path = cache_path()
    if not refresh and path.is_file():
        return path.read_text(encoding="utf-8")
    content = "".join(record + "\n" for record in main())
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".actions-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return content


def records(actions, source_name, seen_ids):
    if not isinstance(actions, list):
        raise ValueError(f"{source_name}: actions must be a list")
    for number, action in enumerate(actions, 1):
        if not isinstance(action, dict):
            raise ValueError(f"{source_name}: action {number} must be a table")
        unknown = set(action) - {"id", "title", "description", "keywords", "category", "command", "mode", "context", "parameters"}
        if unknown:
            raise ValueError(f"{source_name}: action {number}: unknown fields: {', '.join(sorted(unknown))}")
        for key in ("id", "title", "category", "command"):
            if not isinstance(action.get(key), str) or not action[key].strip():
                raise ValueError(f"{source_name}: action {number} needs a nonempty {key}")
        action_id = action["id"]
        if action_id in seen_ids:
            raise ValueError(f"{source_name}: duplicate action id: {action_id}")
        seen_ids.add(action_id)
        if action.get("mode", "shell-insert") != "shell-insert":
            raise ValueError(f"{source_name}: {action_id}: unsupported mode")
        description = action.get("description", action["title"])
        keywords = action.get("keywords", [])
        context = action.get("context", {})
        if not isinstance(description, str) or not isinstance(keywords, list) or not all(isinstance(word, str) for word in keywords):
            raise ValueError(f"{source_name}: {action_id}: invalid description or keywords")
        if not isinstance(context, dict) or any(key not in ("requires_git_repo", "requires_tmux") for key in context):
            raise ValueError(f"{source_name}: {action_id}: invalid context")
        if any(not isinstance(value, bool) for value in context.values()):
            raise ValueError(f"{source_name}: {action_id}: context values must be booleans")
        parameters = action.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError(f"{source_name}: {action_id}: parameters must be a table")
        placeholders = set(PLACEHOLDER.findall(action["command"]))
        if placeholders != set(parameters):
            raise ValueError(f"{source_name}: {action_id}: parameters must match command placeholders")
        for name, parameter in parameters.items():
            if not isinstance(parameter, dict) or set(parameter) - {"source", "prompt"}:
                raise ValueError(f"{source_name}: {action_id}: invalid parameter {name}")
            if any(not isinstance(value, str) or not value.strip() for value in parameter.values()):
                raise ValueError(f"{source_name}: {action_id}: parameter {name} needs nonempty text values")
        fields = (action["title"], action["category"], description, action["command"],
                  "tmux" if context.get("requires_tmux", False) else "all",
                  " ".join(keywords) or "-", str(source_name),
                  "1" if context.get("requires_git_repo", False) else "0", action_id)
        if any("\t" in field or "\n" in field or "\r" in field for field in fields):
            raise ValueError(f"{source_name}: {action_id}: tabs and line breaks are not supported")
        yield "\t".join(fields)


def resolve(path, action_id, expected_command, cwd, reused_command=None):
    actions = load_actions(path)
    list(records(actions, path, set()))
    action = next((action for action in actions if action["id"] == action_id), None)
    if action is None or action["command"] != expected_command:
        raise ValueError("Action changed since Spotlight loaded it; refresh Commands")
    if reused_command is not None:
        return reused_command
    import shlex
    import subprocess
    # Direct imports by tests need the sibling module on the search path too.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from spotlight_config import current_theme, ansi, fzf_colors, fzf_info, fzf_error

    command = action["command"]
    values = {}
    theme = current_theme()
    colors = theme['colors']
    info = os.environ.get('SPOTLIGHT_FZF_INFO') or fzf_info()
    for name in dict.fromkeys(PLACEHOLDER.findall(command)):
        parameter = action["parameters"][name]
        prompt = parameter.get("prompt", name)
        if "source" in parameter:
            try:
                result = subprocess.run(["sh", "-c", parameter["source"]], cwd=cwd,
                                        text=True, capture_output=True, timeout=30)
            except subprocess.TimeoutExpired as error:
                raise ValueError(f"{name} suggestions timed out after 30 seconds") from error
            if result.returncode:
                raise ValueError(f"{name} suggestions failed: {result.stderr.strip() or result.returncode}")
            if not result.stdout.strip():
                raise ValueError(f"No suggestions for {name}")
            rows = []
            for line in result.stdout.splitlines():
                value, separator, label = line.partition("\t")
                if value:
                    display = label.replace("\t", " ") if separator else value
                    rows.append(f"  {display}  {ansi(colors['hint'])}{value}\033[0m\t{value}")
            if not rows:
                raise ValueError(f"No suggestions for {name}")
            header = (f"  {ansi(colors['accent'], True)}{ansi(colors['tab_foreground'])}\033[1m {action['title']} \033[0m"
                      f"  {ansi(colors['muted'])}›  {prompt}\033[0m")
            preview = "printf '%s\\n\\n%s\\n\\n%s\\n' " + " ".join(
                shlex.quote(text) for text in (action["category"].upper(),
                                               action.get("description", action["title"]), command))
            choice = subprocess.run([
                "fzf", "--no-clear", "--ansi", "--delimiter=\t", "--with-nth=1", "--nth=1",
                "--layout=reverse", "--border=none", "--prompt=  Search ❯ ",
                "--pointer=▸", f"--info={info}", f"--header={header}",
                "--header-first", f"--preview={preview}",
                "--preview-window=right:40%:wrap:border-left",
                "--bind=ctrl-/:toggle-preview", f"--color={fzf_colors(theme)}",
            ], input="\n".join(rows) + "\n",
                                    text=True, capture_output=True)
            if choice.returncode in (1, 130):
                return None
            if choice.returncode:
                raise ValueError(fzf_error(choice.stderr, info) or f"Parameter picker failed (exit {choice.returncode})")
            value = choice.stdout.rstrip("\n").rsplit("\t", 1)[-1]
        else:
            with open("/dev/tty", "r+") as terminal:
                terminal.write(f"{prompt}: ")
                terminal.flush()
                value = terminal.readline().rstrip("\n")
        if not value:
            return None
        values[name] = shlex.quote(value)
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], command)


def main():
    seen_ids = set()
    for source in action_sources().split(":"):
        if not source:
            continue
        root = Path(source).expanduser()
        paths = (sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in (".toml", ".cheat"))
                 if root.is_dir() else ([root] if root.suffix in (".toml", ".cheat") and root.is_file() else []))
        for path in paths:
            yield from records(load_actions(path), path, seen_ids)


def install(url):
    from urllib.parse import urlparse
    from urllib.request import urlopen

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Use an HTTPS URL to a TOML or Navi .cheat action file")
    if parsed.netloc == "github.com":
        parts = parsed.path.split("/")
        if len(parts) < 6 or parts[3] != "blob":
            raise ValueError("Use a GitHub file URL containing /blob/ or a raw HTTPS URL")
        url = "https://raw.githubusercontent.com/" + "/".join(parts[1:3] + parts[4:])
        parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix not in (".toml", ".cheat"):
        raise ValueError("Action URL must end in .toml or .cheat")
    stem = Path(parsed.path).stem or "actions"
    stem = (re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-") or "actions")[:80]
    target = config_actions_dir() / f"{stem}-{hashlib.sha256(url.encode()).hexdigest()[:8]}{suffix}"
    with urlopen(url, timeout=15) as response:
        if urlparse(response.geturl()).scheme != "https":
            raise ValueError("The download redirected away from HTTPS")
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Action file exceeds 1 MiB")
    imported = parse_actions(data.decode("utf-8"), target)
    existing_ids = {record.rsplit("\t", 1)[-1] for record in main()}
    new_records = list(records(imported, target, existing_ids))
    if not new_records:
        raise ValueError("Action file has no actions")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(data)
    # Active modules change source keys; installation affects every variant.
    for path in cache_path().parent.glob("actions-*.tsv"):
        path.unlink(missing_ok=True)
    print(f"Installed {len(new_records)} actions: {target}")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "install":
            if len(sys.argv) == 3:
                url = sys.argv[2]
            elif len(sys.argv) == 2:
                with open("/dev/tty") as terminal:
                    print("Action file HTTPS URL: ", end="", file=sys.stderr, flush=True)
                    url = terminal.readline().strip()
            else:
                raise ValueError("Usage: actions.py install [HTTPS_URL]")
            install(url)
        elif len(sys.argv) == 6 and sys.argv[1] == "resolve":
            command = resolve(*sys.argv[2:])
            if command is None:
                sys.exit(130)
            print(command, end="")
        elif len(sys.argv) == 7 and sys.argv[1] == "reuse":
            print(resolve(*sys.argv[2:]), end="")
        elif sys.argv[1:] in (["cache"], ["cache", "--refresh"]):
            print(cached_records(refresh=len(sys.argv) == 3), end="")
        elif len(sys.argv) == 1:
            for record in main():
                print(record)
        else:
            raise ValueError("Usage: actions.py [cache [--refresh] | install [HTTPS_URL] | resolve PATH ID COMMAND CWD | reuse PATH ID COMMAND CWD RESOLVED]")
    except (OSError, ValueError, UnicodeError, tomllib.TOMLDecodeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
