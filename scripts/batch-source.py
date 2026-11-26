"""Index generated MASM procedures once; preserve the original source bytes.

This is an offline selection helper, never part of the guest runtime. Cached
units have a bounded text budget so broad dependency scans can evict old units.
"""
from collections import OrderedDict
from pathlib import Path
import re

MARKERS=re.compile(r'(?m)^(boom_[A-Za-z0-9_]+) (PROC\b[^\n]*|ENDP)\n')
BYTE_MARKERS=re.compile(rb'(?m)^(boom_[A-Za-z0-9_]+) (PROC\b[^\r\n]*|ENDP)\r?\n')
CLASS_DATA=re.compile(rb'(?m)^boom_class(\d+) DWORD 0434C4153h,2,0,0\r?\n QWORD [^\r\n]+\r?\n DWORD \1,0\r?\n QWORD 0,0,0,OFFSET boom_batch_class_failure_root\1\r?\n')
HANDLER_DATA=re.compile(rb'(?m)^\.const\r?\nALIGN 8\r?\nboom_handlers(\d+) DWORD 045584348h, 1, (\d+), 0\r?\n    QWORD OFFSET boom_handler_rows\1, OFFSET boom_runtime_type_map, OFFSET boom_t\d+\r?\nboom_handler_rows\1 LABEL BYTE\r?\n((?:    DWORD \d+, \d+, \d+, 0\r?\n    QWORD (?:0|OFFSET boom_t\d+)\r?\n)+)(?=(?:\r?\n)*\.(?:code|const|data\??)\r?\n)')
CONSTANT_DATA=re.compile(rb'(?m)^\.const\r?\nALIGN 8\r?\n(?:PUBLIC (boom_batch_vtable\d+)\r?\n|(boom_batch_vconstraints_[A-Za-z0-9_]+) QWORD|(boom_batch_call_\d+_\d+_186)_rows LABEL BYTE)')


def procedure_spans(source):
    result={};opened=None
    binary=isinstance(source,bytes)
    for match in (BYTE_MARKERS if binary else MARKERS).finditer(source):
        name,kind=match[1],match[2]
        if binary:name,kind=name.decode('ascii'),kind.decode('utf-8')
        if kind.startswith('PROC'):
            if opened is not None or name in result:raise ValueError('Duplicate/nested generated procedure: '+name)
            opened=(name,match.start())
        else:
            if opened is None or opened[0]!=name:raise ValueError('Mismatched generated procedure end: '+name)
            result[name]=(opened[1],match.end());opened=None
    if opened is not None:raise ValueError('Unterminated generated procedure: '+opened[0])
    return result


class Sources:
    def __init__(self,budget=512*1024*1024):
        if budget<=0:raise ValueError('Source cache budget must be positive')
        self.budget=budget;self.used=0;self.entries=OrderedDict();self.locations={};self.metadata={};self.reads=0;self.indexes=0;self.slices=0;self.metadata_indexes=0

    def _entry(self,path):
        path=str(Path(path))
        stamp=self._stamp(path)
        if path in self.entries:
            entry=self.entries.pop(path)
            if entry[1]==stamp:self.entries[path]=entry;return entry
            self.used-=len(entry[0])
        source=Path(path).read_text(encoding='utf-8');entry=[source,stamp]
        while self.entries and self.used+len(source)>self.budget:
            _,old=self.entries.popitem(last=False);self.used-=len(old[0])
        self.entries[path]=entry;self.used+=len(source);self.reads+=1
        return entry

    def text(self,path):return self._entry(path)[0]

    @staticmethod
    def _stamp(path):
        stat=Path(path).stat();return stat.st_size,stat.st_mtime_ns

    def function(self,path,symbol):
        path=str(Path(path));stamp=self._stamp(path)
        if path not in self.locations or self.locations[path][0]!=stamp:
            source=Path(path).read_bytes();spans=procedure_spans(source)
            if self._stamp(path)!=stamp:raise ValueError('Generated source changed while indexing')
            self.locations[path]=(stamp,spans);self.reads+=1;self.indexes+=1
        spans=self.locations[path][1]
        if symbol not in spans:raise ValueError('Original generated function is missing: '+symbol)
        start,end=spans[symbol]
        with Path(path).open('rb') as stream:stream.seek(start);body=stream.read(end-start)
        if len(body)!=end-start or self._stamp(path)!=stamp:raise ValueError('Generated source changed while selecting')
        self.slices+=1
        return body.decode('utf-8').replace('\r\n','\n').replace('\r','\n')

    def _metadata(self,path):
        path=str(Path(path));stamp=self._stamp(path)
        if path not in self.metadata or self.metadata[path][0]!=stamp:
            source=Path(path).read_bytes();classes={};constants={}
            for match in CLASS_DATA.finditer(source):
                id_=int(match[1])
                if id_ in classes:raise ValueError('Duplicate source class descriptor')
                classes[id_]=(match.start(),match.end())
            for match in CONSTANT_DATA.finditer(source):
                name=(match[1] or match[2] or match[3]).decode('ascii')
                if name in constants:raise ValueError('Duplicate source dispatch data')
                constants[name]=match.start()
            if self._stamp(path)!=stamp:raise ValueError('Generated metadata changed while indexing')
            handlers={}
            for match in HANDLER_DATA.finditer(source):
                id_=int(match[1])
                if id_ in handlers or int(match[2])!=match[3].count(b'    DWORD '):raise ValueError('Duplicate/invalid source exception handler data')
                handlers[id_]=(match.start(),match.end())
            self.metadata[path]=(stamp,classes,constants,handlers);self.reads+=1;self.metadata_indexes+=1
        return self.metadata[path]

    def handler_table(self,path,id_):
        path=str(Path(path));metadata=self._metadata(path)
        if id_ not in metadata[3]:raise ValueError('Missing source exception handler data: '+str(id_))
        begin,end=metadata[3][id_]
        return self._slice(path,metadata[0],begin,end)

    def _slice(self,path,stamp,begin,end):
        with Path(path).open('rb') as stream:stream.seek(begin);body=stream.read(end-begin)
        if len(body)!=end-begin or self._stamp(path)!=stamp:raise ValueError('Generated source changed while selecting data')
        self.slices+=1
        return body.decode('utf-8').replace('\r\n','\n').replace('\r','\n')

    def class_descriptor(self,path,id_):
        stamp,classes,_,_=self._metadata(path)
        if id_ not in classes:raise ValueError('Original source class descriptor is missing: '+str(id_))
        start,end=classes[id_]
        with Path(path).open('rb') as stream:stream.seek(start);body=stream.read(end-start)
        if len(body)!=end-start or self._stamp(path)!=stamp:raise ValueError('Generated descriptor changed while selecting')
        return body.decode('utf-8').replace('\r\n','\n').replace('\r','\n')

    def fragment(self,path,symbol,expected):
        stamp,_,constants,_=self._metadata(path)
        if symbol not in constants:raise ValueError('Original dispatch data is missing: '+symbol)
        if not expected or not expected.endswith('\n'):raise ValueError('Expected dispatch data has no complete line boundary')
        with Path(path).open('rb') as stream:
            stream.seek(constants[symbol]);body=b''.join(stream.readline() for _ in range(expected.count('\n')))
        if self._stamp(path)!=stamp:raise ValueError('Generated dispatch data changed while selecting')
        body=body.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
        if body!=expected:raise ValueError('Selected dispatch data differs from generated source')
        return body
