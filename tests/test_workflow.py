import json
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from workflow import route, failure_action, audit_mapping, select_family, preflight, audit_dispatches, digest
ROOT = Path(__file__).parents[1]

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / 'references/task.example.json').read_text())
        self.config = json.loads((ROOT / 'routing.json').read_text())

    def test_tiny_uses_no_agent(self):
        self.task['tiny'] = True
        result = route(self.task, self.config)
        self.assertIsNone(result['dispatch'])
        self.assertEqual(result['action'], 'main_agent_direct')

    def test_clear_mechanical_uses_economy(self):
        result = route(self.task, self.config)
        self.assertEqual(result['tier'], 'economy')
        self.assertEqual(result['dispatch']['fork_turns'], 'none')

    def test_tiny_code_still_gets_independent_reviewer(self):
        self.task.update(role='Reviewer', write_scope=[], tiny=True)
        result = route(self.task, self.config)
        self.assertIsNotNone(result['dispatch'])
        self.assertEqual(result['review_requirement'], 'independent_at_delivery')

    def test_multimodule_judgment_standard(self):
        self.task.update(difficulty='L2', assessment_evidence='接口明确，但需要协调两个模块的数据契约')
        result = route(self.task, self.config)
        self.assertEqual(result['tier'], 'standard')
        self.assertEqual(result['requested'], {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'})

    def test_61_deep_comparison_uses_max_only_with_evidence(self):
        self.task.update(parent_model='gpt-6.1-sol', difficulty='L2', reasoning_need='deep_comparison')
        with self.assertRaises(ValueError): route(self.task, self.config)
        self.task['reasoning_evidence'] = '需要对比日志与请求不一致的多个候选解释'
        result = route(self.task, self.config)
        self.assertEqual(result['dispatch']['model'], 'gpt-6.1-sol')
        self.assertEqual(result['dispatch']['reasoning_effort'], 'max')
        self.config['catalog']['gpt-6.1-sol'].remove('max')
        with self.assertRaises(ValueError): route(self.task, self.config)

    def test_56_standard_is_terra_high(self):
        self.task.update(parent_model='gpt-5.6-sol', difficulty='L2')
        self.assertEqual(route(self.task, self.config)['requested'],
                         {'model': 'gpt-5.6-terra', 'reasoning_effort': 'high'})

    def test_risk_evidence_required(self):
        for value in ['', '   ', None, []]:
            self.task['risk_evidence'] = value
            with self.assertRaises(ValueError): route(self.task, self.config)

    def test_no_forced_model_diversity(self):
        first = route(self.task, self.config)['dispatch']
        self.task['id'] = 'NEXT-L1'
        second = route(self.task, self.config)['dispatch']
        self.assertEqual(first['model'], second['model'])
        self.assertEqual(first['reasoning_effort'], second['reasoning_effort'])

    def test_unknown_cause_then_reassess(self):
        self.task.update(difficulty='L3', role='Advisor', write_scope=[], assessment_evidence='尚无可复现根因')
        self.assertEqual(route(self.task, self.config)['tier'], 'strong')
        self.task.update(difficulty='L1', role='Executor', write_scope=['slug.py'], assessment_evidence='已用失败测试证实根因，实现路径明确')
        self.assertEqual(route(self.task, self.config)['tier'], 'economy')

    def test_one_line_balance_high_risk(self):
        self.task.update(risk='high', tiny=True, assessment_evidence='一行余额规则改变账本不变量')
        r = route(self.task, self.config)
        self.assertEqual(r['review_requirement'], 'independent_strong_before_commit')
        self.assertEqual(r['tier'], 'economy')
        self.task.update(role='Reviewer', write_scope=[])
        r = route(self.task, self.config)
        self.assertEqual(r['tier'], 'strong')
        self.assertIsNotNone(r['dispatch'])
        self.assertEqual(r['review_mode'], 'code')
        self.assertEqual(r['review_isolation'], 'behavioral_read_only')
        self.assertEqual(r['review_result'], 'not_run')
        self.assertEqual(r['review_requirement'], 'independent_strong_before_commit')
        self.assertIn('review_permission_isolation_not_enforced', r['warnings'])

    def test_strict_review_requires_both_verified_boundaries_at_any_risk(self):
        self.task.update(role='Reviewer', write_scope=[], review_mode='strict')
        for risk in ['low', 'high']:
            self.task['risk'] = risk
            for permission in [{}, {'filesystem_read_only': True},
                               {'external_writes_disabled': True},
                               {'filesystem_read_only': True, 'external_writes_disabled': False}]:
                self.task['observed_permissions'] = permission
                r = route(self.task, self.config)
                self.assertIsNone(r['dispatch'])
                self.assertEqual(r['final_acceptance'], '阻塞')
                self.assertIn('strict_review_permission_boundary_unverified', r['warnings'])
        self.task['observed_permissions'] = {'filesystem_read_only': True, 'external_writes_disabled': True}
        r = route(self.task, self.config)
        self.assertIsNotNone(r['dispatch'])
        self.assertEqual(r['review_isolation'], 'enforced_read_only')

    def test_code_review_unknown_isolation_is_not_fabricated(self):
        self.task.update(role='Reviewer', write_scope=[], risk='high', observed_permissions={})
        r = route(self.task, self.config)
        self.assertIsNotNone(r['dispatch'])
        self.assertEqual(r['review_isolation'], 'unknown')
        self.assertEqual(r['review_result'], 'not_run')

    def test_isolated_test_blocks_only_dependent_review_task(self):
        self.task.update(role='Reviewer', write_scope=[], risk='high', review_mode='isolated_test')
        r = route(self.task, self.config)
        self.assertIsNone(r['dispatch'])
        self.assertIn('isolated_test_environment', r['missing_verification'])
        self.task['review_mode'] = 'code'
        self.assertIsNotNone(route(self.task, self.config)['dispatch'])
        self.task['review_mode'] = 'isolated_test'
        self.task['verification']['available'].append('isolated_test_environment')
        r = route(self.task, self.config)
        self.assertIsNotNone(r['dispatch'])
        self.assertEqual(r['review_isolation'], 'behavioral_test_scope')
        self.task['verification']['required'].append('real_device')
        self.assertIsNone(route(self.task, self.config)['dispatch'])

    def test_invalid_review_mode_rejected(self):
        self.task.update(role='Reviewer', write_scope=[], review_mode='production')
        with self.assertRaises(ValueError): route(self.task, self.config)

    def test_code_review_preserves_parent_pending_without_blocking(self):
        self.task.update(role='Reviewer', write_scope=[], risk='high',
                         pending_verification=['real_device', 'isolated_test_environment'])
        r = route(self.task, self.config)
        self.assertIsNotNone(r['dispatch'])
        self.assertEqual(r['pending_verification'], ['real_device', 'isolated_test_environment'])
        self.assertEqual(r['missing_verification'], [])
        self.assertNotEqual(r['final_acceptance'], '通过')
        self.task['verification']['required'].append('necessary_test_evidence')
        r = route(self.task, self.config)
        self.assertIsNone(r['dispatch'])
        self.assertIn('necessary_test_evidence', r['missing_verification'])
        self.assertEqual(r['pending_verification'], ['real_device', 'isolated_test_environment'])

    def test_invalid_pending_verification_rejected(self):
        for pending in ['real_device', None, [True]]:
            self.task['pending_verification'] = pending
            with self.assertRaises(ValueError): route(self.task, self.config)

    def test_missing_device_not_model_upgrade(self):
        self.task['verification']['required'].append('real_device')
        r = route(self.task, self.config)
        self.assertEqual(r['final_acceptance'], '阻塞')
        self.assertEqual(r['tier'], 'economy')
        self.assertIsNone(r['dispatch'])

    def test_role_override_detected(self):
        r = route(self.task, self.config, {'model':'gpt-6-astra','model_reasoning_effort':'ultra'})
        self.assertIn('role_overrides_model', r['warnings'])
        self.assertIn('role_overrides_reasoning_effort', r['warnings'])
        self.assertIsNone(r['dispatch'])

    def test_alias_collapse_detected(self):
        for v in self.config['families']['6'].values():
            self.config['aliases'][v['model']] = 'one-upstream'
            v['reasoning_effort'] = 'high'
        self.assertIn('tiers_collapse_same_model_and_effort', audit_mapping(select_family(self.task, self.config)[1]))
        self.assertIn('single_model_reasoning_tiers_only', audit_mapping(select_family(self.task, self.config)[1]))

    def test_failure_bounds(self):
        f = {'cause':'capability', 'root_cause':'wrong_state_model'}
        self.assertEqual(failure_action([f]), 'escalate_with_evidence')
        self.assertEqual(failure_action([f,f]), 'stop_same_plan_rediagnose')
        self.assertEqual(failure_action([f,f,f]), 'stop_limit')
        for cause in ['environment','permission','tool']:
            self.assertEqual(failure_action([dict(cause=cause,root_cause='absent')]), 'blocked_environment')
        self.assertEqual(failure_action([dict(cause='external',root_cause='503')]), 'diagnose_external_no_model_upgrade')

    def test_blocked_failure_cannot_dispatch(self):
        self.task['failures'] = [{'cause':'context','root_cause':'missing_contract'}]
        self.assertIsNone(route(self.task, self.config)['dispatch'])

    def test_read_only_scope_rejected(self):
        self.task['role'] = 'Reviewer'
        with self.assertRaises(ValueError): route(self.task, self.config)

    def test_unsupported_model_rejected(self):
        self.config['families']['6']['economy']['model'] = 'imaginary-fast'
        with self.assertRaises(ValueError): route(self.task, self.config)

    def test_all_parent_models_keep_family(self):
        for parent, family in self.config['parent_models'].items():
            for difficulty in ['L1', 'L2', 'L3']:
                self.task.update(parent_model=parent, difficulty=difficulty)
                r = route(self.task, self.config)
                self.assertEqual(r['family'], family)
                self.assertEqual(self.config['parent_models'][r['dispatch']['model']], family)

    def test_missing_or_unknown_parent_rejected(self):
        for parent in [None, 'gpt-5.6', 'future-model']:
            self.task['parent_model'] = parent
            with self.assertRaises(ValueError): route(self.task, self.config)

    def test_cross_family_config_rejected(self):
        self.config['families']['6']['economy']['model'] = 'gpt-5.6-luna'
        with self.assertRaises(ValueError): route(self.task, self.config)

    def test_escalation_stays_in_family(self):
        self.task.update(parent_model='gpt-5.6-sol', difficulty='L2',
                         failures=[{'cause':'capability','root_cause':'complex_state'}])
        r = route(self.task, self.config)
        self.assertEqual(r['dispatch']['model'], 'gpt-5.6-sol')
        self.assertEqual(r['tier'], 'strong')

    def test_speed_follows_parent_except_6_luna_without_faking_application(self):
        for family in ['6', '5.6']:
            for tier, setting in self.config['families'][family].items():
                self.task.update(parent_model='gpt-' + family + '-sol',
                                 difficulty={'economy':'L1','standard':'L2','strong':'L3'}[tier])
                r = route(self.task, self.config)
                expected_speed = 'fast' if setting['model'] == 'gpt-6-luna' else 'inherit_parent'
                self.assertEqual(r['speed_preference']['requested'], expected_speed)
                self.assertEqual(r['speed_preference']['application'], 'unavailable_per_child_in_current_spawn_tool')
                self.assertIsNone(r['speed_preference']['observed'])
                self.assertNotIn('service_tier', r['dispatch'])
                if setting['model'].endswith('-luna'):
                    self.assertEqual(r['dispatch']['reasoning_effort'], 'xhigh')
                elif setting['model'].endswith('-sol'):
                    self.assertEqual(r['dispatch']['reasoning_effort'], 'high')

    def test_runtime_not_fabricated(self):
        r = route(self.task, self.config)
        self.assertIsNone(r['observed_runtime']['model'])
        self.assertIsNone(r['evidence_binding'])
        self.assertEqual(r['review_result'], 'not_run')

    def prepared(self):
        result = route(self.task, self.config)
        call = dict(result['dispatch'], message='有界任务契约；真实文本由主 Agent 注入')
        capabilities = {'source': 'fixture schema', 'parameters': list(call), 'catalog': self.config['catalog']}
        result['preflight'] = preflight(result, call, capabilities)
        return result, call, capabilities

    def test_preflight_rejects_inheritance_mismatch_and_extra_params(self):
        result, call, capabilities = self.prepared()
        for key in ['model', 'reasoning_effort', 'fork_turns']:
            bad = dict(call)
            del bad[key]
            with self.assertRaises(ValueError): preflight(result, bad, capabilities)
        for change in [dict(fork_turns='all'), dict(model='gpt-6-astra'), dict(reasoning_effort='low'),
                       dict(service_tier='fast'), dict(message='')]:
            with self.assertRaises(ValueError): preflight(result, dict(call, **change), capabilities)
        capabilities['catalog'] = {}
        with self.assertRaises(ValueError): preflight(result, call, capabilities)
        result['dispatch'] = None
        with self.assertRaises(ValueError): preflight(result, call, capabilities)

    def audit_fixture(self, call_change=None, model=None, effort=None, record_change=None,
                     extra=False, desktop=False, parent_match=True, changed_artifact=False, contexts=None):
        result, call, capabilities = self.prepared()
        with TemporaryDirectory() as directory:
            base = Path(directory)
            result['route_evidence'] = {}
            for key, content in [('task', self.task), ('config', self.config), ('capabilities', capabilities)]:
                path = base / (key + '.json')
                path.write_text(json.dumps(content), encoding='utf-8')
                result['route_evidence'][key] = {'path': str(path), 'sha256': digest(path.read_bytes())}
            if record_change:
                record_change(result)
            if changed_artifact:
                (base / 'task.json').write_text('{}', encoding='utf-8')
            actual = dict(call)
            if call_change:
                call_change(actual)
            events = [
                {'type': 'session_meta', 'payload': {'id': 'parent-1'}},
                {'timestamp': '2099-01-01T00:00:00Z', 'type': 'response_item', 'payload': {
                    'type': 'function_call', 'name': 'collaboration.spawn_agent', 'call_id': 'call-1',
                    'arguments': json.dumps(actual)}},
                {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'call-1',
                    'output': json.dumps({'task_name': '/root/smoke_1'} if desktop else {'agent_id': 'child-1'})}}]
            if extra:
                events.append({'timestamp': '2099-01-01T00:00:00Z', 'type': 'response_item', 'payload': {
                    'type': 'function_call', 'name': 'collaboration.spawn_agent', 'call_id': 'call-2',
                    'arguments': json.dumps({'task_name': 'unrouted', 'message': 'bypass'})}})
            parent = base / 'parent.jsonl'
            parent.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
            children = []
            if model or effort or contexts:
                child = base / 'child.jsonl'
                child.write_text('\n'.join(json.dumps(e) for e in [
                    {'type': 'session_meta', 'payload': {'id': 'child-1',
                        **({'agent_path': '/root/smoke_1', 'parent_thread_id': 'parent-1' if parent_match else 'another-parent'}
                           if desktop else {})}},
                    *({'type': 'turn_context', 'payload': context}
                      for context in (contexts or [{'model': model, 'effort': effort}]))]), encoding='utf-8')
                children.append(child)
            return audit_dispatches(parent, [result], children)

    def test_audit_matching_request_runtime_is_not_upstream_proof(self):
        result = self.audit_fixture(model='gpt-6-luna', effort='xhigh')
        self.assertEqual(result['protocol_status'], 'passed')
        self.assertEqual(result['dispatches'][0]['runtime_status'], 'match')
        self.assertIsNone(result['dispatches'][0]['upstream_identity'])

    def test_audit_unknown_runtime_stays_unknown(self):
        result = self.audit_fixture()
        self.assertEqual(result['protocol_status'], 'passed')
        self.assertEqual(result['dispatches'][0]['runtime_status'], 'unknown')

    def test_audit_detects_unrouted_spawn_even_with_valid_receipt(self):
        result = self.audit_fixture(extra=True)
        self.assertEqual(result['protocol_status'], 'failed')
        codes = {v['code'] for v in result['violations']}
        self.assertTrue({'missing_route_preflight', 'missing_model', 'missing_reasoning_effort'} <= codes)

    def test_audit_detects_call_and_runtime_mismatch(self):
        result = self.audit_fixture(call_change=lambda call: call.pop('model'), model='gpt-6-astra', effort='high')
        codes = {v['code'] for v in result['violations']}
        self.assertTrue({'dispatch_route_mismatch', 'missing_model', 'runtime_request_mismatch'} <= codes)

    def test_audit_detects_late_preflight_and_changed_message(self):
        result = self.audit_fixture(call_change=lambda call: call.update(message='changed'),
            record_change=lambda record: record['preflight'].update(checked_at='2100-01-01T00:00:00+00:00'))
        codes = {v['code'] for v in result['violations']}
        self.assertTrue({'dispatch_message_changed_after_preflight', 'preflight_not_before_dispatch'} <= codes)

    def test_audit_detects_missing_artifact_bindings(self):
        result = self.audit_fixture(record_change=lambda record: record.update(route_evidence={}))
        self.assertIn('missing_route_artifact_binding', {v['code'] for v in result['violations']})

    def test_desktop_agent_path_and_opaque_message_are_not_fabricated(self):
        result = self.audit_fixture(desktop=True, model='gpt-6-luna', effort='xhigh',
                                   call_change=lambda call: call.update(message='gAAAAopaque'))
        self.assertEqual(result['protocol_status'], 'passed')
        dispatch = result['dispatches'][0]
        self.assertEqual(dispatch['agent_id'], 'child-1')
        self.assertEqual(dispatch['message_status'], 'unverifiable_opaque_log')
        self.assertEqual(result['unverified'], [{'task_name': 'smoke_1', 'field': 'message_status'}])

    def test_child_from_other_parent_cannot_supply_runtime_proof(self):
        result = self.audit_fixture(desktop=True, parent_match=False, model='gpt-6-luna', effort='xhigh')
        self.assertIn('child_parent_binding_unconfirmed', {v['code'] for v in result['violations']})

    def test_changed_artifacts_detected(self):
        result = self.audit_fixture(changed_artifact=True)
        self.assertIn('route_artifact_changed_or_missing', {v['code'] for v in result['violations']})

    def test_partial_runtime_cannot_claim_match(self):
        result = self.audit_fixture(model='gpt-6-luna')
        self.assertEqual(result['dispatches'][0]['runtime_status'], 'unknown')

    def test_later_matching_context_does_not_hide_earlier_mismatch(self):
        result = self.audit_fixture(contexts=[{'model': 'gpt-6-astra', 'effort': 'high'},
                                             {'model': 'gpt-6-luna', 'effort': 'xhigh'}])
        self.assertEqual(result['protocol_status'], 'failed')
        self.assertEqual(result['dispatches'][0]['runtime_status'], 'mismatch')
        self.assertEqual(len(result['dispatches'][0]['runtime_records']), 2)
        self.assertIn('runtime_request_mismatch', {v['code'] for v in result['violations']})

    def test_later_matching_context_does_not_hide_incomplete_context(self):
        result = self.audit_fixture(contexts=[{'model': 'gpt-6-luna'},
                                             {'model': 'gpt-6-luna', 'effort': 'xhigh'}])
        self.assertEqual(result['dispatches'][0]['runtime_status'], 'unknown')

if __name__ == '__main__': unittest.main()
