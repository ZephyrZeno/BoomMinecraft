"""Source identity/I/O helpers for separate assembly providers, never guest code."""
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
_BASE_SCOPE=ContextVar('fresh_provider_base_scope',default=None)


def check(value,message):
    if not value:raise ValueError(message)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(size=Path(path).stat().st_size,sha256=h)


def artifact(path):
    path=Path(path).resolve();return dict(path=str(path),digest=digest(path))


def checked(record):
    p=Path(record['path']).resolve();check(p.is_relative_to(ART),'Provider artifact must remain in project .boom')
    actual=digest(p)
    check(all(record['digest'][k]==v for k,v in actual.items()),'Provider artifact changed: '+str(p));return p


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def base(batch,plan):
    batch,plan=Path(batch).resolve(),Path(plan).resolve()
    check(batch.is_relative_to(ART) and plan.is_relative_to(ART),'Provider base/plan must remain in project .boom')
    scope=_BASE_SCOPE.get()
    if scope is not None:
        check((batch,plan)==scope[0],'Provider verification scope belongs to another batch/plan')
        return scope[1]
    return _fresh_base(batch,plan)


def _fresh_base(batch,plan):
    s=read(batch/'summary.json');p=read(plan/'summary.json');v=read(batch/'verification.json')
    check(s['schema']==23 and v.get('verified') and v.get('frames',{}).get('verified'),'Provider requires the verified normal-frame batch ABI')
    check(s['input_fingerprint']==p['input_fingerprint'],'Provider base/source input differs')
    classes=checked(p['artifacts']['classes']);methods=checked(p['artifacts']['methods'])
    identity=dict(batch=str(batch),plan=str(plan),batch_summary=artifact(batch/'summary.json'),base_verification=artifact(batch/'verification.json'),
        source_plan=artifact(plan/'summary.json'),source_classes=artifact(classes),source_methods=artifact(methods),
        input_fingerprint=s['input_fingerprint'],ir_identity=s['ir_identity'],base_compiler_sha256=s['compiler_sha256'],
        runtime_layout_abi=s['runtime_layout_abi'],context_bytes=32,source_frame_abi=3,
        class_pool_abi=s['class_literals']['abi'],source_transform_chain='original_locked_no_transforms')
    return identity,s,[json.loads(l) for l in classes.read_text(encoding='utf-8').splitlines()]


@contextmanager
def base_scope(batch,plan):
    """Reuse a freshly checked base only inside this validation call chain.

    Every shared artifact is hashed again before the scope can return success.
    No receipt flag, persistent cache, or previous process restores this scope.
    """
    check(_BASE_SCOPE.get() is None,'Nested provider verification scopes are not supported')
    key=(Path(batch).resolve(),Path(plan).resolve());snapshot=base(*key)
    fingerprint=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    token=_BASE_SCOPE.set((key,snapshot))
    try:
        yield
    finally:
        _BASE_SCOPE.reset(token)
        check(hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()==fingerprint,'Provider verifier mutated the shared source snapshot')
        identity=snapshot[0]
        for name in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):
            record=identity[name];check(artifact(record['path'])==record,'Shared provider base changed during verification: '+name)


_PROVIDER_TOOLS=module('provider_data_tool_manifest','provider-tool-manifest.py')
TOOL_FILES=_PROVIDER_TOOLS.tool_files(ROOT)


def tools_identity():return _PROVIDER_TOOLS.tools_identity(ROOT)


def original_class(summary,source):
    catalog=checked(summary['frames']['original_system_catalog'])
    directory=(catalog.parent/'image').resolve();path=(directory/source['origin']['jar_entry']).resolve()
    check(path.is_relative_to(directory),'Provider original class path escaped system image')
    raw=path.read_bytes();check(hashlib.sha256(raw).hexdigest()==source['origin']['sha256'],'Provider original class changed')
    return raw


def write(path,value):
    path=Path(path);check(not path.exists(),'Provider evidence already exists: '+str(path))
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
