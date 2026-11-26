"""Accept only the complete one-argument-per-line LINK responses we generate."""
from pathlib import Path
import re


PREFIXES = {
    'diagnostic': ('/NOLOGO', '/DLL', '/NOENTRY', '/MACHINE:X64', '/DYNAMICBASE', '/NXCOMPAT', '/BREPRO'),
    'native': ('/NOLOGO', '/MACHINE:X64', '/SUBSYSTEM:CONSOLE', '/ENTRY:boom_process_entry',
               '/NODEFAULTLIB', '/DYNAMICBASE', '/NXCOMPAT', '/HIGHENTROPYVA', '/BREPRO', '/STACK:8388608'),
}


def check(value, message):
    if not value:
        raise ValueError(message)


def path_text(value):
    path = Path(value)
    text = str(path)
    check(path.is_absolute() and not any(ord(c) < 32 or c == '"' for c in text),
          'Canonical LINK response requires absolute paths without quotes or control characters')
    return text


def sdk_libraries(*, winsock=False):
    """Allow the installed SDK pairs the PowerShell producer can select."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
        root = Path(winreg.QueryValueEx(key, 'KitsRoot10')[0]).resolve()/'Lib'
    result = []
    for version in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not version.is_dir() or not re.fullmatch(r'\d+(?:\.\d+)+', version.name):
            continue
        pair = [version/'um/x64/synchronization.lib', version/'um/x64/kernel32.lib']
        if winsock:
            pair.append(version/'um/x64/ws2_32.lib')
        if all(path.is_file() for path in pair):
            result.append(pair)
    check(result, 'Canonical LINK response needs an installed Windows SDK library pair')
    return result


def diagnostic_libraries(runtime_dll, *, winsock=False):
    runtime = Path(runtime_dll).resolve().with_suffix('.lib')
    check(runtime.is_file(), 'Canonical LINK response runtime import library is missing')
    return [[runtime, *pair] for pair in sdk_libraries(winsock=winsock)]


def native_libraries(inputs, runtime_dll, *, winsock=False):
    libraries = [Path(record['path']) for record in inputs if Path(record['path']).suffix.lower() == '.lib']
    check(libraries in diagnostic_libraries(runtime_dll,winsock=winsock),
          'Native LINK libraries differ from the sealed runtime and installed Windows SDK pair')
    return libraries


def same_argument(actual, expected):
    if actual==expected:
        return True
    if expected.startswith('"') and actual.casefold()==expected.casefold():
        try:
            return Path(actual[1:-1]).samefile(Path(expected[1:-1]))
        except OSError:
            pass
    return False


def verify(response, *, profile, output, objects, library_choices, exports):
    """Match every argument; no LINK tokenization or unrecognized input is trusted."""
    check(profile in PREFIXES, 'Unknown canonical LINK response profile')
    object_paths = [path_text(path) for path in objects]
    check(all(Path(path).suffix.lower() == '.obj' for path in object_paths) and
          len(set(map(lambda p: str(Path(p).resolve()).casefold(), object_paths))) == len(object_paths),
          'Canonical LINK response has duplicate or invalid expected COFF objects')
    symbols = sorted(set(exports))
    check(all(re.fullmatch(r'boom_\w+', symbol, flags=re.ASCII) for symbol in symbols),
          'Canonical LINK response contains an unsupported export name')
    prefix = [*PREFIXES[profile], '/OUT:"'+path_text(output)+'"']
    quoted_objects = ['"'+path+'"' for path in object_paths]
    tail = ['/EXPORT:'+symbol for symbol in symbols]
    raw = Path(response).read_bytes()
    text = raw.decode('utf-8')
    # Producers use LF or CRLF and one argument per line. Do not normalize any
    # other whitespace, BOM, quoting, option, or nested response-file syntax.
    normalized = text.replace('\r\n', '\n')
    check('\r' not in normalized and normalized.endswith('\n'),
          'Canonical LINK response has unsupported line endings')
    actual = normalized[:-1].split('\n')
    for choice in library_choices:
        libraries = [path_text(path) for path in choice]
        check(all(Path(path).suffix.lower() == '.lib' for path in libraries),
              'Canonical LINK response has an invalid expected library')
        expected = prefix+quoted_objects+['"'+path+'"' for path in libraries]
        actual_tail=actual[len(expected):]
        # PowerShell's diagnostic producer sorts exports using its culture;
        # Python's native producer uses ordinal order. All diagnostic tail
        # arguments must still be exact source exports, each present once.
        exports_match=(actual_tail==tail if profile=='native' else
                       len(actual_tail)==len(tail) and set(actual_tail)==set(tail))
        # A sealed path may acquire the installed file's case during resolve
        # (kernel32.lib is shipped as kernel32.Lib). Windows file arguments
        # retain their exact quoting and spelling apart from filesystem case.
        if len(actual)==len(expected)+len(tail) and exports_match and all(same_argument(a,e) for a,e in zip(actual,expected)):
            return dict(profile=profile, objects=object_paths, libraries=libraries, exports=symbols,
                        complete_argument_sequence_verified=True)
    raise ValueError('Canonical LINK response differs: options, output, sealed COFF parts or their order, libraries, or exports')


def winsock_import_tokens(library):
    """Resolve only the five source APIs from the sealed SDK's short import objects."""
    import struct
    raw=Path(library).read_bytes();check(raw.startswith(b'!<arch>\n'),'Expected the selected SDK import library archive')
    required={'WSAStartup','WSACleanup','WSAGetLastError','socket','closesocket'}
    found={};at=8
    while at<len(raw):
        check(at+60<=len(raw) and raw[at+58:at+60]==b'`\n','Malformed SDK archive member header')
        size_text=raw[at+48:at+58].strip()
        check(size_text and size_text.isdigit(),'Invalid SDK import member size')
        size=int(size_text);begin=at+60;end=begin+size
        check(end<=len(raw),'Truncated SDK import member')
        member=raw[begin:end]
        if len(member)>=20 and member[:4]==b'\0\0\xff\xff':
            _,_,version,machine,_,amount,ordinal,flags=struct.unpack_from('<HHHHIIHH',member)
            if version==0:
                check(20+amount<=len(member),'Truncated SDK short import payload')
                names=member[20:20+amount].split(b'\0')
                check(len(names)>=3 and names[-1]==b'','Invalid SDK short import names')
                api=names[0].decode('ascii')
                if api in required:
                    kind,name_kind=flags&3,(flags>>2)&7
                    check(api not in found and machine==0x8664 and kind==0 and name_kind in (0,1) and flags>>5==0 and
                          names[1].decode('ascii').lower()=='ws2_32.dll','The selected SDK has an ambiguous/foreign Winsock import')
                    check(name_kind!=0 or ordinal>0,'The selected SDK has an invalid Winsock ordinal')
                    found[api]='#'+str(ordinal) if name_kind==0 else api
        at=end
        if size&1:
            check(at<len(raw) and raw[at:at+1]==b'\n','Invalid SDK archive member alignment')
            at+=1
    check(set(found)==required and len(set(found.values()))==len(required),
          'The selected SDK does not supply the five exact distinct source Winsock APIs')
    return dict(sorted(found.items()))
