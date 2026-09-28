#!/usr/bin/env python3
"""Local synthetic model service. No real inference, network, or device access.

Run --help or a subcommand's --help for the available operations.
Only files under this fixture's work/ directory are changed.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = b"SYNTHETIC-CENN-NOT-A-REAL-MODEL\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def metadata(raw):
    catalog = read_json(ROOT / "materials/service-catalog.json")
    result = catalog["models"].get(digest(raw))
    if result is None:
        raise ValueError("Unrecognized synthetic model identity")
    return copy.deepcopy(result)


def configure(raw, template=None, labels=None):
    result = copy.deepcopy(template or {})
    info = metadata(raw)
    result.update({key: info[key] for key in ("chip", "input", "output", "detector")})
    result["synthetic"] = True
    result["source_model_sha256"] = digest(raw)
    if labels is not None:
        result["labels"] = labels
    elif "labels" not in result:
        result["labels"] = [{"id": i, "name": f"class_{i}"}
                            for i in range(info["detector"]["class_count"])]
    return result


def compare_config(config, raw):
    info = metadata(raw)
    differences = []
    for key in ("chip", "input", "output", "detector"):
        if config.get(key) != info[key]:
            differences.append(key)
    if config.get("source_model_sha256") != digest(raw):
        differences.append("source_model_sha256")
    labels = config.get("labels", [])
    ids = [item.get("id") for item in labels]
    if sorted(ids) != list(range(info["detector"]["class_count"])):
        differences.append("labels.id")
    return differences


def inspect_entry(entry):
    config = read_json(entry / "config.json")
    binary = (entry / "model.nn").read_bytes()
    wrapped = binary.startswith(WRAPPER)
    return {"synthetic": True, "entry": str(entry), "config": config,
            "container": "synthetic-wrapper" if wrapped else "unrecognized",
            "stored_model_sha256": digest(binary),
            "payload_sha256": digest(binary[len(WRAPPER):]) if wrapped else None}


def load_entry(entry):
    binary = (entry / "model.nn").read_bytes()
    if not binary.startswith(WRAPPER):
        return {"synthetic": True, "ok": False, "stage": "container",
                "error": "model format is not supported", "bmrt_called": False,
                "actual_device_load": False}
    raw = binary[len(WRAPPER):]
    metadata(raw)
    differences = compare_config(read_json(entry / "config.json"), raw)
    return {"synthetic": True, "ok": not differences, "stage": "config" if differences else "loaded",
            "differences": differences, "bmrt_called": False, "actual_device_load": False,
            "note": "Synthetic validation only; no BMRT or detector executes"}


def entry_path(args, state):
    if getattr(args, "entry_dir", None):
        return args.entry_dir.resolve()
    model_id = args.id
    if not model_id or Path(model_id).name != model_id or model_id in (".", ".."):
        raise ValueError("Invalid entry ID")
    return state / "entries" / model_id


def save_entry(state, raw, config, action, source):
    entries = state / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    number = 1
    while (entries / f"model-{number:03d}").exists():
        number += 1
    model_id = f"model-{number:03d}"
    entry = entries / model_id
    entry.mkdir()
    (entry / "model.nn").write_bytes(WRAPPER + raw)
    write_json(entry / "config.json", config)
    write_json(entry / "identity.json", {"synthetic": True, "id": model_id, "operation": action,
                                       "source": str(source), "source_model_sha256": digest(raw)})
    return {"synthetic": True, "id": model_id, "saved": True, "operation": action,
            "source_model_sha256": digest(raw), "actual_device_load": False}


def execute(args, state):
    if args.command == "inspect-model":
        raw = args.model.read_bytes()
        return {"synthetic": True, "model_sha256": digest(raw), "metadata": metadata(raw)}
    if args.command == "add":
        raw = args.model.read_bytes()
        template = read_json(args.template) if args.template else None
        labels = read_json(args.labels) if args.labels else None
        return save_entry(state, raw, configure(raw, template, labels), "add", args.model)
    if args.command == "import":
        with zipfile.ZipFile(args.package) as package:
            manifest = json.loads(package.read("manifest.json"))
            if manifest.get("synthetic") is not True:
                raise ValueError("Only synthetic fixture packages are supported")
            binary = package.read("model.nn")
            if not binary.startswith(WRAPPER):
                raise ValueError("model format is not supported (container; BMRT not called)")
            raw = binary[len(WRAPPER):]
            config = json.loads(package.read("config.json"))
            metadata(raw)
            if manifest.get("source_model_sha256") != digest(raw):
                raise ValueError("Package manifest does not match synthetic payload")
        return save_entry(state, raw, config, "import", args.package)
    if args.command == "list":
        return {"synthetic": True, "entries": sorted(p.name for p in (state / "entries").glob("model-*"))}
    entry = entry_path(args, state)
    if args.command == "read":
        return inspect_entry(entry)
    if args.command == "load":
        return load_entry(entry)
    if args.command == "update":
        config = read_json(args.config)
        if not entry.is_dir():
            raise ValueError("Entry does not exist")
        write_json(entry / "config.json", config)
        return {"synthetic": True, "id": args.id, "saved": True}
    raise ValueError("Unsupported command")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state-dir", type=Path, default=ROOT / "work/service-state",
                        help="Writable local service state, restricted to this fixture's work/")
    commands = result.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-model", help="Read synthetic raw-model tensor metadata")
    inspect.add_argument("--model", required=True, type=Path)
    add = commands.add_parser("add", help="Add raw synthetic bmodel; derive tensor fields and wrap stored bytes")
    add.add_argument("--model", required=True, type=Path)
    add.add_argument("--template", type=Path, help="Optional initial configuration; tensor fields are derived")
    add.add_argument("--labels", type=Path, help="JSON list of {id, name}; otherwise retain template/default labels")
    importer = commands.add_parser("import", help="Import a complete synthetic package; retain its configuration")
    importer.add_argument("--package", required=True, type=Path)
    commands.add_parser("list", help="List entries saved in this local service state")
    for name in ("read", "load"):
        action = commands.add_parser(name, help="Read saved fields" if name == "read" else "Simulate container/config validation")
        identity = action.add_mutually_exclusive_group(required=True)
        identity.add_argument("--id", help="ID returned by add/import")
        identity.add_argument("--entry-dir", type=Path, help="Read an existing local entry directory")
    update = commands.add_parser("update", help="Save explicit configuration for an existing local entry")
    update.add_argument("--id", required=True)
    update.add_argument("--config", required=True, type=Path)
    return result


def main():
    args = parser().parse_args()
    state = args.state_dir.resolve()
    if ROOT / "work" not in state.parents:
        parser().error("--state-dir must be a child of this fixture's work/ directory")
    state.mkdir(parents=True, exist_ok=True)
    try:
        output = execute(args, state)
        exit_code = 0 if output.get("ok", True) else 1
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        output = {"synthetic": True, "ok": False, "error": str(error), "actual_device_load": False}
        exit_code = 1
    event = {"synthetic": True, "command": args.command,
             "arguments": {key: str(value) if isinstance(value, Path) else value
                           for key, value in vars(args).items() if key not in ("state_dir", "command")},
             "result": output, "exit_code": exit_code}
    with (state / "calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
