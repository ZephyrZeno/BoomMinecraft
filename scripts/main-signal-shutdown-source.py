"""Move Signal shutdown after owned-thread reap in native process source.

No Java, runtime provider, field, method ID, platform path, assembler or guest
execution belongs here. The complete original Signal block is moved verbatim.
The only new instructions perform a real idempotent TLCP close; its success
never overwrites an earlier shutdown failure.
"""
import hashlib

SIGNAL_START = ('IF VM_ENTRY_SIGNAL_REQUESTED\n'
    ' ; Close/join while the heap, source classes, frame pool and registry still\n')
OWNED_START = ('IF VM_ENTRY_START_REQUESTED OR VM_ENTRY_SIGNAL_REQUESTED\n'
    ' ; A source worker can still be unwinding its first diagnostic. Reap outside\n')
AFTER_JOIN = 'vpe_worker_context_done:\nENDIF\n'
CLEANUP_START = ('IFDEF VM_ENTRY_REFERENCE_PROCESSING\n'
    ' cmp DWORD PTR [rsp+72],0\n jne vpe_reference_capture\n')
SECOND_CLOSE = ("IF VM_ENTRY_SIGNAL_REQUESTED\n"
    " ; Signal is now drained; TLCP close is a real idempotent final check.\n"
    " ; Keep any prior shutdown error on success; store every nonzero result.\n"
    " lea rcx,boom_provider_threads_pool\n"
    " call boom_provider_threads_close\n"
    " test eax,eax\n"
    " jz vpe_post_signal_threads_closed\n"
    " mov DWORD PTR [rsp+72],eax\n"
    "vpe_post_signal_threads_closed:\n"
    "ENDIF\n")


def check(value, message):
    if not value:
        raise ValueError(message)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def derive(entry_text):
    check(isinstance(entry_text, str) and '\r' not in entry_text, 'Exact LF native source is required')
    for anchor in (SIGNAL_START, OWNED_START, AFTER_JOIN, CLEANUP_START):
        check(entry_text.count(anchor) == 1, 'Ambiguous or missing native shutdown source anchor')
    check('vpe_post_signal_threads_closed' not in entry_text, 'Signal shutdown was already transformed')
    first, limit = entry_text.index(SIGNAL_START), entry_text.index(OWNED_START)
    check(first < limit < entry_text.index(AFTER_JOIN) < entry_text.index(CLEANUP_START),
          'Unexpected original Signal/owned-thread/cleanup ordering')
    block = entry_text[first:limit]
    check(block.startswith(SIGNAL_START) and block.endswith('ENDIF\n') and
          block.count('IF VM_ENTRY_SIGNAL_REQUESTED\n') == 1 and block.count('ENDIF\n') == 1 and
          block.count(' call boom_provider_signal_close\n') == 1,
          'Expected one complete original Signal close and observation block')
    check(entry_text.index(CLEANUP_START) == entry_text.index(AFTER_JOIN) + len(AFTER_JOIN),
          'Owned-thread context capture must directly precede the original cleanup guard')
    without = entry_text[:first] + entry_text[limit:]
    insertion = block + SECOND_CLOSE
    derived = without.replace(AFTER_JOIN, AFTER_JOIN + insertion, 1)
    model = dict(schema=1, operation='move_original_signal_block_after_owned_reap_and_check_TLCP_again',
        original_sha256=digest(entry_text), derived_sha256=digest(derived),
        original_signal_offset=first, original_owned_offset=limit,
        original_signal_block=block, original_signal_block_sha256=digest(block),
        original_owned_anchor=OWNED_START, after_owned_context_anchor=AFTER_JOIN,
        original_cleanup_guard=CLEANUP_START, second_close_text=SECOND_CLOSE,
        signal_block_moved_byteexact=True, status72_success_never_clears_prior_error=True,
        additional_external_imports=[], additional_public_exports=[],
        original_20second_owned_join_loop_unchanged=True,
        original_OWAI_Parker_RPR_failure_guards_unchanged=True,
        Java_or_metadata_or_runtime_or_context_changed=False)
    check(inverse(derived, model) == entry_text, 'Exact inverse native repair failed')
    return derived, model


def inverse(derived, model):
    check(model['schema'] == 1 and digest(derived) == model['derived_sha256'], 'Derived native source/model changed')
    check(model['original_owned_anchor'] == OWNED_START and model['after_owned_context_anchor'] == AFTER_JOIN and
          model['original_cleanup_guard'] == CLEANUP_START and model['second_close_text'] == SECOND_CLOSE,
          'Native repair contract anchors changed')
    block = model['original_signal_block']
    check(digest(block) == model['original_signal_block_sha256'] and block.startswith(SIGNAL_START),
          'Original complete Signal block changed')
    insertion = AFTER_JOIN + block + SECOND_CLOSE
    check(derived.count(insertion) == 1, 'Ambiguous repaired native shutdown block')
    moved_back = derived.replace(insertion, AFTER_JOIN, 1)
    check(moved_back.count(OWNED_START) == 1 and SIGNAL_START not in moved_back,
          'Ambiguous inverse Signal placement')
    original = moved_back.replace(OWNED_START, block + OWNED_START, 1)
    check(digest(original) == model['original_sha256'], 'Inverse differs from every original native source byte')
    return original
