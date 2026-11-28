"""Pure source audit/projection of UFMP2 namespace dimensions and consumers.

derive reads the actual 128-byte pool declaration. audit identifies local
namespace EQU values, direct pool guards, and register boundary comparisons.
project changes only stale EQU integer spans and proves a complete source
inverse. This is source consistency, not CFG, machine, or runtime validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

POOL = 'boom_java_unsafe_field_pool'
DIMENSIONS = {'TYPES': ('types', 8), 'FIELDS': ('fields', 12),
              'NAME_UNITS': ('name_units', 88), 'PAGES': ('pages', 92)}
NUMBER = rb'(?:0[xX][0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*[hH]|\+?[0-9]+)'
CONST = rb'[A-Za-z_][A-Za-z_0-9]*_UFMP_(?:NAME_UNITS|TYPES|FIELDS|PAGES)'
EQU = re.compile(rb'^\s*(?P<name>'+CONST+rb')\s+EQU\s+(?P<value>.*?)\s*$', re.I)
TOKEN = re.compile(rb'(?<![A-Za-z_0-9])('+CONST+rb')(?![A-Za-z_0-9])', re.I)
MEMORY = re.compile(rb'^DWORD\s+PTR\s*\[\s*(?P<register>[A-Za-z0-9]+)\s*\+\s*(?P<offset>'+NUMBER+rb')\s*\]$', re.I)


def check(value, message):
    if not value:
        raise ValueError(message)


def installed_root():
    for path in Path(__file__).resolve().parents:
        cargo = path / 'Cargo.toml'
        if (cargo.is_file() and (path / 'scripts/constructor-provider-source.py').is_file()
                and (path / 'native/runtime/java_classes.asm').is_file()):
            with cargo.open('rb') as stream:
                if tomllib.load(stream).get('package', {}).get('name') == 'boom-minecraft':
                    return path
    raise ValueError('Installed project source/tool root not found')


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=digest))


def source_bytes(value):
    check(isinstance(value, (str, bytes)), 'Explicit UTF8 source text or bytes required')
    raw = value.encode('utf-8') if isinstance(value, str) else value
    raw.decode('utf-8')
    return raw


def integer(value, bits=32):
    check(re.fullmatch(NUMBER, value) is not None, 'Unsupported scalar integer expression: '+repr(value))
    text = value.decode('ascii')
    number = int(text[:-1], 16) if text[-1:].lower() == 'h' else int(text, 16) if text.lower().startswith('0x') else int(text, 10)
    check(bits in (32,64) and 0 <= number < 1 << bits, 'UFMP scalar literal is out of range')
    return number


def code_line(raw):
    """Ignore comments and quoted strings without changing byte positions."""
    result = bytearray(raw.rstrip(b'\r\n'))
    quote = None
    for index, value in enumerate(result):
        if quote is not None:
            result[index] = 32
            if value == quote:
                quote = None
        elif value in (34, 39):
            quote = value
            result[index] = 32
        elif value == 59:
            del result[index:]
            break
    return bytes(result)


def lines(raw):
    at = 0
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        yield number, at, code_line(line), line
        at += len(line)


def derive(pool_source, *, pool_symbol=POOL):
    """Extract ABI2 type/field/name-unit/page values from an explicit pool."""
    raw = source_bytes(pool_source)
    check(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', pool_symbol), 'Invalid explicit UFMP pool symbol')
    definition = re.compile(rb'^\s*(?P<label>'+re.escape(pool_symbol.encode())+rb')\s+DWORD\s+(?P<values>.+)$', re.I)
    directive = re.compile(rb'^\s*(?P<kind>DWORD|QWORD)\s+(?P<values>.+)$', re.I)
    pointer = re.compile(rb'OFFSET\s+[A-Za-z_][A-Za-z_0-9]*$', re.I)
    records = {}
    check(sum(bool(match and match['label'].decode()==pool_symbol)
              for _,_,code,_ in lines(raw) for match in [definition.fullmatch(code)]) == 1,
          'Exactly one explicit UFMP pool declaration is required')
    offset = 0
    start = end = None
    for number, at, code, line in lines(raw):
        if start is None:
            match = definition.fullmatch(code)
            if not match or match['label'].decode() != pool_symbol:
                continue
            start = at
            kind = 'DWORD'
        else:
            if not code.strip():
                continue
            match = directive.fullmatch(code)
            check(match is not None, 'Unsupported/incomplete scalar UFMP128 declaration at line '+str(number))
            kind = match['kind'].decode().upper()
        width = 4 if kind == 'DWORD' else 8
        values = match['values']
        for token_match in re.finditer(rb'[^,]+', values):
            token = token_match.group().strip()
            check(token and offset+width <= 128, 'UFMP pool declaration exceeds its ABI128 shape')
            value = None if width == 8 and pointer.fullmatch(token) else integer(token,bits=width*8)
            position = at+match.start('values')+token_match.start()+len(token_match.group())-len(token_match.group().lstrip())
            records[offset] = dict(value=value, width=width, line=number, begin=position,
                                   end=position+len(token), literal=token.decode('ascii'))
            offset += width
        if offset == 128:
            end = at+len(line)
            break
    check(start is not None and offset == 128, 'One complete UFMP128 pool declaration is required')
    check(records[0]['value'] == 0x55464d50 and records[4]['value'] == 2 and records[108]['value'] == 64,
          'Explicit source is not the supported UFMP2 Field64 pool ABI')
    dimensions = {}
    declarations = {}
    for suffix, (name, position) in DIMENSIONS.items():
        record = records[position]
        check(record['width'] == 4 and type(record['value']) is int and 0 < record['value'] < 1 << 31,
              'Unsupported namespace dimension: '+suffix)
        dimensions[name] = record['value']
        declarations[name] = record
    check(dimensions['pages'] == (dimensions['fields']+1023)//1024, 'UFMP source field/page dimensions disagree')
    return dict(schema=1, pool_symbol=pool_symbol, ABI=2, pool_bytes=128, record_bytes=64,
        dimensions=dimensions, declarations=declarations, source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw), pool_source_span=dict(begin=start,end=end),
        complete_pool_tables_or_machine_verified=False)


def register(value):
    text = value.decode('ascii').lower()
    aliases = {'eax':'rax','ax':'rax','al':'rax','ah':'rax','ebx':'rbx','bx':'rbx','bl':'rbx','bh':'rbx',
        'ecx':'rcx','cx':'rcx','cl':'rcx','ch':'rcx','edx':'rdx','dx':'rdx','dl':'rdx','dh':'rdx',
        'esi':'rsi','si':'rsi','sil':'rsi','edi':'rdi','di':'rdi','dil':'rdi',
        'ebp':'rbp','bp':'rbp','bpl':'rbp','esp':'rsp','sp':'rsp','spl':'rsp'}
    if text in aliases:
        return aliases[text]
    if re.fullmatch(r'r(?:[8-9]|1[0-5])(?:d|w|b)?', text):
        return re.sub('[dwb]$', '', text)
    return text if text in ('rax','rbx','rcx','rdx','rsi','rdi','rsp','rbp') else None


def consumer_audit(consumer_source, namespace):
    raw = source_bytes(consumer_source)
    source_lines = list(lines(raw))
    definitions = {}
    groups = {}
    issues = []
    for number, at, code, _ in source_lines:
        match = EQU.fullmatch(code)
        if not match:
            continue
        name = match['name'].decode('ascii')
        check(name not in definitions, 'Duplicate local namespace constant: '+name)
        suffix = next(key for key in DIMENSIONS if name.upper().endswith('_UFMP_'+key))
        dimension, position = DIMENSIONS[suffix]
        prefix = name[:-(len(suffix))]
        try:
            value = integer(match['value'])
        except ValueError:
            value = None
            issues.append(dict(kind='unsupported_EQU_expression',constant=name,line=number))
        definitions[name] = dict(constant=name,dimension=dimension,expected=namespace['dimensions'][dimension],
            value=value,definition_line=number,begin=at+match.start('value'),end=at+match.end('value'),
            literal=match['value'].decode('ascii'),pool_offset=position,guards=[],boundary_compares=[],uses=[])
        group = groups.setdefault(prefix,{})
        check(dimension not in group, 'Duplicate local namespace dimension')
        group[dimension] = name
    if not definitions:
        issues.append(dict(kind='no_namespace_EQU_definitions'))
    required = {name for name,_ in DIMENSIONS.values()}
    for prefix, dimensions in groups.items():
        for name in sorted(required-set(dimensions)):
            issues.append(dict(kind='missing_namespace_dimension',prefix=prefix,dimension=name))
    pool_registers = {}
    instructions = re.compile(rb'^\s*([A-Za-z][A-Za-z0-9]*)\s*(.*?)\s*$')
    for index, (number, _, code, _) in enumerate(source_lines):
        if EQU.fullmatch(code):
            continue
        if re.match(rb'^\s*\w+\s+(?:PROC|ENDP)\b',code,re.I):
            pool_registers = {}
            continue
        found = [match.group(1).decode('ascii') for match in TOKEN.finditer(code)]
        compare = re.fullmatch(rb'\s*cmp\s+(.+?)\s*,\s*('+CONST+rb')\s*',code,re.I)
        for name in found:
            if name not in definitions:
                issues.append(dict(kind='namespace_reference_without_exact_local_definition',constant=name,line=number))
                continue
            row = definitions[name]
            row['uses'].append(number)
            if not compare or compare.group(2).decode('ascii') != name or len(found) != 1:
                issues.append(dict(kind='unrecognized_namespace_reference',constant=name,line=number))
                continue
            operand = compare.group(1).strip()
            memory = MEMORY.fullmatch(operand)
            if memory:
                base = register(memory['register'])
                position = integer(memory['offset'])
                if position != row['pool_offset']:
                    issues.append(dict(kind='namespace_pool_guard_offset_mismatch',constant=name,line=number,offset=position))
                elif base not in pool_registers:
                    issues.append(dict(kind='namespace_pool_base_without_direct_source_witness',constant=name,line=number,register=base))
                else:
                    row['guards'].append(dict(line=number,register=base,offset=position,
                        pool_base_source_witness=pool_registers[base],control_flow_dominance_proven=False))
            elif register(operand) is not None:
                next_code = next((code for _,_,code,_ in source_lines[index+1:] if code.strip()),b'')
                branch = re.match(rb'^\s*(j[a-z]+)\b',next_code,re.I)
                row['boundary_compares'].append(dict(line=number,operand=operand.decode('ascii'),
                    conditional_branch=branch.group(1).decode('ascii') if branch else None,
                    operand_value_semantics_verified=False))
            else:
                issues.append(dict(kind='unrecognized_namespace_compare_operand',constant=name,line=number))
        instruction = instructions.fullmatch(code)
        if not instruction:
            continue
        opcode = instruction.group(1).lower()
        operands = [part.strip() for part in instruction.group(2).split(b',')]
        if opcode == b'call':
            for name in ('rax','rcx','rdx','r8','r9','r10','r11'):
                pool_registers.pop(name,None)
        elif opcode in (b'mov',b'lea',b'movzx',b'movsx',b'movsxd',b'add',b'sub',b'and',b'or',b'xor',
                        b'not',b'neg',b'inc',b'dec',b'shl',b'shr',b'sar',b'rol',b'ror',b'pop',b'xchg',b'imul') and operands:
            target = register(operands[0])
            if target is not None:
                inherited = pool_registers.get(register(operands[1])) if len(operands)==2 else None
                pool_registers.pop(target,None)
                symbol = namespace['pool_symbol'].encode('ascii')
                exact_lea = opcode == b'lea' and len(operands)==2 and operands[1] in (symbol,b'['+symbol+b']')
                exact_mov = opcode == b'mov' and len(operands)==2 and operands[1]==b'OFFSET '+symbol
                if exact_lea or exact_mov:
                    pool_registers[target] = dict(line=number,pool_symbol=namespace['pool_symbol'],load=opcode.decode())
                elif opcode == b'mov' and inherited:
                    pool_registers[target] = dict(inherited,copied_at_line=number)
                if opcode == b'xchg' and len(operands)==2:
                    pool_registers.pop(register(operands[1]),None)
        elif opcode == b'ret':
            pool_registers = {}
    for row in definitions.values():
        if not row['guards']:
            issues.append(dict(kind='namespace_dimension_without_direct_pool_guard',constant=row['constant']))
        row['matches_pool'] = row['value'] == row['expected']
    return dict(source_sha256=hashlib.sha256(raw).hexdigest(),source_bytes=len(raw),definitions=list(definitions.values()),
        source_pattern_supported=not issues,issues=issues,stale_constants=[r['constant'] for r in definitions.values() if not r['matches_pool']],
        namespace_consistent=not issues and all(row['matches_pool'] for row in definitions.values()))


def audit(pool_source, consumers, *, pool_symbol=POOL):
    """Audit explicit source strings; no files, machine image or runtime are read."""
    check(isinstance(consumers,dict) and consumers, 'Explicit nonempty role-to-source mapping required')
    namespace = derive(pool_source,pool_symbol=pool_symbol)
    rows = {role:consumer_audit(text,namespace) for role,text in consumers.items()}
    return dict(schema=1,scope='UFMP2 four-dimensional source consistency only',namespace=namespace,consumers=rows,
        namespace_consistent=all(row['namespace_consistent'] for row in rows.values()),
        source_pattern_supported=all(row['source_pattern_supported'] for row in rows.values()),
        stale_constant_count=sum(len(row['stale_constants']) for row in rows.values()),
        native_or_Java_execution_or_machine_verification=False)


def formatted_integer(value, previous):
    if previous.lower().startswith('0x'):
        return previous[:2]+format(value,'X' if previous[1]=='X' else 'x')
    if previous[-1:].lower() == 'h':
        digits = format(value,'X' if any(c in 'ABCDEF' for c in previous) else 'x').rjust(len(previous)-1,'0')
        if digits[0].isalpha():
            digits = '0'+digits
        return digits+previous[-1]
    return ('+' if previous.startswith('+') else '')+str(value)


def project(pool_source, consumers, *, pool_symbol=POOL):
    """Return source text and exact-inverse plans; edit only stale EQU literals."""
    before = audit(pool_source,consumers,pool_symbol=pool_symbol)
    check(before['source_pattern_supported'], 'Unsupported consumer source shape; inspect audit issues before projection')
    results = {}
    plans = []
    for role, text in consumers.items():
        raw = source_bytes(text)
        edits = []
        output = bytearray()
        at = 0
        for row in sorted(before['consumers'][role]['definitions'],key=lambda item:item['begin']):
            if row['matches_pool']:
                continue
            start,end = row['begin'],row['end']
            old = raw[start:end]
            new = formatted_integer(row['expected'],row['literal']).encode('ascii')
            check(start>=at and old.decode('ascii')==row['literal'], 'Exact stale EQU source span differs')
            output.extend(raw[at:start])
            after_start = len(output)
            output.extend(new)
            edits.append(dict(constant=row['constant'],dimension=row['dimension'],line=row['definition_line'],
                before_begin=start,before_end=end,after_begin=after_start,after_end=len(output),
                before=old.decode(),after=new.decode(),old_value=row['value'],new_value=row['expected']))
            at = end
        output.extend(raw[at:])
        result = bytes(output)
        inverse = result
        for edit in reversed(edits):
            start,end = edit['after_begin'],edit['after_end']
            check(inverse[start:end].decode('ascii')==edit['after'], 'Exact projected EQU inverse span differs')
            inverse = inverse[:start]+edit['before'].encode('ascii')+inverse[end:]
        check(inverse==raw, 'Complete consumer source inverse differs')
        results[role] = result.decode('utf-8')
        plans.append(dict(role=role,source_before_sha256=hashlib.sha256(raw).hexdigest(),
            source_after_sha256=hashlib.sha256(result).hexdigest(),edits=edits,
            exact_complete_source_inverse=True,only_namespace_EQU_literal_spans_changed=True))
    after = audit(pool_source,results,pool_symbol=pool_symbol)
    check(after['namespace_consistent'], 'Projected consumer dimensions or guards still disagree with the explicit pool')
    return results,dict(schema=1,source_only=True,before=before,after=after,plans=plans,
        exact_complete_source_inverse=True,native_or_Java_execution_or_machine_verification=False)


def output_target(value):
    output,root = Path(value).resolve(),installed_root()
    check(any(output.is_relative_to(root/name) for name in ('.boom','target','dist')),
          'Generated source output must stay in the installed project .boom, target or dist')
    check(not output.exists(), 'Generated source output must be create-new')
    return output


def main(args):
    output = output_target(args.output)  # Refuse output before reading inputs.
    paths = {}
    for value in args.consumer:
        role,separator,path = value.partition('=')
        check(separator and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',role) and role not in paths,
              'Each consumer must be a unique safe ROLE=PATH')
        paths[role] = Path(path)
    pool_text = Path(args.pool).read_bytes().decode('utf-8')
    consumers = {role:path.read_bytes().decode('utf-8') for role,path in paths.items()}
    report = audit(pool_text,consumers,pool_symbol=args.pool_symbol)
    projected = None
    if args.mode == 'project':
        projected,report = project(pool_text,consumers,pool_symbol=args.pool_symbol)
    report.update(producer=artifact(__file__),pool_source=artifact(args.pool),
                  consumer_sources={role:artifact(path) for role,path in paths.items()})
    output.mkdir(parents=True)
    if projected is not None:
        report['projected_sources'] = {}
        for role,text in projected.items():
            path = output/(role+'.asm')
            with path.open('xb') as stream:
                stream.write(text.encode('utf-8'))
            report['projected_sources'][role] = artifact(path)
    path = output/'source.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    consistent = report['after']['namespace_consistent'] if projected is not None else report['namespace_consistent']
    print(json.dumps(dict(source_report=artifact(path),namespace_consistent=consistent,source_only=True)))
    return 0 if consistent else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool',type=Path,required=True)
    parser.add_argument('--pool-symbol',default=POOL)
    parser.add_argument('--consumer',action='append',required=True,metavar='ROLE=PATH')
    parser.add_argument('--mode',choices=('audit','project'),default='audit')
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(main(parser.parse_args()))
