"""Compare source-identical Java method candidates across two input-universe builds."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def check_artifact(path, expected):
    with Path(path).open("rb") as stream:
        one, two, size = hashlib.sha1(), hashlib.sha256(), 0
        while data := stream.read(1024*1024):
            one.update(data); two.update(data); size += len(data)
    if dict(size=size, sha1=one.hexdigest(), sha256=two.hexdigest()) != expected:
        raise ValueError("Batch comparison artifact changed: "+str(path))


def inventory(batch, plan):
    batch, plan = Path(batch), Path(plan)
    summary, source = read(batch/"summary.json"), read(plan/"summary.json")
    if summary["input_fingerprint"] != source["input_fingerprint"]:
        raise ValueError("Comparison plan belongs to different locked input")
    class_path = plan/"classes.jsonl"
    check_artifact(class_path, source["artifacts"]["classes"]["digest"])
    origins = [json.loads(line)["origin"] for line in class_path.read_text(encoding="utf-8").splitlines()]
    methods = {}
    for shard in summary["shards"]:
        path = batch/"shards"/Path(shard["zip"]["path"]).name
        check_artifact(path, shard["zip"]["digest"])
        with zipfile.ZipFile(path) as bundle:
            for name in bundle.namelist():
                unit = json.loads(bundle.read(name))
                origin = origins[unit["class_id"]]
                if unit["source_sha256"] != origin["sha256"]:
                    raise ValueError("Comparison class source differs from plan")
                for method in unit["methods"]:
                    if method["code_sha256"] is None: continue
                    key = (origin["loader"], origin["source_id"], unit["name"], origin["sha256"],
                           method["name"], method["descriptor"], method["code_sha256"])
                    if key in methods: raise ValueError("Duplicate source method in comparison")
                    methods[key] = (method["assembly_emitted"], method["diagnostic"])
    if len(methods) != summary["counts"]["java_methods"]:
        raise ValueError("Comparison method inventory is truncated")
    return summary, methods


def compare(old, new, old_plan, new_plan):
    before, old_methods = inventory(old, old_plan)
    after, new_methods = inventory(new, new_plan)
    if before["input_fingerprint"] != after["input_fingerprint"]:
        raise ValueError("Only the same locked Minecraft input may be compared")
    counts, recovered, regressed = Counter(), [], []
    for key, (generated, diagnostic) in old_methods.items():
        if key not in new_methods:
            counts["old_methods_absent_from_new_universe"] += 1
            continue
        counts["source_identical_methods"] += 1
        now, new_diagnostic = new_methods[key]
        counts["old_generated_on_shared_source"] += generated
        counts["new_generated_on_shared_source"] += now
        counts["new_failures_on_shared_source"] += not now
        if now and not generated:
            counts["previously_failed_now_generated"] += 1
            if len(recovered) < 20: recovered.append(dict(loader=key[0], owner=key[2], method=key[4], descriptor=key[5], old_diagnostic=diagnostic))
        elif generated and not now:
            counts["previously_generated_now_failed"] += 1
            if len(regressed) < 20: regressed.append(dict(loader=key[0], owner=key[2], method=key[4], descriptor=key[5], diagnostic=new_diagnostic))
    counts["additional_java_methods_in_new_universe"] = len(new_methods.keys()-old_methods.keys())
    return dict(verified=True, scope="source_identical_Java_method_assembly_generation_only",
                old_java_methods=len(old_methods), new_java_methods=len(new_methods), counts=dict(counts),
                recovered_examples=recovered, regressed_examples=regressed,
                runtime_compatibility_verified=False, linked=False, game_started=False, full_game_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path); parser.add_argument("new", type=Path)
    parser.add_argument("--old-plan", type=Path, required=True)
    parser.add_argument("--new-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.old, args.new, args.old_plan, args.new_plan)
    text = json.dumps(result, indent=2)+"\n"
    if args.output: args.output.write_text(text, encoding="utf-8")
    print(text, end="")
