"""
The summary of the journal of the API requests (#395), for `python manage.py api_log`:
by source, by origin (page, request of the queue, command), and the slowest requests.
"""

import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

NUMBER = re.compile(r"/\d+(?=/|$)")


@dataclass
class Stats:
    requests: int = 0
    cached: int = 0
    unknown: int = 0  # 404: the source does not know the subject
    errors: int = 0  # network error, refusal, server error, rate limit
    durations: list = field(default_factory=list)  # of the requests sent, in ms

    def add(self, entry):
        self.requests += 1
        if entry.get("cache"):
            self.cached += 1
            return
        self.durations.append(entry.get("ms") or 0)
        status = entry.get("status")
        if status == 404:
            self.unknown += 1
        elif status != 200:
            self.errors += 1

    @property
    def sent(self):
        return self.requests - self.cached

    def median(self):
        return round(statistics.median(self.durations)) if self.durations else 0

    def p95(self):
        if len(self.durations) < 2:
            return self.median()
        return round(statistics.quantiles(self.durations, n=20)[-1])

    def seconds(self):
        return round(sum(self.durations) / 1000, 1)


def entries(paths, since=None):
    """The entries of the journal files, oldest first, from since if given."""
    found = []
    for path in paths:
        if not Path(path).exists():
            continue
        with open(path, encoding="utf-8") as lines:
            for line in lines:
                entry = parse(line)
                if entry and (since is None or entry["at"] >= since):
                    found.append(entry)
    return sorted(found, key=lambda entry: entry["at"])


def parse(line):
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or "at" not in entry:
        return None
    entry["at"] = datetime.fromisoformat(entry["at"])
    return entry


def journal_files(path):
    """The journal and its rotated files (api.log.1 … api.log.5), oldest first."""
    path = Path(path)
    rotated = sorted(path.parent.glob(f"{path.name}.*"), key=rotation_number, reverse=True)
    return [*rotated, path]


def rotation_number(path):
    suffix = path.suffix.lstrip(".")
    return int(suffix) if suffix.isdigit() else 0


def origin(entry):
    """What made the request, without the numbers: « page POST /publications/<n>/refresh/ »."""
    via, label = entry.get("via", "?"), entry.get("label", "")
    if via == "file":
        label = label.split(" ", 1)[0]  # the action, without the identifier
    elif via == "page":
        label = NUMBER.sub("/<n>", label)
    return f"{via} {label}".strip()


@dataclass
class QueueStats:
    """The requests of the queue done for one action: « event »: « file » lines."""

    requests: int = 0
    failed: int = 0
    durations: list = field(default_factory=list)
    waits: list = field(default_factory=list)
    api_requests: int = 0

    def add(self, entry):
        self.requests += 1
        if entry.get("status") == "failed":
            self.failed += 1
        self.durations.append(entry.get("ms") or 0)
        if entry.get("wait_ms") is not None:
            self.waits.append(entry["wait_ms"])
        # A batch (#381) gives its requests on each of its lines: shared out.
        self.api_requests += (entry.get("api_requests") or 0) / (entry.get("batch") or 1)

    def median(self):
        return round(statistics.median(self.durations)) if self.durations else 0

    def median_wait(self):
        return round(statistics.median(self.waits)) if self.waits else 0

    def per_request(self):
        return round(self.api_requests / self.requests, 1) if self.requests else 0


def is_api(entry):
    """A request to an API; the lines written before the queue lines have no event."""
    return entry.get("event", "api") == "api"


def summarize(found):
    by_service, by_origin, by_action = (
        defaultdict(Stats),
        defaultdict(Stats),
        defaultdict(QueueStats),
    )
    for entry in found:
        if is_api(entry):
            by_service[entry.get("service", "?")].add(entry)
            by_origin[origin(entry)].add(entry)
        elif entry.get("event") == "file":
            by_action[entry.get("action", "?")].add(entry)
    slowest = sorted(
        (entry for entry in found if is_api(entry) and not entry.get("cache")),
        key=lambda entry: entry.get("ms") or 0,
        reverse=True,
    )
    return {
        "by_service": by_service,
        "by_origin": by_origin,
        "by_action": by_action,
        "slowest": slowest,
    }
