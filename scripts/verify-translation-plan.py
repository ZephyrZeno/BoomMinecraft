"""Independently verify inventory hashes, coverage and dependency batches.

This verifies a translation PLAN. It never claims compiled or executable code.
Uses only Python's standard library and does not launch Java or the game.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(root, artifact):
    path = root / Path(artifact["path"]).name
    size = 0
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    require({"size": size, "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}
            == artifact["digest"], f"Artifact digest mismatch: {path}")
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def reach(graph, seeds, membership=None, batch=None):
    seen = set()
    todo = list(seeds)
    while todo:
        node = todo.pop()
        if node in seen or (membership is not None and membership[node] != batch):
            continue
        seen.add(node)
        todo.extend(graph[node])
    return seen


def verify(root):
    root = Path(root).resolve()
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    require(summary["mode"] == "inventory_and_plan_only", "Unexpected planner mode")
    require(summary["compiled_methods"] == 0, "Planner cannot claim compiled methods")
    for flag in ("game_started", "world_created", "full_game_ready",
                 "type_layout_and_link_verified", "native_catalog_is_complete"):
        require(summary[flag] is False, f"Planner incorrectly claims {flag}")
    artifacts = summary["artifacts"]
    require(set(artifacts) == {"classes", "methods", "compatibility", "batches",
                               "dependencies", "opcodes"}, "Incomplete artifact manifest")
    classes = list(rows(root, artifacts["classes"]))
    total = summary["methods"]
    require(len(classes) == summary["classes"], "Class count differs")
    require(sum(c["parse_error"] is not None for c in classes)
            == summary["class_parse_failures"], "Class failure count differs")
    require(summary["java_base_classes"] + summary.get("additional_system_classes", 0)
            + summary["application_classes"] == len(classes),
            "Selected input count differs")
    owners = [-1] * total
    identities = set()
    for expected, c in enumerate(classes):
        require(c["id"] == expected, "Class IDs are not deterministic and contiguous")
        key = c["origin"]["loader"], c["name"]
        require(key not in identities, "Defining-loader class identity collision")
        identities.add(key)
        for method in c["method_ids"]:
            require(0 <= method < total and owners[method] == -1, "Duplicate/invalid method owner")
            owners[method] = expected
    require(-1 not in owners, "A method is missing from its defining class")
    kinds, counts = Counter(), Counter()
    startup, main = set(), set()
    expected_groups = defaultdict(lambda: {"occurrences": 0, "methods": set()})
    symbols = set()
    for expected, m in enumerate(rows(root, artifacts["methods"])):
        require(expected < total and m["id"] == expected, "Invalid method ID sequence")
        require(m["class_id"] == owners[expected], "Method defining class differs")
        c = classes[m["class_id"]]
        require(m["class_sha256"] == c["origin"]["sha256"], "Method source hash differs")
        symbol = m["symbol"]
        require((symbol["loader"], symbol["owner"])
                == (c["origin"]["loader"], c["name"]), "Method loader identity differs")
        key = tuple(symbol[k] for k in ("loader", "owner", "name", "descriptor"))
        require(key not in symbols, "Duplicate method symbol")
        symbols.add(key)
        require(not m["assembly_emitted"] and not m["type_layout_and_link_verified"],
                "Inventory row incorrectly claims generated/verified code")
        kinds[m["kind"]] += 1
        counts["methods"] += 1
        counts["java_methods"] += m["code_sha256"] is not None
        counts["native_methods"] += bool(m["access"] & 0x100)
        counts["abstract_methods"] += bool(m["access"] & 0x400)
        counts["structurally_scanned_java_methods"] += m["structural_scan_complete"]
        if m["conservative_startup_reachable"]:
            startup.add(expected)
        if m["conservative_main_reachable"]:
            main.add(expected)
        for problem in m["problems"]:
            group = expected_groups[problem["category"], problem["target"]]
            group["occurrences"] += 1
            group["methods"].add(expected)
    for key, count in counts.items():
        require(count == summary[key], f"Method total differs: {key}")
    require(counts["methods"] == total, "Method inventory is truncated")
    require(kinds["native_binding_candidate"] == summary["native_binding_candidates"],
            "Native binding candidate total differs")
    require(kinds["native_compatibility"] == summary["native_without_catalog_entry"],
            "Uncatalogued native total differs")
    graph, reverse = [], [[] for _ in range(total)]
    for expected, row in enumerate(rows(root, artifacts["dependencies"])):
        require(expected < total and row["method_id"] == expected, "Invalid dependency row")
        edges = row["dependencies"]
        require(edges == sorted(set(edges)) and all(0 <= n < total for n in edges),
                "Invalid or duplicated dependency")
        graph.append(edges)
        for dest in edges:
            reverse[dest].append(expected)
    require(len(graph) == total, "Dependency graph is truncated")
    require(sum(map(len, graph)) == summary["dependency_edges"], "Dependency edge total differs")
    require(reach(graph, summary["startup_seed_methods"]) == startup,
            "Startup reachability differs from graph")
    require(reach(graph, summary["main_seed_methods"]) == main,
            "Main reachability differs from graph")
    require(len(startup) == summary["conservative_startup_methods"]
            and len(main) == summary["conservative_main_methods"], "Reachability totals differ")
    batches = list(rows(root, artifacts["batches"]))
    require(len(batches) == summary["batches"], "Batch count differs")
    membership = [-1] * total
    for expected, batch in enumerate(batches):
        require(batch["id"] == expected and batch["method_ids"], "Invalid/empty batch")
        for node in batch["method_ids"]:
            require(0 <= node < total and membership[node] == -1, "Duplicate/invalid batch member")
            membership[node] = expected
    require(-1 not in membership, "A method is missing from the batch queue")
    for batch in batches:
        nodes, batch_id = set(batch["method_ids"]), batch["id"]
        dependencies = {membership[dest] for node in nodes for dest in graph[node]
                        if membership[dest] != batch_id}
        require(sorted(dependencies) == batch["dependency_batches"], "Batch dependencies differ")
        require(all(dest < batch_id for dest in dependencies), "Caller scheduled before dependency")
        seed = batch["method_ids"][0]
        if len(nodes) > 1:
            require(reach(graph, [seed], membership, batch_id) == nodes
                    and reach(reverse, [seed], membership, batch_id) == nodes,
                    "Batch is not a strongly connected component")
        require(batch["startup_priority"] == bool(nodes & startup)
                and batch["main_priority"] == bool(nodes & main), "Batch priority differs")
    actual_groups = set()
    for group in rows(root, artifacts["compatibility"]):
        key = group["category"], group["target"]
        require(key not in actual_groups and key in expected_groups, "Unexpected/duplicate issue group")
        actual_groups.add(key)
        expected = expected_groups[key]
        affected = expected["methods"]
        require(group["occurrences"] == expected["occurrences"]
                and group["affected_methods"] == sorted(affected), "Issue group coverage differs")
        require(group["startup_methods"] == len(affected & startup)
                and group["main_methods"] == len(affected & main), "Issue group priority differs")
    require(actual_groups == set(expected_groups)
            and len(actual_groups) == summary["compatibility_groups"], "Missing issue groups")
    list(rows(root, artifacts["opcodes"]))
    return {"verified": True, "scope": "inventory_hashes_coverage_and_dependency_plan_only",
            "classes": len(classes), "methods": total, "batches": len(batches),
            "compatibility_groups": len(actual_groups), "compiled_methods": 0,
            "game_started": False, "world_created": False, "full_game_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.plan)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
