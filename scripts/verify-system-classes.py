"""Verify resolved system class provenance, package routing, and optional JVM loader oracle."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("source_ir", Path(__file__).with_name("verify-translation-ir.py"))
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)


def check(condition, message):
    if not condition: raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    with Path(path).open("rb") as stream:
        one, two, size = hashlib.sha1(), hashlib.sha256(), 0
        while data := stream.read(1024*1024):
            one.update(data); two.update(data); size += len(data)
    return dict(size=size, sha1=one.hexdigest(), sha256=two.hexdigest())


def verify(manifest, lock, oracle=None):
    manifest = Path(manifest).resolve()
    catalog, inputs = read(manifest), read(lock)
    check(catalog["schema"] == 1 and catalog["mode"] == "resolved_system_classes", "Unexpected catalog schema/mode")
    check(catalog["input_fingerprint"] == inputs["fingerprint"], "System class input identity differs")
    identity = [catalog[key] for key in ("schema", "mode", "input_fingerprint")]
    identity += [catalog[key]["digest"] for key in ("image", "extractor", "module_snapshot")]
    identity += [catalog[key] for key in ("module_snapshot_fingerprint", "packages", "classes")]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    check(hashlib.sha256(encoded).hexdigest() == catalog["fingerprint"], "System class catalog identity changed")
    for name in ("image", "extractor", "module_snapshot"):
        check(digest(catalog[name]["path"]) == catalog[name]["digest"], f"System class input changed: {name}")
    locked = next(item for item in inputs["java"]["runtime_files"] if item["path"] == catalog["image"]["path"])
    check(locked["digest"] == catalog["image"]["digest"], "System class image is not a locked input")
    snapshot_path = Path(catalog["module_snapshot"]["path"])
    snapshot = read(snapshot_path)
    check(snapshot["fingerprint"] == catalog["module_snapshot_fingerprint"]
          and snapshot["input_fingerprint"] == inputs["fingerprint"], "System module snapshot identity differs")
    owners = {}
    for name, resolved in snapshot["graph"]["resolved"].items():
        module = snapshot["modules"][name]
        path = snapshot_path.parent/"image"/name/"module-info.class"
        check(digest(path)["sha256"] == module["sha256"], "Original module descriptor changed")
        loader = "vanilla-application" if resolved["loader"] == "application" else resolved["loader"]
        for package in module["descriptor"]["packages"]:
            owner = dict(module=name, loader=loader)
            check(package not in owners or owners[package] == owner, "Conflicting resolved package owners")
            owners[package] = owner
    check(owners == catalog["packages"], "System package routing differs from module resolution")
    by_loader, by_module, expected_oracle = Counter(), Counter(), {}
    for name, origin in catalog["classes"].items():
        binary = name.replace(".", "/")
        package = binary.rsplit("/", 1)[0]
        check(name == origin["binary_name"] and origin.get("generated") is None, "Invalid raw system class identity")
        owner = owners[package]
        check(origin["source_id"] == "jdk:"+owner["module"] and origin["loader"] == owner["loader"],
              "System class loader/module differs from resolution")
        entry = owner["module"]+"/"+binary+".class"
        check(origin["jar_entry"] == entry and ".." not in entry.split("/"), "System class entry/name differs")
        raw = (manifest.parent/"image"/entry).read_bytes()
        check(hashlib.sha256(raw).hexdigest() == origin["sha256"], "Original system class changed")
        check(SOURCE.Source(raw).name == binary and int.from_bytes(raw[6:8], "big") == origin["java_class_major"],
              "Original system class declaration differs")
        by_loader[origin["loader"]] += 1; by_module[owner["module"]] += 1
        expected_oracle[(owner["module"], name)] = origin["loader"]
    actual_entries = {p.relative_to(manifest.parent/"image").as_posix()
                      for p in (manifest.parent/"image").rglob("*.class") if p.name != "module-info.class"}
    check(actual_entries == {o["jar_entry"] for o in catalog["classes"].values()}, "System class catalog coverage differs")
    oracle_count = 0
    if oracle:
        observed = {}
        for line in Path(oracle).read_text(encoding="utf-8-sig").splitlines():
            module, name, loader = line.split("\t")
            check((module, name) not in observed, "Duplicate JVM class loader record")
            observed[(module, name)] = loader
        check(observed == expected_oracle, "JVM class/module/defining-loader identity differs")
        oracle_count = len(observed)
    return dict(verified=True, scope="system_class_source_package_routing_and_defining_loader_only",
                classes=len(catalog["classes"]), resolved_modules=len(snapshot["graph"]["resolved"]),
                modules_with_classes=len(by_module), by_loader=dict(by_loader), by_module=dict(by_module),
                JVM_noninitializing_loader_cases=oracle_count, module_access_verified=False,
                game_started=False, world_created=False, full_game_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.manifest, args.lock, args.oracle)
    text = json.dumps(result, indent=2)+"\n"
    if args.output: args.output.write_text(text, encoding="utf-8")
    print(text, end="")
