"""Exercise reuse and single-shard repair in this project's isolated IR cache."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify(executable, root, plan, lock, base):
    root = Path(root).resolve()
    owned = Path(__file__).resolve().parents[1]/".boom"
    check(root.is_relative_to(owned.resolve()), "Cache mutation test requires this project's .boom directory")
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
    original_summary = (root/"summary.json").read_bytes()
    original_index = (root/"shards.jsonl").read_bytes()
    cold = json.loads(original_summary)
    check(cold["mode"] == "symbolic_ir_only" and cold["counts"]["failed_methods"] == 0,
          "Expected a complete cold symbolic IR extraction")
    (root/"cold-summary.json").write_text(json.dumps(cold, indent=2)+"\n", encoding="utf-8")
    initial_index = [json.loads(line) for line in (root/"shards.jsonl").read_text(encoding="utf-8").splitlines()]
    initial_payloads = {entry["class_id"]: entry["digest"] for shard in initial_index for entry in shard["entries"]}
    command = [str(Path(executable).resolve()), "lower-translation", "--lock", str(lock),
               "--jdk-base", str(base), "--plan", str(plan), "--output", str(root)]

    def run(workers, label):
        result = subprocess.run(command+["--workers", str(workers)], capture_output=True, text=True)
        (root/f"{label}.stdout.json").write_text(result.stdout, encoding="utf-8")
        (root/f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")
        check(result.returncode == 0, f"IR cache run failed: {result.stderr[-2000:]}")
        summary = read(root/"summary.json")
        check(summary["identity"] == cold["identity"] and summary["counts"] == cold["counts"],
              "IR cache changed input identity or coverage")
        return summary

    cached = run(1, "cache-reuse")
    check(cached["reused_shards"] == cold["shards"], "Unchanged IR shards were regenerated")
    check(cached["index"]["digest"] == cold["index"]["digest"], "Unchanged IR cache index differs")
    target = root/"shards"/Path(initial_index[0]["zip"]["path"]).name
    check(target.resolve().is_relative_to(root) and target.stat().st_size > 32, "Invalid owned cache target")
    original = target.read_bytes()
    damaged = bytearray(original)
    damaged[32] ^= 0x40
    target.write_bytes(damaged)
    try:
        repaired = run(8, "cache-repair")
        check(repaired["reused_shards"] == cold["shards"]-1, "Damaged shard was not selectively regenerated")
        repaired_index = [json.loads(line) for line in (root/"shards.jsonl").read_text(encoding="utf-8").splitlines()]
        payloads = {entry["class_id"]: entry["digest"] for shard in repaired_index for entry in shard["entries"]}
        check(payloads == initial_payloads, "Rebuilt IR class payloads differ")
        check(hashlib.sha256(target.read_bytes()).hexdigest() == repaired_index[0]["zip"]["digest"]["sha256"],
              "Repaired shard digest differs")
    except BaseException:
        target.write_bytes(original)
        (root/"summary.json").write_bytes(original_summary)
        (root/"shards.jsonl").write_bytes(original_index)
        raise
    report = dict(verified=True, scope="symbolic_ir_cache_only", reused_shards=cached["reused_shards"],
                  damaged_shards=1, regenerated_shards=1, unchanged_payloads=True,
                  cold_elapsed_ms=cold["elapsed_ms"], reuse_elapsed_ms=cached["elapsed_ms"],
                  repair_elapsed_ms=repaired["elapsed_ms"], game_started=False, full_game_ready=False)
    (root/"cache-verification.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir", type=Path)
    parser.add_argument("--boom", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--jdk-base", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.boom, args.ir, args.plan, args.lock, args.jdk_base), indent=2))
