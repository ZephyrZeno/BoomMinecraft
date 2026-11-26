"""Data-driven provider tool identity candidate; no producer is switched here.

This is a declared, statically audited build-source graph, not a Python sandbox.
Runtime source contracts and input artifacts still require their own verifiers.
"""
import argparse
import ast
from collections import OrderedDict,deque
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


ROOT=Path(__file__).resolve().parents[1]
HELPER='scripts/provider-tool-manifest.py'
MANIFEST='native-config/runtime-provider-tools.json'
REGISTRY='native-config/runtime-providers.json'
LEGACY_COUNT=105
LEGACY_PATH_SHA256='e9a87cfad93b62c64784041f3eb4a3451da1bea658d0f5ba880e6c718bab5780'
SOURCE_PATTERN=re.compile(r'(?:scripts|native/(?:providers|kernels|runtime))/[A-Za-z0-9_./-]+\.(?:py|ps1|asm|inc|tpl)',re.I)
_LOADED_IMPLEMENTATION_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_AUDIT_CACHE=OrderedDict()


def check(value,message):
    if not value:raise ValueError(message)


def unique_object(pairs):
    result={}
    for key,value in pairs:
        check(key not in result,'Duplicate JSON key: '+key);result[key]=value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=unique_object)


def sha256(raw):return hashlib.sha256(raw).hexdigest()


def path_digest(paths):return sha256(json.dumps(paths,separators=(',',':')).encode())


def source_path(root,name):
    check(isinstance(name,str) and SOURCE_PATTERN.fullmatch(name) and '\\' not in name and ':' not in name,
        'Expected canonical project source path: '+str(name))
    path=PurePosixPath(name)
    check(not path.is_absolute() and all(part not in ('','.','..') for part in name.split('/')),
        'Source path traversal or alias: '+name)
    target=(root/name).resolve()
    check(target.is_relative_to(root) and target.is_file(),'Missing or escaped source file: '+name)
    return target


def file_path(root,name):
    if name in (MANIFEST,REGISTRY):
        target=(root/name).resolve();check(target.is_relative_to(root) and target.is_file(),'Missing or escaped identity JSON');return target
    return source_path(root,name)


def names(values,label):
    check(isinstance(values,list) and all(isinstance(x,str) for x in values),'Expected path list: '+label)
    check(len(values)==len({x.casefold() for x in values}),'Duplicate or case-aliased source: '+label)
    return values


def tree(root,name):return ast.parse(source_path(root,name).read_text(encoding='utf-8-sig'))


def literal_assignment(parsed,name):
    values=[node.value for node in parsed.body if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id==name for target in node.targets)]
    check(len(values)==1,'Expected one static source declaration: '+name)
    try:return ast.literal_eval(values[0])
    except (ValueError,TypeError):raise ValueError('Nonliteral source declaration: '+name) from None


def module_target(call):
    values=[n.value for n in call.args if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.endswith('.py')]
    check(len(values)<=1,'Ambiguous source module target')
    return 'scripts/'+values[0] if values else None


