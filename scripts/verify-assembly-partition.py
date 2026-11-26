"""Check that bounded assembler units preserve every prior generated method-body byte."""
import argparse
import hashlib
import json
from pathlib import Path


def update_body(path, digest):
    with Path(path).open("rb") as stream:
        header = 0
        for line in stream:
            header += len(line)
            if line == b".code\n": break
        else: raise ValueError("Missing candidate module code section")
        remaining = Path(path).stat().st_size-header-5
        if remaining < 0: raise ValueError("Truncated candidate module")
        size = remaining
        while remaining:
            data = stream.read(min(1024*1024, remaining))
            if not data: raise ValueError("Truncated candidate method body")
            digest.update(data); remaining -= len(data)
        if stream.read() != b"\nEND\n": raise ValueError("Invalid candidate module trailer")
    return size


def verify(original, partitioned):
    original, partitioned = Path(original), Path(partitioned)
    summary = json.loads((partitioned/"summary.json").read_text(encoding="utf-8"))
    if summary["schema"] != 2: raise ValueError("Expected partitioned batch schema")
    total, units = 0, 0
    for shard in summary["shards"]:
        old = original/"shards"/f'{shard["id"]:05}.asm'
        if not shard["units"]:
            if old.exists(): raise ValueError("Prior body disappeared from partitioned output")
            continue
        before, after = hashlib.sha256(), hashlib.sha256()
        old_size = update_body(old, before)
        new_size = 0
        for unit in shard["units"]:
            new_size += update_body(partitioned/"shards"/Path(unit["assembly"]["path"]).name, after)
            units += 1
        if old_size != new_size or before.digest() != after.digest():
            raise ValueError(f'Generated method bodies changed during partition: shard {shard["id"]}')
        total += new_size
    return dict(verified=True, scope="generated_assembly_body_byte_preservation_only",
                shards=len(summary["shards"]), assembly_units=units, preserved_body_bytes=total,
                game_started=False, full_game_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path); parser.add_argument("partitioned", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.original, args.partitioned)
    text = json.dumps(result, indent=2)+"\n"
    if args.output: args.output.write_text(text, encoding="utf-8")
    print(text, end="")
