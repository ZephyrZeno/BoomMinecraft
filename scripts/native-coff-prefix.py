"""Protect an unchanged native assembly/COFF prefix of an appended object.

Full new-object canonical verification remains the caller's responsibility.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_prefix_full_COFF',ROOT/'scripts/jimage-owner-candidate.py')
O=importlib.util.module_from_spec(spec);spec.loader.exec_module(O)

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=digest))

def read_coff(path):
    """Use the full strict reader first; retain raw prefixes and semantic refs."""
    normalized = O.normalized_coff(path)
    raw = Path(path).read_bytes()
    _, count, _, symbol_at, symbol_count, _, _ = struct.unpack_from('<HHIIIHH', raw)
    strings = symbol_at + symbol_count * 18
    sections, by_id = {}, {}
    for ident in range(1, count + 1):
        at = 20 + 40 * (ident - 1)
        name = raw[at:at + 8].rstrip(b'\0').decode('ascii')
        _, _, size, data, reloc, _, nrel, _, flags = struct.unpack_from('<IIIIIIHHI', raw, at + 8)
        if flags & 0x01000000:
            nrel = struct.unpack_from('<I', raw, reloc)[0] - 1
            reloc += 10
        section = dict(name=name, size=size, flags=flags & ~0x01000000,
                       raw=raw[data:data + size] if name != '.bss' else b'',
                       reloc_at=reloc, reloc_count=nrel, id=ident)
        sections[name] = by_id[ident] = section

    def symbol(index):
        at = symbol_at + index * 18
        name = raw[at:at + 8]
        if name[:4] == bytes(4):
            offset = struct.unpack_from('<I', name, 4)[0]
            end = raw.index(b'\0', strings + offset)
            name = raw[strings + offset:end]
        else:
            name = name.rstrip(b'\0')
        value, section_id, kind, storage, aux = struct.unpack_from('<IhHBB', raw, at + 8)
        section = by_id[section_id]['name'] if section_id > 0 else section_id
        return (name.decode('ascii'), value, section, kind, storage), raw[at + 18:at + 18 * (aux + 1)], aux

    symbols = []
    index = 0
    while index < symbol_count:
        row, aux_bytes, aux = symbol(index)
        if row[4] != 103 and row[2] != '.debug$S':
            symbols.append((row, aux_bytes))
        index += aux + 1
    widths = {1: 8, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 2, 11: 4}
    for section in sections.values():
        relocs = []
        for index in range(section['reloc_count']):
            offset, target, kind = struct.unpack_from('<IIH', raw, section['reloc_at'] + 10 * index)
            row, _, _ = symbol(target)
            relocs.append((offset, kind, section['raw'][offset:offset + widths[kind]].hex(), row))
        section['relocations'] = relocs
    return dict(normalized=normalized, sections=sections, symbols=symbols)


def protected_prefix(old_path, new_path):
    before, after = read_coff(old_path), read_coff(new_path)
    check(before['normalized']['machine'] == after['normalized']['machine']
          and before['normalized']['characteristics'] == after['normalized']['characteristics'],
          'Original COFF machine/header contract changed')
    sections = {}
    for name, old in before['sections'].items():
        if name == '.debug$S':
            continue
        check(name in after['sections'], 'Original section disappeared: ' + name)
        new = after['sections'][name]
        check(new['flags'] == old['flags'] and new['size'] >= old['size'], 'Original section flags/extent changed: ' + name)
        check(new['raw'][:len(old['raw'])] == old['raw'], 'Original code/data/unwind byte prefix changed: ' + name)
        prefix = [row for row in new['relocations'] if row[0] < old['size']]
        check(prefix == old['relocations'], 'Original relocation offsets/kinds/addends/target semantics changed: ' + name)
        sections[name] = dict(old_bytes=old['size'], new_bytes=new['size'], old_relocations=len(prefix),
                              raw_prefix_sha256=hashlib.sha256(old['raw']).hexdigest(), exact_prefix=True)
    available = Counter((row, aux.hex()) for row, aux in after['symbols'])
    section_aux_count = ordinary_count = 0
    for row, aux in before['symbols']:
        name, value, section, kind, storage = row
        if section in before['sections'] and name == section and value == 0 and kind == 0 and storage == 3 and len(aux) == 18:
            # Section lengths/relocation counts necessarily grow. All other
            # old auxiliary bytes stay exact, including checksum/association.
            matches = [(candidate, extra) for candidate, extra in after['symbols'] if candidate == row]
            check(len(matches) == 1 and len(matches[0][1]) == 18, 'Original section auxiliary symbol missing/duplicated')
            changed = matches[0][1]
            current = after['sections'][section]
            check(struct.unpack_from('<IH', changed) == (current['size'], min(current['reloc_count'], 65535))
                  and changed[6:] == aux[6:], 'Unaccounted original section auxiliary mutation: ' + section)
            check(struct.unpack_from('<IH', aux) == (before['sections'][section]['size'],
                  min(before['sections'][section]['reloc_count'], 65535)), 'Original section auxiliary/header disagreement')
            section_aux_count += 1
        else:
            key = (row, aux.hex())
            check(available[key] > 0, 'Original symbol value/type/storage/aux/definition changed: ' + name)
            available[key] -= 1
            ordinary_count += 1
    check(set(before['normalized']['exports']) <= set(after['normalized']['exports'])
          and set(before['normalized']['imports']) <= set(after['normalized']['imports']),
          'Original exported definitions or import targets disappeared')
    return dict(verified=True, old=artifact(old_path), appended=artifact(new_path), sections=sections,
                ordinary_old_symbols_with_exact_aux=ordinary_count, section_symbols_with_derived_lengths_only=section_aux_count,
                old_code_data_relocation_targets_and_unwind_prefixes_equal=True,
                filenames_debug_and_physical_table_offsets_excluded_only=True,
                new_complete_canonical_equivalence_not_proved_here=True)


def source_prefix(old_source,new_source):
    old,new=Path(old_source).read_bytes(),Path(new_source).read_bytes()
    check(old.endswith(b'END\n') and new.endswith(b'END\n') and new.startswith(old[:-4]),
          'Original whole source prefix/final END was rewritten')
    check(new[:len(old)-4]+b'END\n'==old,'Exact source inverse differs')
    return dict(original_assembly=artifact(old_source),appended_assembly=artifact(new_source),
        source_prefix_and_inverse_byteexact=True,appended_UTF8_bytes=len(new)-len(old))

def verify(old_source,old_object,new_source,new_object):
    source=source_prefix(old_source,new_source)
    return dict(schema=1,verified=True,scope='unchanged_native_source_and_complete_old_COFF_prefix_only',
        producer=artifact(__file__),COFF_reader=artifact(O.__file__),**source,
        machine_prefix=protected_prefix(old_object,new_object),
        guest_executed=False,game_started=False,new_complete_canonical_equivalence_not_proved_here=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('original-source','original-object','source','object','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();check(args.output.resolve().is_relative_to(ROOT/'.boom') and not args.output.exists(),'Fresh project prefix receipt required')
    result=verify(args.original_source,args.original_object,args.source,args.object)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(artifact(args.output)))

if __name__=='__main__':main()
