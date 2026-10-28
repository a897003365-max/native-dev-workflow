import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from workflow import route, failure_action, audit_mapping, select_family
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
        self.assertEqual(result['requested']['model'], 'gpt-6.1-sol')
        self.assertEqual(result['requested']['reasoning_effort'], 'high')

    def test_multimodule_judgment_standard(self):
        self.task.update(difficulty='L2', assessment_evidence='接口明确，但需要协调两个模块的数据契约')
        self.assertEqual(route(self.task, self.config)['tier'], 'standard')

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

    def test_sol_routes_migrate_to_61_without_changing_other_tiers(self):
        for parent in ['gpt-6-sol', 'gpt-6.1-sol', 'gpt-6.1-terra', 'gpt-6-astra', 'gpt-6-luna']:
            self.task.update(parent_model=parent, difficulty='L2')
            r = route(self.task, self.config)
            self.assertEqual(r['dispatch']['model'], 'gpt-6.1-sol')
            self.assertEqual(r['dispatch']['reasoning_effort'], 'high')
            self.assertEqual(r['speed_preference']['requested'], 'inherit_parent')
        self.task.update(parent_model='gpt-6.1-sol', difficulty='L1',
                         failures=[{'cause':'capability','root_cause':'integration_judgment'}])
        self.assertEqual(route(self.task, self.config)['dispatch']['model'], 'gpt-6.1-sol')
        for settings in self.config['families'].values():
            self.assertNotIn('gpt-6-sol', [value['model'] for value in settings.values()])

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

    def test_optional_routing_inputs_preserve_general_defaults(self):
        self.task.pop('workload', None)
        self.task.pop('reasoning_need', None)
        implicit = route(self.task, self.config)
        self.task.update(workload='general', reasoning_need='normal')
        explicit = route(self.task, self.config)
        self.assertEqual(implicit['requested'], explicit['requested'])
        self.assertEqual(implicit['selection_rules'], explicit['selection_rules'])
        self.assertEqual(explicit['requested'], {'model': 'gpt-6-luna', 'reasoning_effort': 'xhigh'})

    def test_invalid_workload_and_reasoning_need_rejected(self):
        for field in ['workload', 'reasoning_need']:
            for value in ['unknown', None, True, [], {}]:
                with self.subTest(field=field, value=value):
                    task = dict(self.task, **{field: value})
                    with self.assertRaisesRegex(ValueError, 'invalid ' + field):
                        route(task, self.config)

    def test_visual_specialist_for_bounded_observation_and_execution(self):
        for role in ['Explorer', 'Executor']:
            for difficulty in ['L1', 'L2']:
                for risk in ['low', 'medium']:
                    with self.subTest(role=role, difficulty=difficulty, risk=risk):
                        self.task.update(parent_model='gpt-6.1-terra', workload='visual_interaction',
                                         role=role, difficulty=difficulty, risk=risk,
                                         write_scope=[] if role == 'Explorer' else ['slug.py'])
                        r = route(self.task, self.config)
                        self.assertEqual(r['family'], '6')
                        self.assertEqual(r['requested'], {'model': 'gpt-6.1-terra', 'reasoning_effort': 'medium'})
                        self.assertEqual(r['dispatch']['model'], r['requested']['model'])
                        self.assertIn('specialist:visual_interaction', r['selection_rules'])
                        self.assertEqual(r['speed_preference']['requested'], 'inherit_parent')
                        self.assertIsNone(r['speed_preference']['observed'])
                        self.assertIsNone(r['observed_runtime']['model'])
                        self.assertNotIn('service_tier', r['dispatch'])

    def test_visual_preference_does_not_override_general_quality_boundaries(self):
        cases = [('Executor', 'L3', 'low', 'gpt-6-astra'),
                 ('Executor', 'L1', 'high', 'gpt-6-luna'),
                 ('Advisor', 'L2', 'low', 'gpt-6.1-sol'),
                 ('Reviewer', 'L1', 'low', 'gpt-6.1-sol'),
                 ('Reviewer', 'L1', 'high', 'gpt-6-astra')]
        for role, difficulty, risk, model in cases:
            with self.subTest(role=role, difficulty=difficulty, risk=risk):
                self.task.update(workload='visual_interaction', role=role, difficulty=difficulty,
                                 risk=risk, write_scope=['slug.py'] if role == 'Executor' else [])
                r = route(self.task, self.config)
                self.assertEqual(r['requested']['model'], model)
                self.assertNotIn('specialist:visual_interaction', r['selection_rules'])

    def test_review_floor_applies_to_code_behavior_only_in_six_family(self):
        self.task.update(role='Reviewer', write_scope=[], tiny=True, behavior_change=True)
        r = route(self.task, self.config)
        self.assertEqual(r['tier'], 'standard')
        self.assertIn('code_review_floor:standard', r['selection_rules'])
        self.task['behavior_change'] = False
        self.assertEqual(route(self.task, self.config)['requested']['model'], 'gpt-6-luna')
        self.task.update(parent_model='gpt-5.6-sol', behavior_change=True,
                         workload='visual_interaction', reasoning_need='deep_comparison')
        r = route(self.task, self.config)
        self.assertEqual(r['requested'], {'model': 'gpt-5.6-luna', 'reasoning_effort': 'xhigh'})

    def test_deep_comparison_sol_max_matches_validated_dispatch(self):
        self.task.update(difficulty='L2', role='Advisor', write_scope=[])
        self.assertEqual(route(self.task, self.config)['requested']['reasoning_effort'], 'high')
        self.task['reasoning_need'] = 'deep_comparison'
        r = route(self.task, self.config)
        self.assertEqual(r['requested'], {'model': 'gpt-6.1-sol', 'reasoning_effort': 'max'})
        self.assertIn('deep_comparison:max', r['selection_rules'])
        self.assertEqual({k: r['dispatch'][k] for k in r['requested']}, r['requested'])
        conflict = route(self.task, self.config, {'model_reasoning_effort': 'high'})
        self.assertIsNone(conflict['dispatch'])
        self.assertIn('role_overrides_reasoning_effort', conflict['warnings'])

    def test_deep_comparison_does_not_invent_other_model_efforts(self):
        cases = [('gpt-6-astra', 'L1', 'general', 'gpt-6-luna', 'xhigh'),
                 ('gpt-6-astra', 'L3', 'general', 'gpt-6-astra', 'high'),
                 ('gpt-6-astra', 'L2', 'visual_interaction', 'gpt-6.1-terra', 'medium'),
                 ('gpt-5.6-sol', 'L2', 'general', 'gpt-5.6-terra', 'medium'),
                 ('gpt-5.6-sol', 'L3', 'general', 'gpt-5.6-sol', 'high')]
        for parent, difficulty, workload, model, effort in cases:
            with self.subTest(parent=parent, difficulty=difficulty, workload=workload):
                self.task.update(parent_model=parent, difficulty=difficulty, workload=workload,
                                 reasoning_need='deep_comparison')
                self.assertEqual(route(self.task, self.config)['requested'],
                                 {'model': model, 'reasoning_effort': effort})

    def test_deep_comparison_requires_supported_max(self):
        self.task.update(difficulty='L2', reasoning_need='deep_comparison')
        self.config['catalog']['gpt-6.1-sol'].remove('max')
        with self.assertRaisesRegex(ValueError, 'verified catalog'):
            route(self.task, self.config)

    def test_specialist_must_be_configured_supported_and_same_family(self):
        self.task['workload'] = 'visual_interaction'
        settings = self.config['specialists']['6']
        valid = settings.pop('visual_interaction')
        with self.assertRaisesRegex(ValueError, 'specialist must be configured'):
            route(self.task, self.config)
        settings['visual_interaction'] = dict(valid, model='gpt-5.6-terra')
        with self.assertRaisesRegex(ValueError, 'parent model family'):
            route(self.task, self.config)
        settings['visual_interaction'] = dict(valid, reasoning_effort='none')
        with self.assertRaisesRegex(ValueError, 'verified catalog'):
            route(self.task, self.config)
        settings['visual_interaction'] = valid
        self.config['catalog'].pop('gpt-6.1-terra')
        with self.assertRaisesRegex(ValueError, 'verified catalog'):
            route(self.task, self.config)

    def test_ultra_is_not_dispatched_as_single_agent_reasoning(self):
        self.config['families']['6']['standard']['reasoning_effort'] = 'ultra'
        self.task['difficulty'] = 'L2'
        with self.assertRaisesRegex(ValueError, 'ultra delegates additional agents'):
            route(self.task, self.config)
        self.task['workload'] = 'visual_interaction'
        self.config['specialists']['6']['visual_interaction']['reasoning_effort'] = 'ultra'
        with self.assertRaisesRegex(ValueError, 'ultra delegates additional agents'):
            route(self.task, self.config)

    def test_specialist_capability_failure_requires_reassessment_without_resetting_history(self):
        failure = {'cause': 'capability', 'root_cause': 'ambiguous_visual_state'}
        self.task.update(workload='visual_interaction', failures=[failure])
        r = route(self.task, self.config)
        self.assertEqual(r['action'], 'reassess_specialist_failure')
        self.assertIn('specialist_capability_failure:reassess', r['selection_rules'])
        self.assertIsNone(r['dispatch'])
        self.assertEqual(r['retry_count'], 1)
        self.task['workload'] = 'general'
        r = route(self.task, self.config)
        self.assertEqual(r['requested']['model'], 'gpt-6.1-sol')
        self.assertEqual(r['retry_count'], 1)
        self.assertEqual(self.task['failures'], [failure])
        self.task.update(workload='visual_interaction', failures=[failure, failure])
        self.assertEqual(route(self.task, self.config)['action'], 'stop_same_plan_rediagnose')
        self.task['failures'].append(failure)
        self.assertEqual(route(self.task, self.config)['action'], 'stop_limit')

    def test_visual_specialist_does_not_bypass_failure_or_verification_gates(self):
        self.task['workload'] = 'visual_interaction'
        for cause, action in [('environment', 'blocked_environment'), ('permission', 'blocked_environment'),
                              ('tool', 'blocked_environment'), ('external', 'diagnose_external_no_model_upgrade'),
                              ('context', 'supply_context'), ('size', 'resplit')]:
            with self.subTest(cause=cause):
                self.task['failures'] = [{'cause': cause, 'root_cause': 'missing_visual_input'}]
                r = route(self.task, self.config)
                self.assertEqual(r['action'], action)
                self.assertIsNone(r['dispatch'])
        self.task['failures'] = []
        self.task['verification']['required'].append('local_browser')
        r = route(self.task, self.config)
        self.assertEqual(r['requested']['model'], 'gpt-6.1-terra')
        self.assertEqual(r['missing_verification'], ['local_browser'])
        self.assertIsNone(r['dispatch'])

    def test_workload_is_not_inferred_from_ui_words(self):
        self.task['goal'] = '截图 UI visual interaction 局部按钮操作'
        self.assertEqual(route(self.task, self.config)['requested']['model'], 'gpt-6-luna')
        self.task.update(role='Explorer', workload='visual_interaction')
        with self.assertRaisesRegex(ValueError, 'read-only role'):
            route(self.task, self.config)

    def test_runtime_not_fabricated(self):
        r = route(self.task, self.config)
        self.assertIsNone(r['observed_runtime']['model'])
        self.assertIsNone(r['evidence_binding'])
        self.assertEqual(r['review_result'], 'not_run')

if __name__ == '__main__': unittest.main()
