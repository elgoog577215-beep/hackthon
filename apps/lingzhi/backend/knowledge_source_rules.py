"""Narrow, versioned counterexamples; never rewrite a frozen teaching source."""
from copy import deepcopy
import hashlib
import re
import unicodedata


def _compact(value):
    return re.sub(r'[\s`*“”‘’]', '', unicodedata.normalize('NFKC', str(value))).replace(chr(34), '').replace(chr(39), '')


def claims_parenthesis_substring_ban(point, source_text):
    meaning = _compact(point.get('meaning', '')) + _compact(point.get('constraints', '')) + _compact(point.get('value', ''))
    scope = _compact(point.get('conditions', []))
    return (point.get('form') in {'definition', 'fact'} and bool(re.search(r'匹配|括号', str(point.get('subject', ''))))
        and '括号' in source_text and '不能出现)(' in meaning
        and not re.search(r'单对|仅一对|每对|每个.{0,3}对|长度(?:为)?2|开头|前缀|初始|未匹配', scope)
        and not re.search(r'说法.{0,4}(?:错误|不正确|不准确)|不应将|不能将', meaning))


def quarantine_source_errors(response, passages):
    output = deepcopy(response); records = []; traces = output.get('_content_review_trace'); cursor = 0; kept_traces = []
    for key, entry in output['passages'].items():
        source = passages[key]; source_text = source['text']; kept = []
        for ordinal, point in enumerate(entry['points']):
            trace = traces[cursor] if traces is not None else None; cursor += 1
            refuted = claims_parenthesis_substring_ban(point, source_text) and '字符串' in source_text and '不能出现)(' in _compact(source_text)
            if not refuted:
                kept.append(point)
                if trace is not None: kept_traces.append(trace)
                continue
            detail = '将“不能出现)(”理解为任意子串禁令会被合法串()()反驳；需核对原文歧义及前缀条件，未将该无条件定义加入知识候选。'
            witness = '()()'; balances = []; balance = 0
            for char in witness:
                balance += 1 if char == '(' else -1
                balances.append(balance)
            assert min(balances) >= 0 and balance == 0 and ')(' in witness
            record = {'rule_id': 'balanced_parenthesis_substring_counterexample_v1', 'passage_key': key,
                'source_key': source.get('source_key', key.split('.')[0]), 'point_ordinal': ordinal,
                'point': deepcopy(point), 'status': 'excluded_from_candidate', 'counterexample': witness,
                'prefix_balances': balances, 'verification_scope': 'unqualified_substring_interpretation',
                'source_hash': hashlib.sha256(source_text.encode()).hexdigest(), 'detail': detail}
            records.append(record)
            issue = {'passage_key': key, 'kind': 'suspected_error', 'detail': detail}
            if issue not in output['source_issues']: output['source_issues'].append(issue)
        entry['points'] = kept
        if not kept and any(record['passage_key'] == key for record in records):
            entry['note'] = {'handling': 'context', 'reason': '无条件候选解释被可复查反例排除；原文及反例保留为来源疑点。'}
    if traces is not None: output['_content_review_trace'] = kept_traces
    return output, records


def annotate_verified_issues(result, records):
    for issue in result.get('source_issues', []):
        for record in records:
            if issue['source_key'] == record['source_key'] and issue['detail'] == record['detail']:
                issue.update(verification_status='program_counterexample_verified', verification_origin=record['rule_id'],
                    verification={'counterexample': record['counterexample'], 'prefix_balances': record['prefix_balances'],
                                  'scope': record['verification_scope'], 'source_hash': record['source_hash']})
