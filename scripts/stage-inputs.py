"""Offline candidate: validate unique input files at two boundaries of one stage.

No file facts survive into another stage, call, or source epoch. This is a
boundary check, not a lock or an assertion that files cannot change in between.
Original references are retained; successful canonical records have the same
two digest keys (size/SHA256) as the existing B.unique implementation.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import re
import uuid


class InputStageError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise InputStageError(message)


def _digest(value, length, label):
    _require(isinstance(value, str) and re.fullmatch("[0-9a-f]{%d}" % length, value) is not None,
             "Invalid lowercase " + label)
    return value


def _stat_signature(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, getattr(value, 'st_birthtime_ns', None))


class InputStage:
    """Single-use context; every successful stage hashes each unique file twice.

    Grouping resolves absolute paths using Path.resolve, then casefolds the
    resolved spelling, as the Windows caller does. Conflicting declarations
    fail before file contents are opened. Optional SHA1 is actually checked in
    the same streaming pass as SHA256. Other top-level metadata is preserved.
    """

    def __init__(self, references, *, source_epoch):
        _require(isinstance(source_epoch, str) and bool(source_epoch.strip()),
                 "An explicit nonempty source epoch is required")
        self.source_epoch = source_epoch
        self.stage_id = uuid.uuid4().hex
        self.state = "NEW"
        self.references = copy.deepcopy(list(references))
        self._entries = {}
        self._before = {}
        self._after = {}
        self._canonical = None
        self.counters = {phase: dict(open_attempts=0, SHA256_passes=0, SHA1_passes=0, bytes_read=0)
                         for phase in ("before", "after")}
        self.canonical_requests = 0
        self.error = None
        for index, row in enumerate(self.references):
            _require(isinstance(row, dict) and isinstance(row.get("path"), str),
                     "A reference must declare a path")
            raw_path = Path(row["path"])
            _require(raw_path.is_absolute(), "Only explicit absolute input paths are supported")
            path = raw_path.resolve()
            key = str(path).casefold()
            digest = row.get("digest")
            _require(isinstance(digest, dict) and {"size", "sha256"} <= set(digest)
                     and set(digest) <= {"size", "sha256", "sha1"},
                     "A reference must declare size/SHA256 and optional SHA1")
            _require(type(digest["size"]) is int and digest["size"] >= 0,
                     "Invalid declared file size")
            expected = dict(size=digest["size"], sha256=_digest(digest["sha256"], 64, "SHA256"))
            if "sha1" in digest:
                expected["sha1"] = _digest(digest["sha1"], 40, "SHA1")
            if key not in self._entries:
                self._entries[key] = dict(path=path, canonical_path=str(path), expected=expected,
                                          reference_indexes=[index])
            else:
                entry = self._entries[key]
                for name in ("size", "sha256", "sha1"):
                    if name in expected and name in entry["expected"]:
                        _require(expected[name] == entry["expected"][name],
                                 "Conflicting declared " + name + " for " + str(path))
                entry["expected"].update(expected)
                entry["reference_indexes"].append(index)
                # B.unique retains the final canonical value for an existing
                # casefolded key, without changing its first insertion order.
                entry["canonical_path"] = str(path)

    def _epoch(self, source_epoch):
        _require(source_epoch == self.source_epoch, "Source epoch differs from this single-use stage")

    def _snapshot(self, entry, phase):
        counters = self.counters[phase]
        counters["open_attempts"] += 1
        expected = entry["expected"]
        with entry["path"].open("rb") as stream:
            before = os.fstat(stream.fileno())
            sha256 = hashlib.sha256()
            sha1 = hashlib.sha1() if "sha1" in expected else None
            counters["SHA256_passes"] += 1
            counters["SHA1_passes"] += int(sha1 is not None)
            size = 0
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                counters["bytes_read"] += len(block)
                sha256.update(block)
                if sha1 is not None:
                    sha1.update(block)
            after = os.fstat(stream.fileno())
        current_path = entry["path"].stat()
        _require(_stat_signature(before) == _stat_signature(after) == _stat_signature(current_path)
                 and before.st_ctime_ns == after.st_ctime_ns and size == after.st_size, "Input changed while hashing: " + str(entry["path"]))
        actual = dict(size=size, sha256=sha256.hexdigest())
        if sha1 is not None:
            actual["sha1"] = sha1.hexdigest()
        _require(all(actual[name] == value for name, value in expected.items()),
                 "Input differs from declared digest at " + phase + ": " + str(entry["path"]))
        return actual

    def __enter__(self):
        _require(self.state == "NEW", "A stage cannot be entered again")
        self.state = "OPENING"
        try:
            for key, entry in self._entries.items():
                self._before[key] = self._snapshot(entry, "before")
            self._canonical = [dict(path=entry["canonical_path"],
                                    digest={name: self._before[key][name] for name in ("size", "sha256")})
                               for key, entry in self._entries.items()]
            self.state = "OPEN"
            return self
        except BaseException as error:
            self.state, self.error = "FAILED", repr(error)
            raise

    def canonical_inputs(self, *, source_epoch):
        self._epoch(source_epoch)
        _require(self.state == "OPEN", "Canonical inputs are available only inside the open stage")
        self.canonical_requests += 1
        return copy.deepcopy(self._canonical)

    def close(self, *, source_epoch):
        self._epoch(source_epoch)
        _require(self.state == "OPEN", "Only an open stage can close")
        self.state = "CLOSING"
        try:
            for key, entry in self._entries.items():
                actual = self._snapshot(entry, "after")
                _require(actual == self._before[key], "Input changed between stage boundaries")
                self._after[key] = actual
            self.state = "CLOSED"
        except BaseException as error:
            self.state, self.error = "FAILED", repr(error)
            raise
        finally:
            # No callable file-fact cache remains after closure or failure.
            self._canonical = None

    def __exit__(self, error_type, error, traceback):
        if self.state == "OPEN":
            self.close(source_epoch=self.source_epoch)
        return False

    def observation(self):
        """Accounting only: this record cannot reopen or seed another stage."""
        return dict(stage_id=self.stage_id, source_epoch=self.source_epoch, state=self.state,
                    original_references=copy.deepcopy(self.references),
                    unique_paths=len(self._entries), reference_count=len(self.references),
                    reference_indexes_by_path={str(v["path"]): list(v["reference_indexes"])
                                               for v in self._entries.values()},
                    counters=copy.deepcopy(self.counters), canonical_requests=self.canonical_requests,
                    boundary_complete=self.state == "CLOSED", error=self.error,
                    no_cross_stage_or_epoch_cache=True, boundary_checks_are_not_file_locks=True)


def validate_inputs(references, *, source_epoch):
    """One call, two fresh boundaries; returns canonical records and accounting."""
    stage = InputStage(references, source_epoch=source_epoch)
    with stage:
        values = stage.canonical_inputs(source_epoch=source_epoch)
    return values, stage.observation()
