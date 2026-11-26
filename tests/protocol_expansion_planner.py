"""Source-shape preflight must never turn recognition into an implementation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location('protocol_planner', Path(__file__).resolve().parents[1] / 'scripts/plan-protocol-expansion.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def cls():
    return dict(class_id=1, name='p/Host', origin=dict(loader='application', sha256='original'),
                access=0x31, superclass='java/lang/Object', record_components=None,
                fields=[], constants={}, methods=[])


def site(owner, name, descriptor, arguments):
    return dict(name=name, descriptor=descriptor, arguments=arguments,
                bootstrap=dict(owner=owner, name=name, descriptor=M.BOOTSTRAPS[owner, name],
                               reference_kind=6, interface=False))


def concat(descriptor='(I)Ljava/lang/String;', recipe=None, constants=()):
    c = cls()
    c['constants']['1'] = dict(StringUtf16=[1] if recipe is None else recipe)
    c['constants'].update({str(i): value for i, value in enumerate(constants, 2)})
    return c, site(M.CONCAT, 'makeConcatWithConstants', descriptor, list(range(1, len(constants)+2)))


def lambda_site(kind=6, captured='I', target='(II)I'):
    c = cls()
    c['constants'] = {'1': dict(MethodType='(I)I'), '2': dict(Handle=dict(reference_kind=kind,
        owner='p/Host', name='target', descriptor=target, interface=False)), '3': dict(MethodType='(I)I')}
    return c, site(M.LAMBDA, 'metafactory', '('+captured+')Ljava/util/function/IntUnaryOperator;', [1, 2, 3])


def record(operation='equals'):
    c = cls()
    c.update(superclass='java/lang/Record', record_components=[['value', 'D']],
             fields=[dict(name='value', descriptor='D', access=0x12)])
    c['constants'] = {'1': dict(Class='p/Host'), '2': dict(StringUtf16=list(map(ord, 'value'))),
        '3': dict(Handle=dict(reference_kind=1, owner='p/Host', name='value', descriptor='D', interface=False))}
    descriptor = {'equals': '(Lp/Host;Ljava/lang/Object;)Z', 'hashCode': '(Lp/Host;)I',
                  'toString': '(Lp/Host;)Ljava/lang/String;'}[operation]
    s = site(M.RECORD, 'bootstrap', descriptor, [1, 2, 3])
    s['name'] = operation
    return c, s


class ProtocolExpansionTests(unittest.TestCase):
    def test_concat_recipe_preserves_NUL_surrogates_and_constant_markers(self):
        c, s = concat(recipe=[0, 0xD800, 2, 1, 0xDC00], constants=[dict(StringUtf16=[2, 1])])
        plan = M.expand_shape(c, s)
        self.assertEqual(plan['parts'], [dict(literal_utf16=[0, 0xD800, 2, 1]),
            dict(argument=0, descriptor='I'), dict(literal_utf16=[0xDC00])])
        self.assertFalse(plan['expander_implemented'])
        self.assertFalse(plan['semantic_compatibility_verified'])

    def test_char_array_uses_reference_conversion_and_double_is_retained(self):
        c, s = concat('([CDLjava/lang/Object;)Ljava/lang/String;', [1, 1, 1])
        plan = M.expand_shape(c, s)
        self.assertEqual(plan['arguments'], ['[C', 'D', M.OBJECT])
        self.assertIn('float_double_formatting', plan['required_checks'])
        self.assertIn('exception', plan['required_checks'][-1])

    def test_nonstring_bootstrap_constant_is_not_guessed_as_its_numeric_text(self):
        c, s = concat(recipe=[1, 2], constants=[dict(Int=42)])
        result = M.expand_shape(c, s)
        self.assertEqual(result['classification'], 'compatibility_case')
        self.assertIn('link_time_conversion', result['reason'])

    def test_concat_marker_mismatch_and_wide_slot_limit_stay_visible(self):
        c, s = concat(recipe=[1, 1])
        self.assertEqual(M.expand_shape(c, s)['reason'], 'recipe_marker_arity')
        c, s = concat('('+'J'*100+')Ljava/lang/String;', [1]*100)
        self.assertEqual(M.expand_shape(c, s)['classification'], 'structural_candidate')
        c, s = concat('('+'J'*101+')Ljava/lang/String;', [1]*101)
        self.assertEqual(M.expand_shape(c, s)['classification'], 'compatibility_case')

    def test_zero_argument_makeConcat_has_no_invented_literal_or_body(self):
        result = M.expand_shape(cls(), site(M.CONCAT, 'makeConcat', '()Ljava/lang/String;', []))
        self.assertEqual(result['parts'], [])
        self.assertIn('overflow_OOM_and_allocation_identity', result['required_checks'])

    def test_similar_bootstrap_owner_is_insufficient(self):
        c, s = concat()
        for key, value in (('reference_kind', 5), ('interface', True), ('descriptor', '()V')):
            changed = copy.deepcopy(s)
            changed['bootstrap'][key] = value
            self.assertEqual(M.expand_shape(c, changed)['classification'], 'compatibility_case')
        s['bootstrap']['owner'] = 'mods/StringConcatFactory'
        self.assertEqual(M.expand_shape(c, s)['proposed_rule'], 'unregistered')

    def test_lambda_captures_are_normal_class_plan_not_an_opaque_object(self):
        c, s = lambda_site()
        result = M.expand_shape(c, s)
        self.assertEqual(result['captured'], ['I'])
        self.assertEqual(result['expansion'], 'generated_normal_class_and_ordinary_IR')
        self.assertIn('capture_assignability', result['required_checks'])
        self.assertFalse(result['semantic_compatibility_verified'])

    def test_bound_and_unbound_receiver_have_different_null_check_timing(self):
        c, s = lambda_site(kind=5, captured='Lp/Host;', target='(I)I')
        self.assertTrue(M.expand_shape(c, s)['bound_receiver_null_check'])
        c, s = lambda_site(kind=5, captured='', target='()I')
        c['constants']['1'] = c['constants']['3'] = dict(MethodType='(Lp/Host;)I')
        self.assertFalse(M.expand_shape(c, s)['bound_receiver_null_check'])

    def test_constructor_handle_includes_allocated_result(self):
        c, s = lambda_site(kind=8, captured='', target='(I)V')
        c['constants']['2']['Handle']['name'] = '<init>'
        c['constants']['1'] = c['constants']['3'] = dict(MethodType='(I)Lp/Host;')
        self.assertEqual(M.expand_shape(c, s)['effective_implementation_return'], 'Lp/Host;')

    def test_serializable_altMetafactory_requires_its_own_contract(self):
        c, s = lambda_site()
        s['bootstrap']['name'] = 'altMetafactory'
        s['bootstrap']['descriptor'] = M.BOOTSTRAPS[M.LAMBDA, 'altMetafactory']
        c['constants'].update({'4': dict(Int=5), '5': dict(Int=0)})
        s['arguments'] += [4, 5]
        result = M.expand_shape(c, s)
        self.assertEqual(result['classification'], 'compatibility_case')
        self.assertTrue(result['shape']['serializable'])
        c['constants']['4'] = dict(Int=8)
        self.assertEqual(M.expand_shape(c, s)['reason'], 'unknown_altMetafactory_flags')

    def test_marker_and_bridge_counts_must_be_consumed_exactly(self):
        c, s = lambda_site()
        s['bootstrap']['name'] = 'altMetafactory'
        s['bootstrap']['descriptor'] = M.BOOTSTRAPS[M.LAMBDA, 'altMetafactory']
        c['constants'].update({'4': dict(Int=6), '5': dict(Int=1), '6': dict(Class='p/Marker'),
                               '7': dict(Int=1), '8': dict(MethodType='(I)I')})
        s['arguments'] += [4, 5, 6, 7, 8]
        self.assertEqual(M.expand_shape(c, s)['marker_interfaces'], ['p/Marker'])
        s['arguments'].pop()
        self.assertEqual(M.expand_shape(c, s)['reason'], 'invalid_altMetafactory_count')

    def test_primitive_SAM_mismatch_cannot_be_accepted_as_a_cast(self):
        c, s = lambda_site()
        c['constants']['3'] = dict(MethodType='(J)I')
        self.assertEqual(M.expand_shape(c, s)['classification'], 'compatibility_case')

    def test_record_plan_keeps_float_nan_zero_and_type_identity_checks(self):
        for operation in ('equals', 'hashCode', 'toString'):
            c, s = record(operation)
            result = M.expand_shape(c, s)
            self.assertEqual(result['classification'], 'structural_candidate')
            self.assertIn('NaN_canonicalization_and_signed_zero', result['required_checks'])
            self.assertIn('exact_record_type_identity', result['required_checks'])

    def test_record_getter_cannot_substitute_another_field_or_class(self):
        c, s = record()
        c['constants']['3']['Handle']['owner'] = 'p/Other'
        self.assertEqual(M.expand_shape(c, s)['reason'], 'noncanonical_record_getter')
        c, s = record()
        c['fields'][0]['access'] = 0x1A
        self.assertEqual(M.expand_shape(c, s)['reason'], 'record_field_access')

    def test_record_display_names_survive_obfuscation_and_are_not_field_names(self):
        c, s = record('toString')
        c['constants']['2'] = dict(StringUtf16=list(map(ord, 'originalDisplayName')))
        result = M.expand_shape(c, s)
        self.assertEqual(result['classification'], 'structural_candidate')
        self.assertEqual(result['components'][0][0], 'value')
        self.assertEqual(result['bootstrap_display_names_utf16'], list(map(ord, 'originalDisplayName')))
        c['constants']['2'] = dict(StringUtf16=list(map(ord, 'a;b')))
        self.assertEqual(M.expand_shape(c, s)['reason'], 'record_display_name_arity')
        s['name'], s['descriptor'] = 'equals', '(Lp/Host;Ljava/lang/Object;)Z'
        self.assertTrue(M.expand_shape(c, s)['display_names_ignored'])

    def test_record_instance_field_visibility_is_not_a_bootstrap_invariant(self):
        for access in (0x10, 0x11, 0x12):
            c, s = record()
            c['fields'][0]['access'] = access
            self.assertEqual(M.expand_shape(c, s)['classification'], 'structural_candidate')

    def test_descriptor_validation_rejects_void_parameters_and_invalid_arrays(self):
        self.assertEqual(M.signature('([[Lp/C;JD)V'), (['[[Lp/C;', 'J', 'D'], 'V'))
        for bad in ('(V)V', '([V)V', '(I)Vextra', '(Lbad.name;)V', '('+'['*256+'I)V', '(Lmissing)V'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                M.signature(bad)

    def test_inspection_uses_actual_opcode_and_payload_digest(self):
        c, s = concat()
        c['constants']['7'] = dict(InvokeDynamic=s)
        c['methods'] = [dict(id=8, code_sha256='Code', body=dict(instructions=[
            dict(opcode=186, pc=4, operand=dict(Constant=7))]))]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'source.zip'
            data = json.dumps(c).encode()
            with zipfile.ZipFile(path, 'w') as bundle:
                bundle.writestr('class.json', data)
            digest = lambda b: dict(size=len(b), sha256=hashlib.sha256(b).hexdigest())
            entry = dict(class_id=1, class_sha256='original', path='class.json', digest=digest(data))
            shard = dict(zip=dict(path=str(path), digest=digest(path.read_bytes())), entries=[entry])
            protocol = s['bootstrap']['owner'] + '.' + s['bootstrap']['name'] + s['bootstrap']['descriptor']
            request = {1: {7: ('boom_batch_call_1_7_186', protocol)}}
            result = M.inspect_shard((shard, request))
            self.assertEqual(result[0]['source_uses'], [dict(method=8, code_sha256='Code', pc=4)])
            request[1][7] = ('boom_batch_call_1_7_186', 'different')
            with self.assertRaisesRegex(ValueError, 'actual source'):
                M.inspect_shard((shard, request))
            path.write_bytes(path.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                M.inspect_shard((shard, request))

    def test_mixed_server_client_IR_is_rejected_before_planning(self):
        with tempfile.TemporaryDirectory() as root:
            batch, ir = Path(root) / 'batch', Path(root) / 'ir'
            batch.mkdir(); ir.mkdir()
            (batch / 'summary.json').write_text(json.dumps(dict(input_fingerprint='server', ir_identity='IR')), encoding='utf-8')
            (batch / 'verification.json').write_text(json.dumps(dict(verified=True, dispatch=dict(verified=True))), encoding='utf-8')
            (ir / 'summary.json').write_text(json.dumps(dict(input_fingerprint='client', identity='IR')), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                M.plan(batch, ir, 1)


if __name__ == '__main__':
    unittest.main()
