"""Conservative predicate roles for proposals, not a general theorem prover."""
import re


def _norm(text):
    return re.sub(r'[\s`*$]+', '', str(text)).casefold()


def access_order(point):
    if point.get('form') != 'fact' or not re.search(r'原则|核心特征|存取规则', str(point.get('property', ''))): return None
    value = str(point.get('value', ''))
    if re.search(r'LIFO|后进先出', value, re.I) and not re.search(r'FIFO|先进先出', value, re.I): return 'LIFO'
    if re.search(r'FIFO|先进先出', value, re.I) and not re.search(r'LIFO|后进先出', value, re.I): return 'FIFO'
    return None


def _operation(point):
    if point.get('form') != 'fact' or not re.search(r'操作|检查|判空|判满', str(point.get('property', ''))): return None
    text = ' '.join([*point.get('subjects', []), str(point.get('property', ''))])
    return next((term for term in ('入栈','出栈','入队','出队','判空','判满','压栈','弹出','popleft()','stack.pop()','stack.append(...)') if term in text), None)


def _operation_used(source, target):
    operation = _operation(source)
    if not operation: return False
    target_text = str(target['statement']) + ' '.join(target.get('steps', []))
    if '栈帧' in source['statement'] and '栈帧' not in target_text: return False
    if operation == '判空':
        if '队列' in source['statement']: return bool(re.search(r'队列|queue', target_text)) and bool(re.search(r'空|empty|while queue|not queue', target_text))
        if '栈' in source['statement']: return bool(re.search(r'栈|stack', target_text)) and bool(re.search(r'空|empty|while stack|not stack', target_text))
    if operation in target_text: return True
    patterns = {'入栈': r'stack\.append\(', '出栈': r'stack\.pop\(\)', '入队': r'queue\.append\(',
                '出队': r'queue\.(?:popleft\(\)|pop\(0\))'}
    return bool(operation in patterns and re.search(patterns[operation], target_text))


def _definition_entails_order(source, target):
    order = access_order(target)
    if not order or source.get('form') != 'definition' or source.get('subjects') != target.get('subjects'): return False
    text = source['statement']
    if order == 'LIFO': return bool(re.search(r'(?:仅允许|仅能|只允许|只在|仅在).*(?:栈顶|一端).*插入.*删除', text))
    return bool(re.search(r'队尾.*插入.*队头.*删除|一端.*插入.*另一端.*删除', text))


def predicate_contract(source, target):
    """Return only supported kinds; a shared subject alone is insufficient."""
    if source['knowledge_id'] == target['knowledge_id']: return None
    target_text = target['statement'] + ' '.join(target.get('conditions', []))
    if _definition_entails_order(source, target):
        return {'allowed_types': ['derives'], 'allowed_necessities': [], 'basis': 'single_end_or_fifo_definition_entails_order'}
    if target.get('form') == 'procedure':
        order = access_order(source)
        body = _norm(target_text)
        used_order = (order == 'LIFO' and ('入栈' in body and '出栈' in body or 'stack.append(' in body and 'stack.pop()' in body)
            or order == 'FIFO' and ('入队' in body and '出队' in body or 'popleft()' in body or 'queue.pop(0)' in body))
        if used_order or _operation_used(source, target):
            return {'allowed_types': ['applies_to'], 'allowed_necessities': [], 'basis': 'operation_or_order_used_by_frozen_procedure'}
        if source.get('form') == 'procedure' and any(re.fullmatch(r'[A-Za-z_]\w*', s) and s+'(' in target_text for s in source.get('subjects', [])):
            return {'allowed_types': ['applies_to'], 'allowed_necessities': [], 'basis': 'procedure_explicitly_called'}
    same_object = bool(set(source.get('subjects', [])) & set(target.get('subjects', [])))
    source_named = source['name'] != target['name'] and len(source['name']) >= 2 and source['name'] in target_text
    target_operation_uses_object = _operation(target) is not None and any(s in target['statement'] for s in source.get('subjects', []))
    definition_used = source.get('form') == 'definition' and (same_object or target_operation_uses_object
        or target.get('form') == 'procedure' and any(s in target_text for s in source.get('subjects', [])))
    operation = _operation(source)
    operation_referenced = operation and operation in target['statement'] and _operation_used(source, target)
    untyped_named = not source.get('form') and source_named and bool(re.search(r'使用|基础|依赖|前提', target_text))
    if definition_used or source_named or operation_referenced or untyped_named:
        necessary = any(source['name'] in condition and re.search(r'必须|必要|前提|需要', condition) for condition in target.get('conditions', []))
        return {'allowed_types': ['prerequisite'], 'allowed_necessities': ['recommended', 'required'] if necessary else ['recommended'],
                'basis': 'explicit_definition_operation_or_named_concept_reference'}
    return None
