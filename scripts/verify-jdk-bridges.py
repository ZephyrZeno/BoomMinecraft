"""Independent raw classfile checks; no guest execution or JVM fallback."""
import hashlib
import json
import struct
import sys
from pathlib import Path

class Reader:
    def __init__(self, data): self.data, self.pos = data, 0
    def take(self, n):
        result = self.data[self.pos:self.pos+n]
        assert len(result) == n, 'Truncated classfile'
        self.pos += n
        return result
    def u1(self): return self.take(1)[0]
    def u2(self): return struct.unpack('>H', self.take(2))[0]
    def u4(self): return struct.unpack('>I', self.take(4))[0]

def parse(data):
    r = Reader(data)
    assert r.u4() == 0xcafebabe
    r.take(4)
    count = r.u2()
    names, i = {}, 1
    while i < count:
        tag = r.u1()
        if tag == 1: names[i] = r.take(r.u2()).decode('utf-8', errors='replace')
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18): r.take(4)
        elif tag in (5, 6): r.take(8); i += 1
        elif tag in (7, 8, 16, 19, 20): r.take(2)
        elif tag == 15: r.take(3)
        else: raise AssertionError('Unknown constant tag')
        i += 1
    cp = data[10:r.pos]
    access, this, parent = r.u2(), r.u2(), r.u2()
    interfaces = r.u2(); r.take(2 * interfaces)
    def attrs():
        result = []
        for _ in range(r.u2()):
            name = names[r.u2()]
            result.append((name, r.take(r.u4())))
        return result
    fields = r.u2()
    for _ in range(fields): r.take(6); attrs()
    methods = []
    for _ in range(r.u2()):
        flags, name, descriptor = r.u2(), names[r.u2()], names[r.u2()]
        methods.append((flags, name, descriptor, attrs()))
    attributes = attrs()
    assert r.pos == len(data)
    return dict(count=count, cp=cp, access=access, parent=parent, interfaces=interfaces,
                fields=fields, methods=methods, attrs=attributes)

def verify(path):
    result = []
    for record in json.loads(path.read_text(encoding='utf-8-sig')):
        original = Path(record['original_class']).read_bytes()
        generated = Path(record['generated_class']).read_bytes()
        assert hashlib.sha256(original).hexdigest() == record['original']['sha256']
        assert hashlib.sha256(generated).hexdigest() == record['generated']['sha256']
        a, b = parse(original), parse(generated)
        assert b['count'] - a['count'] in (2, 3)
        assert b['cp'].startswith(a['cp'])
        assert b['access'] == 0x31 and b['parent'] == a['parent']
        assert b['interfaces'] == b['fields'] == 0 and len(b['methods']) == 1
        method = b['methods'][0]
        name, descriptor = method[1:3]
        source_descriptor = descriptor
        if record['kind'] in ('Split', 'SplitLimit', 'SplitWithDelimiters'):
            assert descriptor.startswith('(Ljava/lang/String;')
            source_descriptor = '(' + descriptor[len('(Ljava/lang/String;'):]
        elif record['kind'] == 'ClassAsSubclass':
            assert descriptor == '(Ljava/lang/Class;Ljava/lang/Class;)Ljava/lang/Class;'
            source_descriptor = '(Ljava/lang/Class;)Ljava/lang/Class;'
        elif record['kind'] in ('ClassToString', 'ClassDescriptorString', 'ClassComponentType',
                              'ClassGetClassLoader', 'ClassGetClassLoader0'):
            assert descriptor.startswith('(Ljava/lang/Class;)')
            source_descriptor = '()' + descriptor.split(')', 1)[1]
        elif record['kind'] in ('StartsWith', 'EndsWith'):
            assert descriptor == '(Ljava/lang/String;Ljava/lang/String;)Z'
            source_descriptor = '(Ljava/lang/String;)Z'
        elif record['kind'] == 'Contains':
            assert descriptor == '(Ljava/lang/String;Ljava/lang/CharSequence;)Z'
            source_descriptor = '(Ljava/lang/CharSequence;)Z'
        elif record['kind'] == 'ReplaceFirst':
            assert descriptor == '(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;'
            source_descriptor = '(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;'
        source = [m for m in a['methods'] if m[1:3] == (name, source_descriptor)]
        assert len(source) == 1 and method[0] == 9
        assert source[0][3] == method[3], 'Code, handlers, stack maps or debug/other method attributes changed'
        assert any(n == 'Code' for n, _ in method[3])
        assert b['attrs'] == [(n, data) for n, data in a['attrs'] if n in ('BootstrapMethods', 'SourceFile')]
        result.append(dict(kind=record['kind'], generated_sha256=record['generated']['sha256'],
                           original_constant_pool_prefix_retained=True, all_method_attributes_identical=True))
    return dict(bridges=len(result), checks=result, execution_complete=False, passed=True)

if __name__ == '__main__':
    path = Path(sys.argv[1])
    print(json.dumps(verify(path), indent=2))
