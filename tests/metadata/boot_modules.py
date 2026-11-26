"""Offline module-input differential test. Never starts Minecraft."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def identity(snapshot):
    # Match only the manifest's canonical encoding for adversarial mutations.
    # Resolution expectations come independently from the real JVM below.
    snapshot["modules"] = dict(sorted(snapshot["modules"].items()))
    snapshot["graph"]["resolved"] = dict(sorted(snapshot["graph"]["resolved"].items()))
    value = [snapshot["schema"], snapshot["input_fingerprint"], snapshot["image"]["digest"],
             snapshot["extractor"]["digest"], snapshot["loader_table_sha256"],
             snapshot["loaders"], snapshot["modules"], snapshot["graph"]]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def normalized(descriptor):
    d = copy.deepcopy(descriptor)
    # These two image attributes have no public ModuleDescriptor getter. The
    # resolution flags are checked indirectly against the actual default roots.
    d.pop("target", None)
    d.pop("resolution_flags", None)
    for key in ("exports", "opens"):
        for directive in d[key]:
            directive["targets"].sort()
    for key in ("requires", "exports", "opens", "uses", "provides", "packages"):
        d[key].sort(key=lambda v: json.dumps(v, sort_keys=True))
    return d


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--boom", required=True)
    p.add_argument("--lock", required=True)
    p.add_argument("--other-lock")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    project = Path(__file__).resolve().parents[2]
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    boom = str(Path(args.boom).resolve())
    lock = str(Path(args.lock).resolve())
    inputs = load(lock)
    java = Path(inputs["java"]["executable"])
    env = dict(os.environ)
    for key in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"):
        env.pop(key, None)
    sequence = 0

    def run(argv, expected=0):
        nonlocal sequence
        sequence += 1
        result = subprocess.run([str(a) for a in argv], cwd=project, env=env,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=90, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        (root / f"command-{sequence}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != expected:
            raise AssertionError(f"Command failed ({result.returncode}): {argv}\n{result.stdout}\n{result.stderr}")
        return result.stdout, result.stderr

    snapshot_root = root / "snapshot"
    run([boom, "prepare-jdk-modules", "--lock", lock, "--output", snapshot_root])
    manifest = snapshot_root / "jdk-modules.json"
    snapshot = load(manifest)
    assert identity(copy.deepcopy(snapshot)) == snapshot["fingerprint"]
    run([boom, "plan-boot-modules", "--lock", lock, "--jdk-modules", manifest, "--output", root / "plan"])
    plan = load(root / "plan/boot-modules.json")
    assert plan["graph"] == snapshot["graph"] and not plan["module_layer_execution"] and not plan["full_game_ready"]

    classes = root / "oracle-classes"
    classes.mkdir()
    run([java.parent / ("javac.exe" if os.name == "nt" else "javac"), "--release", "21", "-proc:none",
         "-encoding", "UTF-8", "-d", classes, project / "java/subset/dev/boom/subset/BootModuleOracle.java"])
    stdout, stderr = run([java, "--show-module-resolution", "-cp", classes, "dev.boom.subset.BootModuleOracle"])
    (root / "oracle.txt").write_text(stdout, encoding="utf-8")
    lines = stdout.splitlines()
    oracle = json.loads(next(x.removeprefix("BOOM_MODULE_ORACLE ") for x in lines if x.startswith("BOOM_MODULE_ORACLE ")))
    roots = sorted(x.split()[1] for x in lines if x.startswith("root "))
    assert roots == snapshot["graph"]["roots"], "Default root modules differ from JVM"
    assert oracle["resolved"] == snapshot["graph"]["resolved"], "Resolved modules, loaders or canRead relation differ from JVM"
    assert oracle["descriptors"].keys() == snapshot["modules"].keys(), "Observable module universe differs"
    for name, entry in snapshot["modules"].items():
        assert normalized(entry["descriptor"]) == normalized(oracle["descriptors"][name]), f"Descriptor differs: {name}"

    second = root / "second-preparation"
    run([boom, "prepare-jdk-modules", "--lock", lock, "--output", second])
    assert (second / "jdk-modules.json").read_bytes() == manifest.read_bytes(), "Preparation is not reproducible"
    moved = root / "迁移 cache"
    shutil.copytree(snapshot_root, moved)
    run([boom, "plan-boot-modules", "--lock", lock, "--jdk-modules", moved / "jdk-modules.json", "--output", root / "moved-plan"])

    rejections = []
    def reject(label, mutation, expected_message):
        destination = root / label
        shutil.copytree(snapshot_root, destination)
        changed = load(destination / "jdk-modules.json")
        mutation(changed, destination)
        changed["fingerprint"] = identity(changed)
        save(destination / "jdk-modules.json", changed)
        output = root / (label + "-plan")
        stdout, stderr = run([boom, "plan-boot-modules", "--lock", lock, "--jdk-modules", destination / "jdk-modules.json", "--output", output], 1)
        assert expected_message in stderr, (label, stderr)
        assert not output.exists(), f"Rejected snapshot published a plan: {label}"
        rejections.append(label)

    def corrupt_descriptor(s, d):
        path = d / "image/java.base/module-info.class"
        data = bytearray(path.read_bytes()); data[0] ^= 1; path.write_bytes(data)
    def corrupt_loader(s, d):
        path = d / "image/java.base/jdk/internal/module/ModuleLoaderMap$Modules.class"
        data = bytearray(path.read_bytes()); data[0] ^= 1; path.write_bytes(data)
    def descriptor_model(s, d):
        s["modules"]["java.base"]["descriptor"]["version"] = "forged"
    def resolution_model(s, d):
        del s["graph"]["resolved"]["java.base"]
    def loader_model(s, d):
        s["loaders"]["platform"] = sorted(set(s["loaders"]["platform"]) | {"java.base"})
    def escape_name(s, d):
        s["modules"]["../escape"] = s["modules"].pop("java.base")
    def oversized(s, d):
        (d / "image/java.base/module-info.class").write_bytes(bytes(1024 * 1024 + 1))
    reject("raw-descriptor", corrupt_descriptor, "Invalid Java class magic")
    reject("raw-loader", corrupt_loader, "Module defining loader tables changed")
    reject("descriptor-model", descriptor_model, "System module descriptor changed")
    reject("resolution-model", resolution_model, "Cached system module resolution does not match")
    reject("loader-model", loader_model, "Module defining loader tables changed")
    reject("escape-name", escape_name, "Unsupported system module name")
    reject("oversized-descriptor", oversized, "Oversized system module input")
    if args.other_lock:
        output = root / "wrong-lock-plan"
        _, stderr = run([boom, "plan-boot-modules", "--lock", Path(args.other_lock).resolve(), "--jdk-modules", manifest, "--output", output], 1)
        assert "System module snapshot identity mismatch" in stderr and not output.exists()
        rejections.append("other-input-lock")

    report = {
        "scope": "locked JDK21 system modules, default classpath profile; offline compiler metadata",
        "snapshot_fingerprint": snapshot["fingerprint"],
        "snapshot": str(manifest), "available_modules": len(snapshot["modules"]),
        "descriptor_records_checked": len(snapshot["modules"]),
        "default_roots": len(roots), "resolved_modules": len(snapshot["graph"]["resolved"]),
        "module_loader_identities_checked": len(oracle["resolved"]),
        "readability_pairs_checked": len(oracle["resolved"]) ** 2,
        "available_not_resolved": sorted(set(snapshot["modules"]) - set(snapshot["graph"]["resolved"])),
        "service_bindings": len(snapshot["graph"]["service_bindings"]),
        "reproducible_preparation": True, "relocated_cache_verified": True,
        "rehash_does_not_bypass_source_or_graph_validation": True,
        "cache_rejections": rejections, "rejection_count": len(rejections),
        "game_started": False, "module_layer_execution": False,
        "module_layer_findmodule_executable": False, "full_game_ready": False,
        "passed": True, "run_directory": str(root),
    }
    save(root / "result.json", report)
    (project / ".boom/latest-jdk-module-tests.txt").write_text(str(root), encoding="utf-8")
    (project / ".boom/latest-jdk-modules.txt").write_text(str(snapshot_root), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
