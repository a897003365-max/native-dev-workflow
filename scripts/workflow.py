#!/usr/bin/env python3
"""Semantic assessments in; validated native dispatch proposals out. No model calls."""
import argparse
import json
from pathlib import Path

ROLES = {'Explorer', 'Executor', 'Reviewer', 'Advisor'}
FAILURES = {'context', 'size', 'capability', 'environment', 'permission', 'tool', 'external'}


def failure_action(history, limit=3):
    if type(limit) is not int or limit < 1:
        raise ValueError('max_fix_rounds must be a positive integer')
    for item in history:
        if item.get('cause') not in FAILURES or not item.get('root_cause'):
            raise ValueError('failure requires cause and stable root_cause identifier')
    if not history:
        return 'proceed'
    if len(history) >= limit:
        return 'stop_limit'
    cause = history[-1]['cause']
    if cause in {'environment', 'permission', 'tool'}:
        return 'blocked_environment'
    if cause == 'external':
        return 'diagnose_external_no_model_upgrade'
    if len(history) > 1 and history[-1]['root_cause'] == history[-2]['root_cause']:
        return 'stop_same_plan_rediagnose'
    return {'context': 'supply_context', 'size': 'resplit', 'capability': 'escalate_with_evidence'}[cause]


def audit_mapping(config, role_config=None, requested=None):
    warnings = []
    aliases = config.get('aliases', {})
    groups = {}
    for tier, value in config['tiers'].items():
        model = value['model']
        seen = set()
        while model in aliases:
            if model in seen:
                raise ValueError('cyclic model aliases')
            seen.add(model)
            model = aliases[model]
        groups.setdefault((model, value['reasoning_effort']), []).append(tier)
    if len(groups) < len(config['tiers']):
        warnings.append('tiers_collapse_same_model_and_effort')
    mapped = {aliases.get(v['model'], v['model']) for v in config['tiers'].values()}
    if len(mapped) == 1:
        warnings.append('single_model_reasoning_tiers_only')
    if role_config and requested:
        for key, source in [('model', 'model'), ('reasoning_effort', 'model_reasoning_effort')]:
            if source in role_config and role_config[source] != requested[key]:
                warnings.append('role_overrides_' + key)
    return warnings


def select_family(task, config):
    parent = task.get('parent_model')
    family = config['parent_models'].get(parent)
    if family is None:
        raise ValueError('actual parent_model required; unknown model must be verified, no cross-family fallback')
    selected = dict(config, tiers=config['families'][family])
    for value in selected['tiers'].values():
        if config['parent_models'].get(value['model']) != family:
            raise ValueError('child model must stay in parent model family')
    return family, selected


def route(task, config, role_config=None):
    family, config = select_family(task, config)
    required = ['id', 'goal', 'write_scope', 'acceptance', 'difficulty', 'risk',
                'assessment_evidence', 'tools', 'verification', 'role', 'tiny', 'behavior_change']
    for key in required:
        if key not in task:
            raise ValueError('missing field: ' + key)
    if task['difficulty'] not in {'L1', 'L2', 'L3'} or task['risk'] not in {'low', 'medium', 'high'}:
        raise ValueError('invalid difficulty or risk')
    if task['role'] not in ROLES or not task['assessment_evidence'] or not task['acceptance']:
        raise ValueError('role, semantic assessment evidence and acceptance required')
    for key in ['tiny', 'behavior_change']:
        if type(task[key]) is not bool:
            raise ValueError(key + ' must be boolean')
    if task['role'] != 'Executor' and task['write_scope']:
        raise ValueError('read-only role must have empty write_scope')
    v = task['verification']
    for key in ['required', 'available']:
        if not isinstance(v.get(key), list):
            raise ValueError('verification required/available must be lists')
    missing = sorted(set(v['required']) - set(v['available']))
    action = failure_action(task.get('failures', []), config['max_fix_rounds'])
    tier = {'L1': 'economy', 'L2': 'standard', 'L3': 'strong'}[task['difficulty']]
    if task['role'] == 'Reviewer' and task['risk'] == 'high':
        tier = 'strong'
    if action == 'escalate_with_evidence':
        tier = {'economy': 'standard', 'standard': 'strong', 'strong': 'strong'}[tier]
    requested = dict(config['tiers'][tier])
    catalog = config['catalog']
    if requested['model'] not in catalog or requested['reasoning_effort'] not in catalog[requested['model']]:
        raise ValueError('requested model/effort not in verified catalog')
    warnings = audit_mapping(config, role_config, requested)
    blocked = missing or any(w.startswith('role_overrides_') for w in warnings)
    direct = (task['role'] == 'Executor' and task['tiny']
              and task['difficulty'] == 'L1' and task['risk'] == 'low')
    permission = task.get('observed_permissions', {})
    strict_review_missing = task['role'] == 'Reviewer' and task['risk'] == 'high' and not (
        permission.get('filesystem_read_only') is True and permission.get('external_writes_disabled') is True)
    if strict_review_missing:
        blocked = True
        warnings.append('high_risk_review_permission_boundary_unverified')
    can_dispatch = not direct and not blocked and action in {'proceed', 'escalate_with_evidence'}
    return {
        'task': task, 'family': family, 'tier': tier, 'selection_reason': task['assessment_evidence'],
        'action': 'blocked_verification_or_config' if blocked else ('main_agent_direct' if direct and action == 'proceed' else action),
        'requested': requested, 'speed_preference': config.get('speed_preferences', {}).get(requested['model']),
        'missing_verification': missing, 'warnings': warnings,
        'dispatch': dict(task_name=task['id'].lower().replace('-', '_'), fork_turns='none',
                         model=requested['model'], reasoning_effort=requested['reasoning_effort']) if can_dispatch else None,
        'review_requirement': 'independent_strong_before_commit' if task['risk'] == 'high' else (
            'independent_at_delivery' if task['behavior_change'] else 'lightweight_explicitly_label'),
        'observed_runtime': {'model': None, 'reasoning_effort': None, 'upstream_model': None,
                             'permissions': permission, 'source': None},
        'retry_count': len(task.get('failures', [])), 'review_result': 'not_run',
        'final_acceptance': '阻塞' if blocked else '部分完成',
        'evidence_binding': None, 'usage': {'measured': None, 'estimated': None, 'quota': 'unknown'}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('--config', type=Path, default=Path(__file__).parents[1] / 'routing.json')
    parser.add_argument('--role-config', type=Path)
    args = parser.parse_args()
    role = None
    if args.role_config:
        import tomllib
        role = tomllib.loads(args.role_config.read_text())
    try:
        result = route(json.loads(args.task.read_text()), json.loads(args.config.read_text()), role)
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
