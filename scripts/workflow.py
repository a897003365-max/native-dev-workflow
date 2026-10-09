#!/usr/bin/env python3
"""Semantic assessments in; validated native dispatch proposals out. No model calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
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
                'assessment_evidence', 'risk_evidence', 'reasoning_need',
                'tools', 'verification', 'role', 'tiny', 'behavior_change']
    for key in required:
        if key not in task:
            raise ValueError('missing field: ' + key)
    if task['difficulty'] not in {'L1', 'L2', 'L3'} or task['risk'] not in {'low', 'medium', 'high'}:
        raise ValueError('invalid difficulty or risk')
    if task['role'] not in ROLES or not task['assessment_evidence'] or not task['acceptance']:
        raise ValueError('role, semantic assessment evidence and acceptance required')
    for key in ['assessment_evidence', 'risk_evidence']:
        if not isinstance(task[key], str) or not task[key].strip():
            raise ValueError(key + ' must contain factual assessment evidence')
    if task['reasoning_need'] not in {'routine', 'deep_comparison'}:
        raise ValueError('invalid reasoning_need')
    if task['reasoning_need'] == 'deep_comparison' and not task.get('reasoning_evidence', '').strip():
        raise ValueError('deep_comparison requires reasoning_evidence')
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
    pending = task.get('pending_verification', [])
    if not isinstance(pending, list) or any(not isinstance(item, str) for item in pending):
        raise ValueError('pending_verification must be a list of verification names')
    review_mode = task.get('review_mode', 'code')
    if review_mode not in {'code', 'isolated_test', 'strict'}:
        raise ValueError('invalid review_mode')
    if task['role'] == 'Reviewer' and review_mode == 'isolated_test':
        missing = sorted(set(missing) | ({'isolated_test_environment'} - set(v['available'])))
    action = failure_action(task.get('failures', []), config['max_fix_rounds'])
    tier = {'L1': 'economy', 'L2': 'standard', 'L3': 'strong'}[task['difficulty']]
    if task['role'] == 'Reviewer' and task['risk'] == 'high':
        tier = 'strong'
    if action == 'escalate_with_evidence':
        tier = {'economy': 'standard', 'standard': 'strong', 'strong': 'strong'}[tier]
    requested = dict(config['tiers'][tier])
    effort_rule = config.get('reasoning_rules', {}).get(requested['model'])
    if effort_rule:
        requested['reasoning_effort'] = effort_rule[task['reasoning_need']]
    catalog = config['catalog']
    if requested['model'] not in catalog or requested['reasoning_effort'] not in catalog[requested['model']]:
        raise ValueError('requested model/effort not in verified catalog')
    warnings = audit_mapping(config, role_config, requested)
    blocked = missing or any(w.startswith('role_overrides_') for w in warnings)
    direct = (task['role'] == 'Executor' and task['tiny']
              and task['difficulty'] == 'L1' and task['risk'] == 'low')
    permission = task.get('observed_permissions', {})
    review_isolation = None
    if task['role'] == 'Reviewer':
        if permission.get('filesystem_read_only') is True and permission.get('external_writes_disabled') is True:
            review_isolation = 'enforced_read_only'
        elif permission.get('sandbox') == 'danger-full-access' or any(
                permission.get(key) is False for key in ['filesystem_read_only', 'external_writes_disabled']):
            review_isolation = 'behavioral_read_only'
        else:
            review_isolation = 'unknown'
        if review_mode == 'isolated_test' and review_isolation == 'behavioral_read_only':
            review_isolation = 'behavioral_test_scope'
        if review_isolation != 'enforced_read_only':
            warnings.append('review_permission_isolation_not_enforced')
            if review_mode == 'strict':
                blocked = True
                warnings.append('strict_review_permission_boundary_unverified')
    can_dispatch = not direct and not blocked and action in {'proceed', 'escalate_with_evidence'}
    return {
        'task': task, 'family': family, 'tier': tier, 'selection_reason': task['assessment_evidence'],
        'action': 'blocked_verification_or_config' if blocked else ('main_agent_direct' if direct and action == 'proceed' else action),
        'requested': requested, 'speed_preference': config['speed_preferences'].get(requested['model'], config['speed_preferences']['default']),
        'missing_verification': missing, 'warnings': warnings,
        'pending_verification': pending,
        'review_mode': review_mode if task['role'] == 'Reviewer' else None,
        'review_isolation': review_isolation,
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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rollout_rows(path):
    with path.open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            yield number, json.loads(line)


def preflight(result, call, capabilities):
    """Check a proposed call. This does not intercept the native spawn tool."""
    expected = result['dispatch']
    if expected is None:
        raise ValueError('route is not dispatchable')
    if set(call) != set(expected) | {'message'}:
        raise ValueError('dispatch requires exact routed fields plus message; no omitted or extra parameters')
    if any(call[key] != value for key, value in expected.items()):
        raise ValueError('dispatch differs from route')
    if not isinstance(call['message'], str) or not call['message'].strip():
        raise ValueError('dispatch message required')
    if not capabilities.get('source') or not set(call) <= set(capabilities['parameters']):
        raise ValueError('current spawn schema source/parameters required')
    if call['reasoning_effort'] not in capabilities['catalog'].get(call['model'], []):
        raise ValueError('current spawn schema does not support requested model/effort')
    return {'checked_at': datetime.now(timezone.utc).isoformat(),
            'parameters': expected, 'message_sha256': digest(call['message'].encode()),
            'capabilities_source': capabilities['source'],
            'enforcement': 'local_check_only_not_tool_interception'}


def runtime_from_rollout(path):
    """Only read caller-selected metadata; never infer upstream identity."""
    identity, metadata, observed = None, {}, []
    for number, row in rollout_rows(path):
        data = row.get('payload', {})
        if row.get('type') == 'session_meta':
            metadata = {key: data.get(key) for key in ['id', 'agent_path', 'parent_thread_id']}
            metadata['source'] = {'path': str(path.resolve()), 'line': number}
            identity = metadata['agent_path'] or metadata['id']
        if row.get('type') == 'turn_context':
            observed.append({'model': data.get('model'),
                        'reasoning_effort': data.get('effort', data.get('reasoning_effort')),
                        'source': {'path': str(path.resolve()), 'line': number}})
    return identity, {'metadata': metadata, 'observed': observed}


def audit_dispatches(rollout, records, child_rollouts=()):
    """Audit actual spawn calls, including calls without a route receipt."""
    calls, responses, parent_id = [], {}, None
    for number, row in rollout_rows(rollout):
        data = row.get('payload', {})
        if row.get('type') == 'session_meta':
            parent_id = data.get('id')
        if row.get('type') != 'response_item':
            continue
        if data.get('type') == 'function_call' and data.get('name', '').split('.')[-1] == 'spawn_agent':
            calls.append((number, row.get('timestamp'), data))
        elif data.get('type') == 'function_call_output' and any(
                call[2].get('call_id') == data.get('call_id') for call in calls):
            responses[data.get('call_id')] = data.get('output')
    runtime = {}
    for path in child_rollouts:
        identity, entry = runtime_from_rollout(path)
        if not identity or identity in runtime:
            raise ValueError('missing or duplicate child runtime identity')
        runtime[identity] = entry
    receipts = {}
    for record in records:
        name = (record.get('dispatch') or {}).get('task_name')
        if name in receipts:
            raise ValueError('duplicate route task_name')
        receipts[name] = record
    findings, results, used = [], [], set()
    for number, timestamp, data in calls:
        call = json.loads(data['arguments'])
        violations = []
        message_status = 'unknown'
        record = receipts.get(call.get('task_name'))
        if not record or not record.get('preflight'):
            violations.append('missing_route_preflight')
        else:
            if call['task_name'] in used:
                violations.append('reused_preflight')
            used.add(call['task_name'])
            receipt = record['preflight']
            if receipt['parameters'] != record.get('dispatch'):
                violations.append('preflight_route_record_mismatch')
            evidence = record.get('route_evidence', {})
            if not {'task', 'config', 'capabilities'} <= evidence.keys():
                violations.append('missing_route_artifact_binding')
            for binding in evidence.values():
                path = Path(binding['path'])
                if not path.is_file() or digest(path.read_bytes()) != binding['sha256']:
                    violations.append('route_artifact_changed_or_missing')
            if any(call.get(k) != v for k, v in receipt['parameters'].items()):
                violations.append('dispatch_route_mismatch')
            # Desktop rollouts may store a gAAAA... opaque envelope, not plaintext.
            # Do not decrypt it or claim its contents match the planned message.
            if call.get('message', '').startswith('gAAAA'):
                message_status = 'unverifiable_opaque_log'
            elif digest(call.get('message', '').encode()) != receipt['message_sha256']:
                message_status = 'mismatch'
                violations.append('dispatch_message_changed_after_preflight')
            else:
                message_status = 'match'
            if not timestamp or datetime.fromisoformat(receipt['checked_at']) >= datetime.fromisoformat(timestamp.replace('Z', '+00:00')):
                violations.append('preflight_not_before_dispatch')
        for key in ['model', 'reasoning_effort', 'fork_turns']:
            if key not in call:
                violations.append('missing_' + key)
        if call.get('fork_turns') != 'none':
            violations.append('fork_turns_must_be_none')
        response = responses.get(data.get('call_id'))
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                response = None
        reference = (response.get('agent_id') or response.get('task_name')) if isinstance(response, dict) else None
        if not reference:
            violations.append('agent_reference_unconfirmed')
        entry = runtime.get(reference, {})
        metadata = entry.get('metadata', {})
        agent_id = metadata.get('id') or (response.get('agent_id') if isinstance(response, dict) else None)
        observed = entry.get('observed', [])
        if metadata.get('agent_path') and (not parent_id or metadata.get('parent_thread_id') != parent_id):
            violations.append('child_parent_binding_unconfirmed')
            observed = []
        status = 'unknown'
        if observed:
            status = 'match' if all(all(context.get(k) is not None for k in ['model', 'reasoning_effort'])
                                    for context in observed) else 'unknown'
            if any(context[k] != call.get(k) for context in observed
                   for k in ['model', 'reasoning_effort'] if context.get(k) is not None):
                status = 'mismatch'
                violations.append('runtime_request_mismatch')
        results.append({'call_id': data.get('call_id'), 'agent_id': agent_id, 'agent_reference': reference,
                        'task_name': call.get('task_name'),
                        'request': {k: call.get(k) for k in ['model', 'reasoning_effort', 'fork_turns']},
                        'source': {'path': str(rollout.resolve()), 'line': number},
                        'agent_binding': metadata, 'runtime_records': observed,
                        'runtime_status': status, 'message_status': message_status,
                        'upstream_identity': None, 'violations': violations})
        findings.extend({'task_name': call.get('task_name'), 'code': v} for v in violations)
    for name in receipts.keys() - used:
        findings.append({'task_name': name, 'code': 'route_without_dispatch'})
    if not calls:
        findings.append({'task_name': None, 'code': 'no_dispatch_evidence'})
    return {'protocol_status': 'failed' if findings else 'passed',
            'scope': str(rollout.resolve()), 'dispatches': results, 'violations': findings,
            'unverified': [{'task_name': r['task_name'], 'field': field}
                           for r in results
                           for field in ['runtime_status', 'message_status']
                           if r[field] in {'unknown', 'unverifiable_opaque_log'}],
            'upstream_identity': 'unknown', 'enforcement': 'audit_only_not_tool_interception'}


def write_json(path, result):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path, nargs='?')
    parser.add_argument('--config', type=Path, default=Path(__file__).parents[1] / 'routing.json')
    parser.add_argument('--role-config', type=Path)
    parser.add_argument('--dispatch-file', type=Path)
    parser.add_argument('--capabilities', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--audit-rollout', type=Path)
    parser.add_argument('--records', type=Path, nargs='+')
    parser.add_argument('--child-rollout', type=Path, action='append', default=[])
    args = parser.parse_args()
    role = None
    if args.role_config:
        import tomllib
        role = tomllib.loads(args.role_config.read_text(encoding='utf-8'))
    try:
        if args.audit_rollout:
            if args.task or args.dispatch_file or not args.records:
                raise ValueError('audit requires --records and no routing task/dispatch')
            result = audit_dispatches(args.audit_rollout, [read_json(p) for p in args.records], args.child_rollout)
        else:
            if not args.task or not args.task.is_absolute():
                raise ValueError('routing task must be a real absolute path')
            result = route(read_json(args.task), read_json(args.config), role)
            result['route_evidence'] = {k: {'path': str(p.resolve()), 'sha256': digest(p.read_bytes())}
                                        for k, p in [('task', args.task), ('config', args.config)]}
            if args.dispatch_file:
                if not args.capabilities or not args.output:
                    raise ValueError('preflight requires --capabilities and --output')
                result['preflight'] = preflight(result, read_json(args.dispatch_file), read_json(args.capabilities))
                result['route_evidence']['capabilities'] = {
                    'path': str(args.capabilities.resolve()), 'sha256': digest(args.capabilities.read_bytes())}
        if args.output:
            write_json(args.output, result)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('protocol_status') == 'failed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