def loader_targets(parsed,data_bound=None):
    """Recognize the bounded local importlib factories used by current sources."""
    factories={};direct={}
    parents={child:node for node in ast.walk(parsed) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(parsed):
        if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='spec_from_file_location'):continue
        check(len(node.args)==2,'Unknown importlib source-loader ABI')
        enclosing=parents.get(node)
        while enclosing is not None and not isinstance(enclosing,(ast.FunctionDef,ast.AsyncFunctionDef)):
            enclosing=parents.get(enclosing)
        bindings={}
        if enclosing:
            bindings={target.id:assignment.value for assignment in ast.walk(enclosing) if isinstance(assignment,ast.Assign)
                for target in assignment.targets if isinstance(target,ast.Name)}
        expression=node.args[1]
        if isinstance(expression,ast.Name) and expression.id in bindings:expression=bindings[expression.id]
        parameter=None;suffix='';target=None
        if isinstance(expression,ast.Call) and isinstance(expression.func,ast.Attribute) and expression.func.attr=='with_name' and len(expression.args)==1:
            operand=expression.args[0]
        elif isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Div):
            operand=expression.right
        else:operand=expression
        if isinstance(operand,ast.Constant) and isinstance(operand.value,str):
            value=operand.value;target=value if value.startswith('scripts/') else 'scripts/'+value
        elif isinstance(operand,ast.Name):parameter=operand.id
        elif (isinstance(operand,ast.BinOp) and isinstance(operand.op,ast.Add) and isinstance(operand.left,ast.Name) and
                isinstance(operand.right,ast.Constant) and operand.right.value=='.py'):parameter=operand.left.id;suffix='.py'
        else:
            target=(data_bound or {}).get(ast.unparse(node))
            check(target is not None,'Unknown dynamic importlib source path: '+ast.unparse(node))
        if parameter:
            check(enclosing and parameter in [a.arg for a in enclosing.args.args],'Unbound dynamic importlib source path')
            binding=([a.arg for a in enclosing.args.args].index(parameter),suffix)
            check(enclosing.name not in factories or factories[enclosing.name]==binding,'Ambiguous local source loader')
            factories[enclosing.name]=binding
        else:
            check(target.endswith('.py'),'Non-Python importlib source target');direct[node]=target
    return factories,direct


def loaded_target(call,factories):
    if isinstance(call.func,ast.Name) and call.func.id in factories:
        index,suffix=factories[call.func.id]
        if len(call.args)>index and isinstance(call.args[index],ast.Constant) and isinstance(call.args[index].value,str):
            return 'scripts/'+call.args[index].value+suffix
        return None
    return module_target(call)


def literal_source_expression(node):
    if isinstance(node,ast.Name) and node.id=='ROOT':return ''
    if isinstance(node,ast.Attribute) and node.attr=='ROOT':return ''
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
        left=literal_source_expression(node.left);right=literal_source_expression(node.right)
        if left is not None and right is not None:return left+'/'+right if left else right
    return None


def source_audit(root,name,api=None,data_bound=None):
    """Audit literal module loads, embedded native paths, and KERNELS boundaries.

    API-scoped files retain whole-file byte identity. Their deliberately unused
    functions do not enlarge this provider source graph.
    """
    parsed=tree(root,name);runtime=[];tools=set();dynamic=[]
    if api is not None:
        check(isinstance(api,list) and len(api)==len(set(api)) and api,'Invalid exported API scope')
        functions={n.name:n for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        check(set(api)<=functions.keys(),'Unknown API-scoped function')
        wanted=set(api);queue=list(api)
        while queue:
            for call in ast.walk(functions[queue.pop()]):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id in functions and call.func.id not in wanted:
                    wanted.add(call.func.id);queue.append(call.func.id)
        parsed=ast.Module(body=[n for n in parsed.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name in wanted],type_ignores=[])
    factories,direct=loader_targets(parsed,data_bound);tools.update(direct.values())
    check(set(data_bound or {})<={ast.unparse(n) for n in direct},'Unknown declared data-bound import')
    for node in ast.walk(parsed):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            imported=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module]
            for value in imported:
                check(value is not None and not (isinstance(node,ast.ImportFrom) and node.level),'Unresolved relative source import')
                if value.split('.')[0] in sys.stdlib_module_names:continue
                target=('' if value.startswith('scripts.') else 'scripts/')+value.replace('.','/')+'.py'
                source_path(root,target);tools.add(target)
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and SOURCE_PATTERN.fullmatch(node.value):tools.add(node.value)
        path=literal_source_expression(node)
        if path and SOURCE_PATTERN.fullmatch(path):tools.add(path)
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and '/' not in node.value and node.value.endswith('.asm.inc'):
            if (root/'native/providers'/node.value).is_file():tools.add('native/providers/'+node.value)
        if not isinstance(node,ast.Call):continue
        function=node.func
        check(not ((isinstance(function,ast.Name) and function.id in ('__import__','eval','exec')) or
            (isinstance(function,ast.Attribute) and function.attr=='import_module')),'Unsupported dynamic executable dependency')
        if (isinstance(function,ast.Name) and function.id in factories) or (isinstance(function,ast.Attribute) and function.attr=='module'):
            target=loaded_target(node,factories)
            if target:tools.add(target)
            else:dynamic.append(ast.unparse(node))
        if isinstance(function,ast.Attribute) and function.attr=='with_name':
            for arg in node.args:
                if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and arg.value.endswith('.py'):tools.add('scripts/'+arg.value)
    for node in parsed.body:
        if not isinstance(node,ast.Assign) or not any(isinstance(n,ast.Name) and n.id=='KERNELS' for n in node.targets):continue
        values=literal_assignment(parsed,'KERNELS');check(isinstance(values,(list,tuple)),'Expected explicit model KERNELS')
        names(list(values),'model KERNELS')
        for value in values:
            check('/' not in value and '\\' not in value and value not in ('.','..'),'Nonlocal model KERNELS entry')
            if value.endswith('.asm.inc'):tools.add('native/providers/'+value)
            else:
                check(value.endswith('.asm'),'Unknown model runtime source kind');runtime.append('native/runtime/'+value)
    return dict(tool_sources=sorted(tools),runtime_sources=sorted(runtime),dynamic_modules=sorted(set(dynamic)))


