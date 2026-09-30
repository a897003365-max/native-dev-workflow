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
        self.assertIsNone(r['dispatch'])
        self.task['observed_permissions'] = {'filesystem_read_only':True, 'external_writes_disabled':True}
        self.assertIsNotNone(route(self.task, self.config)['dispatch'])

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

if __name__ == '__main__': unittest.main()
