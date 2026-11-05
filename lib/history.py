#!/usr/bin/env python3
"""Private, bounded MRU storage for opaque, encoded launcher records."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sys
import tempfile

MAX_HISTORY = 100


def history_path(*, inherited=True):
    if inherited and os.environ.get("SPOTLIGHT_HISTORY_FILE"):
        return Path(os.environ["SPOTLIGHT_HISTORY_FILE"])
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "spotlight/history-v1.tsv"


def history_limit(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("history limit must be an integer from 0 to 100")
    text = str(value)
    if not text or not text.isascii() or not text.isdecimal() or not 0 <= int(text) <= MAX_HISTORY:
        raise ValueError("history limit must be an integer from 0 to 100")
    return int(text)


def valid_record(record):
    fields = record.split("\t")
    return (len(fields) == 4 and all(field.startswith("v:") for field in fields)
            and (fields[0].startswith(("v:snippet:", "v:module:")) or fields[0] == "v:install-actions")
            and all(ord(char) >= 32 and ord(char) != 127 and not 0xD800 <= ord(char) <= 0xDFFF
                    for field in fields for char in field))


@contextmanager
def transaction(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600), "a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def record_history(record, limit):
    limit = history_limit(limit)
    if not valid_record(record):
        raise ValueError("expected one encoded history record with four v:-prefixed fields")
    if not limit:
        return
    path = history_path()
    with transaction(path):
        previous = path.read_text(errors="surrogateescape").split("\n") if path.exists() else []
        rows = list(dict.fromkeys([record] + [row for row in previous if valid_record(row)]))[:limit]
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".history-", delete=False) as output:
                temporary = Path(output.name)
                output.write("\n".join(rows) + "\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def clear_history():
    path = history_path()
    if path.parent.exists():
        with transaction(path):
            path.unlink(missing_ok=True)


def main():
    try:
        if sys.argv[1:] == ["clear"]:
            clear_history()
        elif len(sys.argv) == 3 and sys.argv[1] == "record":
            record = sys.stdin.read()
            if record.endswith("\n"):
                record = record[:-1]
            record_history(record, sys.argv[2])
        else:
            raise ValueError("usage: history.py record LIMIT | clear")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"spotlight history: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