def native_includes(root,name):
    result=[]
    for line in source_path(root,name).read_text(encoding='utf-8-sig').splitlines():
        match=re.match(r'(?i)^\s*INCLUDE\s+([^;]+)',line)
        if match:
            target=match[1].strip().strip('"<>');source_path(root,target);result.append(target)
    names(result,'native INCLUDE targets');return result


def _family_test(node,subscript=False):
    if not isinstance(node,ast.Compare) or len(node.ops)!=1 or not isinstance(node.ops[0],ast.Eq):return None
    left=node.left
    match=(isinstance(left,ast.Name) and left.id=='family') or (subscript and isinstance(left,ast.Subscript) and
        isinstance(left.slice,ast.Constant) and left.slice.value=='family')
    return node.comparators[0].value if match and isinstance(node.comparators[0],ast.Constant) and isinstance(node.comparators[0].value,str) else None


def routes(root,loaders):
    check(set(loaders)=={'builder','verifier','framed_table','assignment'},'Unknown loader contract field')
    builder,verifier,framed=(loaders[k] for k in ('builder','verifier','framed_table'))
    mapping=literal_assignment(tree(root,framed),loaders['assignment']);check(isinstance(mapping,dict),'Expected framed route table')
    result={}
    for family,row in mapping.items():
        check(isinstance(family,str) and isinstance(row,tuple) and len(row)==3 and all(isinstance(x,str) for x in row),
            'Invalid literal framed family route')
        result[family]=dict(model='scripts/'+row[0],verifier=framed,kernel='native/providers/'+row[2])
    for node in ast.walk(tree(root,builder)):
        family=_family_test(node.test) if isinstance(node,ast.If) else None
        if not family:continue
        calls=[x for statement in node.body for x in ast.walk(statement) if isinstance(x,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='C' for t in x.targets) and isinstance(x.value,ast.Call) and
            isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='module']
        targets=[module_target(x.value) for x in calls]
        if not targets:continue
        check(len(targets)==1 and targets[0] and family not in result,'Ambiguous source model family route')
        result[family]=dict(model=targets[0],verifier=verifier,kernel=None)
    for node in ast.walk(tree(root,verifier)):
        family=_family_test(node.test,True) if isinstance(node,ast.If) else None
        if not family:continue
        calls=[x.value for statement in node.body for x in ast.walk(statement) if isinstance(x,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='verifier' for t in x.targets) and isinstance(x.value,ast.Call)]
        targets=[module_target(x) for x in calls]
        if not targets:continue
        check(family in result and len(targets)==1 and targets[0],'Verifier has no unique source-model route')
        result[family]['verifier']=targets[0]
    # Non-model raw ASM routes must still be admitted by the actual verifier.
    # The literal whitelist is read as data, never copied as Python branches.
    for node in ast.walk(tree(root,verifier)):
        if not (isinstance(node,ast.Compare) and len(node.ops)==1 and isinstance(node.ops[0],ast.In) and
                isinstance(node.left,ast.Subscript) and isinstance(node.left.slice,ast.Constant) and node.left.slice.value=='family'):continue
        try:admitted=ast.literal_eval(node.comparators[0])
        except (ValueError,TypeError):continue
        if isinstance(admitted,(list,tuple)) and all(isinstance(x,str) for x in admitted):
            for family in admitted:result.setdefault(family,dict(model=None,verifier=verifier,kernel=None))
    return result


