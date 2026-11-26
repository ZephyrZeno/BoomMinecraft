"""Reuse already verified providers inside one offline call chain only.

Callers supply the objects returned by load_packs in this process. No CLI reads
this parameter, and an execution verifier still starts with fresh load_packs.
The handoff rechecks package/receipt bytes, tools and shared base artifacts.
"""
from pathlib import Path


def reuse(verifier,batch,plan,paths,packs):
    S=verifier.S;batch=Path(batch).resolve();plan=Path(plan).resolve()
    expected=[Path(p).resolve() for p in paths or ()]
    S.check(expected==[Path(p['reference']['path']).resolve() for p in packs],
            'Reused provider order or manifest set differs')
    checked=set();tool_identity=S.tools_identity()
    for pack in packs:
        path=S.checked(pack['reference']);S.checked(pack['verification']);m=pack['manifest']
        S.check(S.read(path)==m,'Reused provider manifest bytes differ')
        base=m['base']
        S.check(Path(base['batch']).resolve()==batch and Path(base['plan']).resolve()==plan,
                'Reused provider batch/plan differs')
        S.check(m['tool_sources']==tool_identity,'Reused provider tool identity changed')
        for key in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):
            record=base[key];identity=(record['path'],record['digest']['size'],record['digest']['sha256'])
            if identity not in checked:S.checked(record);checked.add(identity)
    return packs
