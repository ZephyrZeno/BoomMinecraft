"""Generate MASM data only after exhaustive agreement with the locked JDK oracle."""
import argparse
import hashlib
import json
import pathlib
import struct


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ucd", type=pathlib.Path, required=True)
    p.add_argument("--oracle", type=pathlib.Path, required=True)
    p.add_argument("--jdk-base", type=pathlib.Path, required=True)
    p.add_argument("--assembly", type=pathlib.Path, required=True)
    p.add_argument("--manifest", type=pathlib.Path, required=True)
    a = p.parse_args()
    raw = a.ucd.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73":
        raise ValueError("Expected the exact official Unicode 15.0 UnicodeData.txt")
    data = {}
    for line in raw.decode("utf-8").splitlines():
        fields = line.split(";")
        cp = int(fields[0], 16)
        upper, lower = (int(fields[n], 16) if fields[n] else cp for n in (12, 13))
        if cp != upper or cp != lower:
            if not all(0 <= x <= 0x10FFFF for x in (cp, upper, lower)) or cp in data:
                raise ValueError("Malformed Unicode row")
            data[cp] = (upper, lower)
    oracle = a.oracle.read_bytes()
    magic, count = struct.unpack_from(">II", oracle)
    if magic != 0x55434331 or len(oracle) != 8 + count * 12:
        raise ValueError("Malformed independent oracle")
    observed = {}
    for off in range(8, len(oracle), 12):
        cp, upper, lower = struct.unpack_from(">III", oracle, off)
        if cp in observed:
            raise ValueError("Repeated oracle row")
        observed[cp] = (upper, lower)
    if data != observed:
        different = [hex(cp) for cp in sorted(data.keys() | observed.keys())
                     if data.get(cp) != observed.get(cp)]
        raise ValueError("Unicode/JDK simple mappings differ: " + ", ".join(different[:20]))
    rows = sorted((cp, *values) for cp, values in data.items())
    packed = b"".join(struct.pack("<III", *r) for r in rows)
    begin, end = "; BEGIN GENERATED UNICODE SIMPLE CASE DATA", "; END GENERATED UNICODE SIMPLE CASE DATA"
    source = a.assembly.read_text(encoding="utf-8")
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError("Missing unique assembly data markers")
    body = [begin, ".const", f"unicode_case_count EQU {len(rows)}", "ALIGN 4", "unicode_case_rows LABEL DWORD"]
    body += ["    DWORD " + ", ".join(f"0{x:08X}h" for x in row) for row in rows]
    source = source.split(begin)[0] + "\n".join(body) + "\n" + end + source.split(end)[1]
    base = json.loads(a.jdk_base.read_text(encoding="utf-8-sig"))
    names = ["java.lang.Character", "java.lang.CharacterData", "java.lang.CharacterDataLatin1",
             "java.lang.CharacterData00", "java.lang.CharacterData01", "java.lang.CharacterData02",
             "java.lang.CharacterData03", "java.lang.CharacterData0E", "java.lang.CharacterDataUndefined",
             "java.lang.CharacterDataPrivateUse"]
    manifest = {"abi": 1, "unicode_version": "15.0.0", "source_url": "https://www.unicode.org/Public/15.0.0/ucd/UnicodeData.txt",
                "source_sha256": digest, "mapping_rows": len(rows), "mapping_bytes_sha256": hashlib.sha256(packed).hexdigest(),
                "exhaustive_code_points": 0x110000, "jdk_character_sources": {name: base["classes"][name]["sha256"] for name in names}}
    a.assembly.write_text(source, encoding="utf-8", newline="\n")
    a.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Generated {len(rows)} mapping rows after exhaustive Unicode/JDK agreement")


if __name__ == "__main__":
    main()