def validate_api_consumers(root,files,scopes,data_bound):
    """Do not hide a newly consumed batch-verifier API behind an old scope."""
    for name in files:
        if not name.endswith('.py') or name==HELPER:continue
        parsed=tree(root,name);aliases={};specs={};factories,direct=loader_targets(parsed,data_bound.get(name))
        for node in ast.walk(parsed):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call):
                function=node.value.func
                if node.value in direct:
                    for var in node.targets:
                        if isinstance(var,ast.Name):specs[var.id]=direct[node.value]
                target=loaded_target(node.value,factories) if ((isinstance(function,ast.Attribute) and function.attr=='module') or
                    (isinstance(function,ast.Name) and function.id in factories)) else None
                if isinstance(function,ast.Attribute) and function.attr=='module_from_spec' and len(node.value.args)==1 and isinstance(node.value.args[0],ast.Name):
                    target=specs.get(node.value.args[0].id)
                if target in scopes:
                    for var in node.targets:
                        if isinstance(var,ast.Name):aliases[var.id]=target
        for node in ast.walk(parsed):
            if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in aliases:
                check(node.attr in scopes[aliases[node.value.id]],'Undeclared consumed source API: '+name+':'+ast.unparse(node))


def load(root=ROOT):
    root=Path(root).resolve();manifest_path=file_path(root,MANIFEST);registry_path=file_path(root,REGISTRY)
    manifest=read(manifest_path);registry=read(registry_path)
    check(set(manifest)=={'schema','kind','legacy_prefix','tool_order','shared_files','families','dependency_audits','native_includes','api_scopes','dynamic_loads','data_bound_imports','loaders'},
        'Unknown or missing tool-manifest field')
    check(manifest['schema']==1 and manifest['kind']=='runtime-provider-tool-manifest','Unsupported tool-manifest schema')
    check(registry.get('schema')==1 and isinstance(registry.get('families'),dict),'Unsupported native registry')
    prefix=manifest['legacy_prefix']
    check(prefix==dict(count=LEGACY_COUNT,sha256=LEGACY_PATH_SHA256),'Immutable legacy prefix contract changed')
    order=names(manifest['tool_order'],'ordered identity tools')
    check(len(order)>=LEGACY_COUNT+2 and path_digest(order[:LEGACY_COUNT])==LEGACY_PATH_SHA256,
        'Current 105-tool order/prefix changed')
    check(HELPER in order and MANIFEST in order and REGISTRY in order,'Helper, manifest, and registry must all be identity inputs')
    real_paths=[file_path(root,name) for name in order]
    check(len(real_paths)==len({str(p).casefold() for p in real_paths}),'Two tool names resolve to the same file')
    shared=names(manifest['shared_files'],'shared sources');check({HELPER,MANIFEST,REGISTRY}<=set(shared),'Identity controls must be shared sources')
    families=manifest['families'];check(isinstance(families,dict) and families.keys()==registry['families'].keys(),'Unknown or missing registry family')
    source_routes=routes(root,manifest['loaders']);check(not source_routes.keys()-families.keys(),'Loader table contains an unknown family')
    owned={name:'shared' for name in shared};roots=set(order[:LEGACY_COUNT])|{HELPER,MANIFEST,REGISTRY}
    for family,row in families.items():
        rule=registry['families'][family]
        check(set(row)=={'source_scope','model','verifier','kernel','owned_files'},'Unknown family tool schema: '+family)
        check(row['source_scope']=={key:rule[key] for key in ('loader','source_id','owner')},'Family source/loader boundary differs: '+family)
        check(row['kernel']==rule['kernel'],'Registry kernel omitted or changed: '+family)
        check(family in source_routes,'Registry family has no actual producer/verifier route: '+family)
        expected=source_routes[family]
        check(row['model']==expected['model'] and row['verifier']==expected['verifier'] and
            expected['kernel'] in (None,row['kernel']),'Registry family source/verifier binding differs: '+family)
        own=names(row['owned_files'],family)
        check(row['kernel'] in own and (row['model'] is None or row['model'] in own),'Family must own its model/kernel')
        for name in own:
            check(name not in owned,'Multiple owners of one tool source: '+name);owned[name]=family
        roots|={row['kernel'],row['verifier']}
        if row['model']:roots.add(row['model'])
    check(set(order)==set(owned),'Unowned or unlisted source in exact tool list')
    scopes=manifest['api_scopes'];check(isinstance(scopes,dict) and set(scopes)<=set(order),'API scope outside tool set')
    family_apis={row[key] for row in families.values() for key in ('model','verifier') if row[key]}
    check(not set(scopes)&(family_apis|set(manifest['loaders'][key] for key in ('builder','verifier','framed_table'))),
        'A family model or primary verifier cannot be hidden behind an API scope')
    pyfiles={p for p in order if p.endswith('.py') and p!=HELPER}
    check(set(manifest['dependency_audits'])==pyfiles,'Missing or extra source dependency audit')
    data_bound=manifest['data_bound_imports'];check(isinstance(data_bound,dict) and set(data_bound)<=pyfiles,'Unknown data-bound import source')
    for name,binding in data_bound.items():
        check(isinstance(binding,dict) and binding and all(isinstance(k,str) and isinstance(v,str) for k,v in binding.items()),'Malformed data-bound import contract')
        static=tree(root,name)
        visible={n.value for n in ast.walk(static) if isinstance(n,ast.Constant) and isinstance(n.value,str) and SOURCE_PATTERN.fullmatch(n.value)}
        visible|={module_target(n) for n in ast.walk(static) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='module'}
        check(set(binding.values())<=visible,'Data-bound import target must also have an explicit static source declaration')
    audits={name:source_audit(root,name,scopes.get(name),data_bound.get(name)) for name in sorted(pyfiles)}
    check(audits==manifest['dependency_audits'],'Source dependencies changed or were not explicitly declared')
    include_graph={name:native_includes(root,name) for name in order if name.endswith(('.asm','.inc','.tpl'))}
    check(include_graph==manifest['native_includes'],'Native INCLUDE dependency was not explicitly declared')
    check(all(set(paths)<=set(order) for paths in include_graph.values()),'Implicit undeclared native INCLUDE dependency')
    validate_api_consumers(root,order,scopes,data_bound)
    declared={}
    for row in manifest['dynamic_loads']:
        check(set(row)=={'source','expression','table','assignment','column'},'Unknown dynamic loader declaration')
        key=row['source'],row['expression'];check(key not in declared,'Duplicate dynamic loader declaration')
        check(row['table']==manifest['loaders']['framed_table'] and row['assignment']==manifest['loaders']['assignment'] and row['column']==0,
            'Unknown dynamic source family table')
        declared[key]=row
    actual={(name,expression) for name,audit in audits.items() for expression in audit['dynamic_modules']}
    check(actual==declared.keys(),'Unknown or undeclared dynamic source load')
    for name,audit in audits.items():
        check(set(audit['tool_sources'])<=set(order),'Implicit undeclared source dependency: '+name)
        for runtime in audit['runtime_sources']:source_path(root,runtime)
    reached=set();queue=deque(roots)
    while queue:
        name=queue.popleft()
        if name in reached:continue
        check(name in owned,'A required model/verifier/kernel is not an identity input: '+name);reached.add(name)
        queue.extend(audits.get(name,{}).get('tool_sources',[]))
        queue.extend(include_graph.get(name,[]))
    check(reached==set(order),'Unreachable extra source was added to the tool namespace')
    return dict(schema=1,tool_files=tuple(order),legacy_prefix_count=LEGACY_COUNT,owners=owned,
        family_sources=families,dependency_audits=audits,native_includes=include_graph,api_scopes=scopes,
        runtime_contract_sources=sorted({p for row in audits.values() for p in row['runtime_sources']}),
        helper_sha256=sha256(source_path(root,HELPER).read_bytes()),manifest_sha256=sha256(manifest_path.read_bytes()),
        registry_sha256=sha256(registry_path.read_bytes()),
        producer_switched=False,named_module_receipts_accepted=False)


