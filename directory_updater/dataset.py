"""Import a completed read-only Devvit metadata run from its JSON logs."""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re


PREFIXES = {
    "SUBREDDIT_REFRESH_START ": "start",
    "SUBREDDIT_METADATA ": "metadata",
    "SUBREDDIT_METADATA_ERROR ": "error",
    "SUBREDDIT_REFRESH_DONE ": "done",
}


def parse_timestamp(value):
    """Normalize the timestamp formats returned by the Reddit platform."""
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value.replace("Z", "+00:00"))
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def read_csv(csv_path):
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "name" not in fields or len(fields) != len(set(fields)):
        raise ValueError("CSV needs a name column and unique column headers.")
    if not rows:
        raise ValueError("The community list is empty.")
    names = set()
    for row in rows:
        name = row.get("name", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{2,21}", name or ""):
            raise ValueError(f"Invalid subreddit name: {name!r}.")
        if name.lower() in names:
            raise ValueError(f"CSV contains duplicate community names: {name}.")
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Malformed CSV row for {name}; keep the same number of columns.")
        names.add(name.lower())
    for field in ("subs", "description", "created_utc", "updated_utc"):
        if field not in fields:
            fields.append(field)
            for row in rows:
                row[field] = ""
    return fields, rows


def read_run(log_path):
    events = []
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        try:
            envelope = json.loads(line)
        except ValueError:
            continue  # CLI notices are not application records.
        if not isinstance(envelope, dict):
            continue
        message = envelope.get("message", "")
        if not isinstance(message, str):
            continue
        for prefix, kind in PREFIXES.items():
            if message.startswith(prefix):
                events.append((kind, json.loads(message[len(prefix):])))
                break
    starts = [event for kind, event in events if kind == "start"]
    if not starts:
        raise ValueError("No metadata run found in the JSON log.")
    start = starts[-1]
    run = start["run"]
    records, errors, done = {}, {}, None
    for kind, event in events:
        if event.get("run") != run:
            continue
        if kind == "metadata":
            key = event["name"].lower()
            records[key] = event
            errors.pop(key, None)
        elif kind == "error":
            key = event["name"].lower()
            errors[key] = event
            records.pop(key, None)
        elif kind == "done":
            done = event
    if done is None or done["total"] != start["total"]:
        raise ValueError(f"Run is incomplete: {len(records) + len(errors)}/{start['total']} processed.")
    if len(records) + len(errors) != start["total"]:
        raise ValueError("Missing log records; capture the complete run before importing.")
    return run, records, errors


def updated_dataset(log_path, csv_path):
    run, records, errors = read_run(log_path)
    fields, rows = read_csv(csv_path)
    names = {row["name"].lower() for row in rows}
    if len(names) != len(rows):
        raise ValueError("CSV contains duplicate community names.")
    if names != set(records) | set(errors):
        raise ValueError("Run and CSV contain different community lists; refresh the current list first.")
    if not records:
        raise ValueError("Reddit returned no usable metadata; existing files were preserved.")
    descriptions = 0
    for row in rows:
        record = records.get(row["name"].lower())
        if record is None:
            continue
        count = record.get("subs")
        if type(count) is not int or count < 0:
            raise ValueError(f"Invalid subscriber count for {row['name']}; CSV not written.")
        description = record.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError(f"Invalid description for {row['name']}; CSV not written.")
        parse_timestamp(record["updated_utc"])
        row["subs"] = str(count)
        row["updated_utc"] = record["updated_utc"]
        if description is not None:
            row["description"] = description
            descriptions += 1
        # Preserve existing creation dates; complete missing dates when returned.
        if not row.get("created_utc") and record.get("created_utc"):
            created = parse_timestamp(record["created_utc"])
            row["created_utc"] = created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return fields, rows, {
        "run": run, "subscribers_updated": len(records),
        "descriptions_updated": descriptions,
        "descriptions_preserved": len(records) - descriptions,
        "failed_preserved": {event["name"]: event["error"] for event in errors.values()},
    }
