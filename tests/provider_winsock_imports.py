"""Actual SDK import dependencies; no network API is executed by these fixtures."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('source_Winsock_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


LINK=module('canonical-link-response');PE=module('vm-entry-source');COFF=module('verify-batch-assembly')
APIS={'WSAStartup','WSACleanup','WSAGetLastError','socket','closesocket'}
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))


class RealWinsockImportDependency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name!='nt' or not ML64.is_file():raise unittest.SkipTest('Real Windows ml64/link and SDK required')
        cls.output=ROOT/'.boom/provider-Winsock-tests'/uuid4().hex;cls.output.mkdir(parents=True)
        source=cls.output/'runtime-fixture.asm';obj=source.with_suffix('.obj');runtime=source.with_suffix('.dll')
        source.write_text('option casemap:none\n.code\nPUBLIC boom_runtime_import_fixture\n'
            'boom_runtime_import_fixture PROC\n mov eax,42\n ret\nboom_runtime_import_fixture ENDP\nEND\n')
        cls.run_tool([str(ML64),'/nologo','/c','/Fo'+str(obj),str(source)],'runtime-assembler.log',0)
        cls.run_tool([str(ML64.with_name('link.exe')),'/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64',
            '/EXPORT:boom_runtime_import_fixture','/OUT:'+str(runtime),str(obj)],'runtime-link.log',0)
        cls.choices=LINK.diagnostic_libraries(runtime,winsock=True);cls.legacy=LINK.diagnostic_libraries(runtime);cls.libs=cls.choices[0]
        cls.asm=cls.output/'probe.asm';cls.obj=cls.asm.with_suffix('.obj');cls.dll=cls.asm.with_suffix('.dll')
        text='option casemap:none\n'+''.join('EXTERN '+n+':PROC\n' for n in sorted(APIS))
        text+='.code\nPUBLIC boom_winsock_import_probe\nboom_winsock_import_probe PROC\n'
        text+=''.join(' mov rax,OFFSET '+n+'\n' for n in sorted(APIS))
        text+=' xor eax,eax\n ret\nboom_winsock_import_probe ENDP\nEND\n';cls.asm.write_text(text)
        cls.run_tool([str(ML64),'/nologo','/c','/Fo'+str(cls.obj),str(cls.asm)],'probe-assembler.log',0)
        prefix=[*LINK.PREFIXES['diagnostic'],'/OUT:"'+str(cls.dll)+'"','"'+str(cls.obj)+'"']
        tail=['/EXPORT:boom_winsock_import_probe'];cls.rsp=cls.output/'link.rsp'
        cls.rsp.write_text('\n'.join(prefix+['"'+str(p)+'"' for p in cls.libs[:-1]]+tail)+'\n')
        cls.without=cls.run_tool([str(ML64.with_name('link.exe')),'@'+str(cls.rsp)],'without-ws2.log')
        cls.rsp.write_text('\n'.join(prefix+['"'+str(p)+'"' for p in cls.libs]+tail)+'\n')
        cls.with_winsock=cls.run_tool([str(ML64.with_name('link.exe')),'@'+str(cls.rsp)],'with-ws2.log',0)

    @classmethod
    def run_tool(cls,arguments,log,expected=None):
        with (cls.output/log).open('wb') as stream:code=subprocess.run(arguments,stdout=stream,stderr=stream).returncode
        if expected is not None and code!=expected:raise RuntimeError('Real SDK fixture failed: '+str(cls.output/log))
        return code

    def test_legacy_libraries_cannot_resolve_the_five_actual_COFF_imports(self):
        self.assertNotEqual(self.without,0)
        self.assertEqual(COFF.coff_symbols(self.obj,APIS),({'boom_winsock_import_probe'},APIS))

    def test_actual_image_imports_exactly_the_five_source_APIs(self):
        self.assertEqual(self.with_winsock,0);parsed=PE.pe(self.dll);tokens=LINK.winsock_import_tokens(self.libs[-1])
        self.assertEqual(set(tokens),APIS);self.assertEqual(set(parsed['imports']),{'ws2_32.dll'})
        self.assertEqual(sorted(parsed['imports']['ws2_32.dll']),sorted(tokens.values()))

    def test_fourth_library_requires_the_explicit_canonical_consumer_policy(self):
        proof=LINK.verify(self.rsp,profile='diagnostic',output=self.dll,objects=[self.obj],library_choices=self.choices,exports=['boom_winsock_import_probe'])
        self.assertEqual(len(proof['libraries']),4)
        with self.assertRaisesRegex(ValueError,'Canonical LINK response differs'):
            LINK.verify(self.rsp,profile='diagnostic',output=self.dll,objects=[self.obj],library_choices=self.legacy,exports=['boom_winsock_import_probe'])

    def test_import_metadata_cannot_redirect_the_source_API_to_a_foreign_DLL(self):
        raw=bytearray(self.libs[-1].read_bytes());at=bytes(raw).lower().index(b'wsastartup\0ws2_32.dll\0')+len(b'WSAStartup\0')
        raw[at:at+10]=b'evil32.dll';path=self.output/'wrong-dll.lib';path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'foreign Winsock import'):LINK.winsock_import_tokens(path)

    def test_distinct_source_APIs_cannot_alias_one_import_ordinal(self):
        tokens=LINK.winsock_import_tokens(self.libs[-1]);self.assertTrue(tokens['WSACleanup'].startswith('#'))
        raw=bytearray(self.libs[-1].read_bytes());at=bytes(raw).lower().index(b'wsastartup\0ws2_32.dll\0')
        self.assertEqual(raw[at-20:at-16],b'\0\0\xff\xff');struct.pack_into('<H',raw,at-4,int(tokens['WSACleanup'][1:]))
        path=self.output/'duplicate-ordinal.lib';path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'five exact distinct'):LINK.winsock_import_tokens(path)


if __name__=='__main__':unittest.main()