def tool_files(root=ROOT):return load(root)['tool_files']


def _identity_bytes(root,order):return {name:sha256(file_path(root,name).read_bytes()) for name in order}


def _audited_identity(root):
    """Cache source-graph work only. Every call hashes all current input bytes."""
    root=Path(root).resolve()
    check(sha256(source_path(root,HELPER).read_bytes())==_LOADED_IMPLEMENTATION_SHA256,
        'Loaded helper full source identity changed; restart in a fresh process')
    entry=_AUDIT_CACHE.get(root)
    if entry is not None:
        current=_identity_bytes(root,entry['contract']['tool_files'])
        check(current[HELPER]==_LOADED_IMPLEMENTATION_SHA256,'Loaded helper full source identity changed')
        if current==entry['identity']:
            for name in entry['contract']['runtime_contract_sources']:source_path(root,name)
            _AUDIT_CACHE.move_to_end(root)
            return deepcopy(entry['contract']),current
    initial=read(file_path(root,MANIFEST));order=names(initial.get('tool_order'),'ordered identity tools')
    check({HELPER,MANIFEST,REGISTRY}<=set(order),'Helper, manifest, and registry must all be identity inputs')
    before=_identity_bytes(root,order)
    check(before[HELPER]==_LOADED_IMPLEMENTATION_SHA256,'Loaded helper full source identity changed')
    contract=load(root);after=_identity_bytes(root,contract['tool_files'])
    check(before==after,'Tool source changed during independent graph audit')
    _AUDIT_CACHE[root]=dict(contract=deepcopy(contract),identity=dict(after));_AUDIT_CACHE.move_to_end(root)
    while len(_AUDIT_CACHE)>4:_AUDIT_CACHE.popitem(last=False)
    return deepcopy(contract),after


def tools_identity(root=ROOT):
    return _audited_identity(root)[1]


def snapshot(root=ROOT):
    root=Path(root).resolve();before=load(root);identity=tools_identity(root);after=load(root)
    check(before==after,'Tool manifest or source graph changed during identity enumeration')
    check(identity=={name:sha256(file_path(root,name).read_bytes()) for name in before['tool_files']},'Tool source changed during enumeration')
    return dict(schema=1,verified=True,scope='standalone_declared_provider_tool_graph_and_full_file_identity_only',
        root=str(root),contract=json.loads(json.dumps(before)),tool_sources=identity,
        separately_required_runtime_sources={name:sha256(source_path(root,name).read_bytes()) for name in before['runtime_contract_sources']},
        production_sources_switched=False,
        provider_packs_revalidated=False,named_batch_revalidated=False,game_started=False)


def verify_snapshot(expected,root=ROOT):
    current=snapshot(root);check(current==expected,'Sealed tool namespace or full source identity changed');return current


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    check(output.is_relative_to(ROOT/'.boom') and not output.exists(),'Fresh project .boom receipt required')
    result=snapshot();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,ensure_ascii=True);stream.write('\n')
    print(output)
