"""Source-bound selection data; unselected original targets remain fail stops."""
import hashlib
import re


def check(value,message):
    if not value:raise ValueError(message)


def model_contract(C,meta):
    if not meta.get('selection_specific_sites_required'):return
    check(callable(C.selected_sites) and isinstance(C.SELECTED,str) and C.SELECTED.startswith('boom_') and
        meta['selected_site_bytes']==32,'Unknown selection-specific source ABI')


def project(packs,selected_packs,selected_classes,selected_methods,S):
    families=S.module('selection_source_family_table','framed-runtime-service.py').FAMILIES
    selected_method_ids={int(key) for key in selected_methods}
    parts=[];proof=[];pending_methods=set();pending_classes=set();symbols=set()
    for index,pack in enumerate(packs):
        m=pack['manifest']
        if index not in selected_packs or m['family'] not in families:continue
        module,key,_=families[m['family']];meta=S.read(S.checked(m[key+'_metadata']))
        if not meta.get('selection_specific_sites_required'):continue
        C=S.module('selection_'+key,module);model_contract(C,meta)
        text,imports,sites=C.selected_sites(meta,selected_classes,selected_methods)
        S.check(C.SELECTED not in symbols,'Duplicate selection data symbol');symbols.add(C.SELECTED)
        for row in sites:
            callback=row['callback']
            if callback is None:continue
            method=re.fullmatch(r'boom_m(\d+)',callback);cls=re.fullmatch(r'boom_batch_initialize_(\d+)',callback)
            S.check(method is not None or cls is not None,'Selection callback is not an original method/class gap')
            (pending_methods if method else pending_classes).add(int((method or cls)[1]))
        S.check(all(not r['ready'] or r['method'] in selected_method_ids for r in sites),
                'Selection data marks unselected Java Code ready')
        parts.append(text);proof.append(dict(provider_manifest=pack['reference'],metadata=m[key+'_metadata'],symbol=C.SELECTED,
            imports=sorted(imports),sites=sites,assembly_sha256=hashlib.sha256(text.encode()).hexdigest()))
    return ''.join(parts),pending_methods,pending_classes,proof
