"""Test-only System123 bridge/decoder over genuine focused source artifacts.

This module is deliberately separate from the frozen candidate and canonical
VM-entry decoder. It does not call an old verifier with modified globals.
"""
import hashlib
import argparse
import importlib.util
import json
from pathlib import Path
import struct


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('stack_component_'+name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


M=module('vm-entry-source');S=M.S
TEMPLATE=ROOT/'native/entry/stack_walk_component.asm.inc'


def checked(record):
    path=Path(record['path']).resolve();actual=M.native_input_artifact(record)
    S.check(actual['path']==str(path),'Component artifact path differs');return path


def historical_inputs(images_file,snapshot_file,snapshot_sha):
    """Check a sealed historical full proof, preserving all original receipts.

    Only source files explicitly copied and hash-bound before the cutover may
    resolve through the snapshot. All ASM/COFF/image/data inputs remain at their
    original artifact paths and must still match. This is historical reuse,
    not a current-tool full-selection verification claim.
    """
    images_file,snapshot_file=Path(images_file).resolve(),Path(snapshot_file).resolve()
    S.check(images_file.is_relative_to(S.ART) and snapshot_file.is_relative_to(S.ART) and
            S.digest(snapshot_file)['sha256']==snapshot_sha,'Explicit focused historical snapshot pin differs')
    images,snapshot=S.read(images_file),S.read(snapshot_file)
    S.check(snapshot['baseline_images']==S.artifact(images_file) and snapshot['baseline_full_source_proof']==images['source_selection'] and
            snapshot['all_original_focused_inputs_rehashed'] is True and snapshot['old_receipts_modified'] is False,
            'Snapshot is not bound to the genuine focused full proof')
    sources={}
    for row in snapshot['sources']:
        original=Path(row['original']['path']).resolve();copy=checked(row['snapshot'])
        S.check(any(original.is_relative_to(ROOT/name) for name in ('scripts','native','native-config')) and
                copy.is_relative_to(snapshot_file.parent) and row['original']['digest']==row['snapshot']['digest'] and
                original not in sources,'Invalid or repeated historical source mapping')
        sources[original]=row
    for record in images['inputs']:
        original=Path(record['path']).resolve()
        if original in sources:S.check(sources[original]['original']==record,'Historical source seal differs from the full input record')
        else:checked(record)
    directory=Path(images['source_selection_directory']);closure=S.read(checked(images['source_manifest']))
    proof=S.read(checked(images['source_selection']))
    S.check(proof['verified'] is True and proof['closure_manifest_sha256']==S.digest(directory/'closure.json')['sha256'] and
            proof['diagnostic_manifest_sha256']==S.digest(directory/'diagnostic.json')['sha256'] and
            images['source_selection_independently_reverified'] is True and images['runtime_acceptance_proven'] is False,
            'Historical full source proof scope or original manifests differ')
    D=module('diagnostic-objects');sealed=D.verify(directory)
    S.check(sealed==proof['verified_assembly_objects'],'Actual retained source/COFF provenance differs from the real full proof')
    return images,closure,proof,dict(snapshot=S.artifact(snapshot_file),historical_full_source=S.artifact(images['source_selection']['path']),
        historical_namespace_reused=True,current_full_selection_reverified=False,old_receipts_modified=False)


def assembly(closure):
    """Insert one explicit bridge after the intact original System123 owner."""
    model=M.binding_model(closure,True,signal_control=True,system_phase2=True,system_phase3=True)
    S.check(not model.get('game_entry') and M.report_layout(model)==(544,13),'Component requires the ordinary complete System123 owner ABI13')
    original,imports=M.assembly(model)
    anchor=' call boom_vm_call_system_phase3\n test eax,eax\n jz vpe_capture\nENDIF\n'
    S.check(original.count(anchor)==1 and original.endswith('\nEND\n'),'Missing unique original post-System3 insertion point')
    addition=(' lea rcx,boom_vm_entry_context\n lea rdx,boom_vm_entry_report\n'
              ' call boom_stack_walk_component_entry\n test eax,eax\n jz vpe_capture\n')
    classes=closure['selected_classes'];graphics=[row for row in classes if row['name']=='javax/swing/DebugGraphics']
    buffered=[row for row in classes if row['name']=='java/awt/image/BufferedImage']
    S.check(len(graphics)==len(buffered)==1,'Normal original Graphics/BufferedImage class descriptors must be selected')
    graphics,buffered=graphics[0],buffered[0]
    ctors=[(ident,row) for ident,row in closure['selected_methods'].items() if row['class_id']==graphics['class_id'] and
           row['name']=='<init>' and row['descriptor']=='(Ljava/awt/Graphics;)V']
    S.check(len(ctors)==1,'Entire original Graphics-argument constructor must be selected')
    ident,ctor=ctors[0]
    aliases=(f'SW_TEST_GRAPHICS_CLASS TEXTEQU <boom_class{graphics["class_id"]}>\n'
             f'SW_TEST_GRAPHICS_LAYOUT TEXTEQU <boom_layout{graphics["class_id"]}>\n'
             f'SW_TEST_GRAPHICS_CONSTRUCTOR TEXTEQU <boom_m{ident}>\n'
             f'SW_TEST_BUFFERED_CLASS TEXTEQU <boom_class{buffered["class_id"]}>\n')
    extra_procs={'boom_object_new',f'boom_m{ident}'}
    extra_data={f'boom_class{graphics["class_id"]}',f'boom_layout{graphics["class_id"]}',
                f'boom_class{buffered["class_id"]}','boom_stack_walk_active_count','boom_stack_walk_counters'}
    declarations=''.join(f'EXTERN {name}:PROC\n' for name in sorted(extra_procs-imports))
    declarations+=''.join(f'EXTERN {name}:BYTE\n' for name in sorted(extra_data-imports))
    body=original.replace(anchor,anchor+addition)
    template=TEMPLATE.read_text(encoding='utf-8')
    final=aliases+declarations+body[:-5]+template+'\nEND\n'
    recovered=final.removeprefix(aliases+declarations)
    S.check(recovered.endswith(template+'\nEND\n'),'Test bridge source complement differs')
    recovered=recovered[:-(len(template)+5)]+'\nEND\n'
    S.check(recovered.replace(anchor+addition,anchor)==original,'Owner changes exceed one post-System3 call and the explicit new test helper')
    proof=dict(scope='explicit_test_only_single_post_System3_bridge',original_owner_assembly_sha256=hashlib.sha256(original.encode()).hexdigest(),
        inserted_call_sha256=hashlib.sha256(addition.encode()).hexdigest(),component_template=S.artifact(TEMPLATE),
        other_owner_source_bytes_identical=True,Java_Code_changed=False,Java_fields_or_clinit_state_patched=False,
        main_game_entry_requested=False,BufferedImage_expected_uninitialized=True,source_constructor=dict(ctor,method=int(ident)))
    return final,model,imports|extra_procs|extra_data,M.entry_exports(model)|{'boom_stack_walk_component_entry','boom_stack_walk_component_report'},proof


def decode(raw,probe,exit_code,diagnostics):
    """Read the real ABI13 prefix plus the explicit separate component report."""
    S.check(len(raw)==544 and struct.unpack_from('<II',raw)==(0x52454d56,13),'Component native owner report ABI differs')
    S.check(len(probe)==128,'Component observation report size differs')
    def u(at):return struct.unpack_from('<I',raw,at)[0]
    def q(at):return struct.unpack_from('<Q',raw,at)[0]
    def p(at):return struct.unpack_from('<I',probe,at)[0]
    def pq(at):return struct.unpack_from('<Q',probe,at)[0]
    S.check(exit_code==u(80) and exit_code in (0,70,86) and u(64)==7 and u(68)==u(48)==0 and q(40)==0,
            'Component owned process cleanup/monitor/exit protocol failed')
    S.check(u(76)==u(272)==u(276)==u(280)==1 and u(284)==0 and u(288)==1 and u(292)==2 and
            u(512)==u(516)==1 and u(520)==2 and u(524)==4 and u(528)==u(540)==0,
            'Complete original System123 must return before the component')
    S.check(p(0)==1 and p(8)==p(12)==0,'Component was not entered or BufferedImage initialized')
    latest=[u(at) for at in (296,300,304,308)];test=[p(at) for at in (16,20,24,28)]
    S.check(latest==test,'Component Context differs from the latest original main capture')
    S.check(u(136)==u(184)==u(200)==0,'Component original worker failure publication differs')
    # Signal has one worker; the aggregate Thread lifecycle counts both owned
    # Reference and Signal workers, neither is counted as a normal Java run.
    S.check(u(144)==u(148)==1 and q(152)==q(168)==q(176)==1 and q(120)==0 and q(128)==q(208)==q(216)==q(224)==q(232)==2,
            'Component signal/worker exit/reap counters differ')
    S.check(u(320)==u(324)==u(328)==1 and u(332)==u(376)==0 and u(380)==6 and q(352)==q(360) and
            u(400)==u(404)==u(408)==1 and u(412)==0,'Component Reference/Object.wait owner did not close')
    S.check(u(448)==u(452)==1 and u(456)==0 and u(460)==0 and u(464)==u(468)==0 and
            q(472)==q(480)==q(488)==q(496)==0,'Component native owners retained live state')
    S.check(q(504)<=1048576,'Component native root snapshot exceeds the private vector')
    S.check(pq(48)==0,'Component left an active StackWalker generation')
    rows={row['id']:row for row in diagnostics['rows']};fault=rows.get(u(32)) if u(28)==2 else None
    passed=p(4)==1 and latest[0]==0 and exit_code==0 and u(72)==1 and u(28)==0
    if not passed:S.check(u(72)==0 and ((exit_code==86 and latest[0]==45057 and fault) or (exit_code==70 and latest[0]!=0)),
                         'Component failure has no actual source stop or Context')
    return dict(verified=True,scope='test_only_original_System123_then_original_DebugGraphics_StackWalker_prefix',
        original_System123_completed=True,VM_level=4,cold_constructor_completed=bool(passed),latest_test_Context=test,
        first_source_fault=fault,BufferedImage_initialized=False,Stack_native_active=pq(48),native_checks=pq(56),
        native_first_batches=pq(64),native_fetches=pq(72),Class_mirrors_filled=pq(80),native_generations_cleaned=pq(88),
        original_Java_callback_execution_verified=bool(passed and pq(64)>0 and pq(88)==pq(64)),
        native_8_OS_execution_verified=False,full_selection_reverified=False,prototype_native_added=3,
        runtime_acceptance_complete=False,game_started=False,world_created=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images',type=Path,required=True);parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--snapshot-sha256',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    S.check(output.is_relative_to(S.ART/'stack-walk') and not output.exists(),'Fresh isolated component emitter output required')
    images,closure,proof,history=historical_inputs(args.images,args.snapshot,args.snapshot_sha256)
    source,model,imports,exports,bridge=assembly(closure);output.mkdir(parents=True)
    (output/'owner.asm').write_text(source,encoding='utf-8')
    S.write(output/'emitter.json',dict(scope='unexecuted_test_only_System123_then_original_DebugGraphics_bridge',
        baseline_images=S.artifact(args.images),historical_inputs=history,assembly=S.artifact(output/'owner.asm'),
        binding_model=model,imports=sorted(imports),exports=sorted(exports),bridge=bridge,
        producer=S.artifact(Path(__file__)),template=S.artifact(TEMPLATE),linked=False,executed=False,
        callback_execution_verified=False,native_8_OS_execution_verified=False,full_selection_reverified=False))
    print(output/'emitter.json')
