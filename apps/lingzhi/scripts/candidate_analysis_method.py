from __future__ import annotations
from copy import deepcopy
import json
from typing import Any

async def analyze_teacher_course_change(
        self,
        overview: dict[str, Any],
        ranked_candidates: list[dict[str, Any]],
        instruction: str,
    ) -> dict[str, Any] | None:
        """Judge one bounded batch of a complete whole-course impact scan.

        The index is only a speed layer. The model receives cross-asset
        candidates and decides which units are genuinely affected; returned
        IDs must come from the supplied candidate set and are validated again
        by the orchestration service.
        """
        scan_candidates = []
        for item in ranked_candidates:
            item = deepcopy(item)
            if isinstance(item.get('content'), str):
                # Full editable text is already represented by content fragments.
                # Keep field names for exact patches without sending it twice.
                item['editable_field_names'] = list((item.pop('editable_fields', None) or {}).keys())
                item.pop('summary', None)
                item.pop('rank_score', None)
            scan_candidates.append(item)
        prompt = (
            "�������ʦ�����ſγ̵��޸�Ҫ��ֻ���һ�� JSON ����\n"
            f"��ʦԭ����{instruction}\n\n"
            "�γ����ʲ��ſ���\n"
            f"{json.dumps(overview, ensure_ascii=False)}\n\n"
            "�����������ϵ��չ��ĺ�ѡ��Ԫ��\n"
            f"{json.dumps(scan_candidates, ensure_ascii=False)}\n\n"
            "�����ֶΣ�interpreted_goal��signal_kind��signal_confidence��"
            "hard_constraints��soft_preferences��protected_requirements��assumptions��"
            "blocking_questions��clarifications��affected_units��structure��"
            "signal_kind ֻ���� semantic��structural��mixed��uncertain��"
            "affected_units ÿ��ֻ�ܰ�����ѡ����ʵ���ڵ� unit_id���Լ� disposition��"
            "reason��confidence��content_patches��disposition ֻ���� reuse_exact��reuse_rebind��"
            "rewrite_partial��regenerate��retire��blocked��"
            "��� course_content ��ѡ�� editable_fields ���㹻֧�ž�ȷ�޸ģ�"
            "content_patches �������� {field,before,after,replace_all}��field ֻ����"
            "markdown��text��content��title��summary��before �������ִ����ڸú�ѡ"
            "editable_fields �С�����ȫ���滻ҪΪÿ����ʵ���еĵ�Ԫ�ֱ𷵻� patch��"
            "���ܿɿ��γ����ֺ�ѡʱ content_patches=[]�����ò²�ԭ�ġ�"
            "��Ƭģʽ�� content �ǵ�ǰԭ�ģ�editable_field_names �ǿɱ༭�ֶ�����"
            "before ������������ content��ʹ����̿�Ψһ��λ��Ƭ�Σ�����������ԭ�ġ�"
            "������ֻ�ж��޸�Ӱ�죬��Ҫ��ÿ�����������ʵ����Ŀ���ο��𰸻��δ��롣"
            "����ʵ������������ͨ���������н������޸ģ������ڲ�ֻ��������Σ�"
            "ֻ����ʦ��ȷҪ��ı佲�β㼶��������˳��ʱ������ṹ�ؽ���"
            "structure ���� required��reason��affected_node_ids��retire_node_ids��proposed_outline��"
            "���ṹ���䣬required=false �� proposed_outline=[]�����½�Ҫ�ϲ���ɾ����"
            "��֡��ƶ����ؽ����ȸ������ĵ������¿γ���������ֻ���ر仯�ڵ㣩��"
            "proposed_outline ÿ����� provisional_id��title��parent_ref��"
            "source_node_ids��learning_focus��ɾ���ľɽڵ� ID ����������� retire_node_ids��"
            "�ϲ�ʱ�½ڵ�����ȫ����Դ ID�����ʱ����½ڵ������ͬһ��Դ ID��"
            "��Ҫ��Ϊ��ʦ��ǲ�רҵ�ͻ�е��С��Χ��Ҫ��Ŀ���ƶϿ�����Ӱ����ʲ���"
            "����Ҫ�ѽ���ͬ�ʳ��ֵĵ�Ԫ��Ϊ�ظġ��޷���ȫ�ƶ��һ�ı�ṹʱ��"
            "��������� clarifications��blocking_questions ֻ�����Ǵ��ַ������飬"
            "���������зŶ�����ʽ���ݲ����ڱ����豻�޸ġ�"
            "��Ҫ��ʦ����ʱ��clarifications ���� 1��3 ������Ӱ�췽�������⣻ÿ�����"
            "question_id��prompt��response_type=single_choice��required=true �� 2��4 �� options��"
            "ÿ�� option ���� option_id��label��impact��recommended�����һ�� recommended��"
            "����γ̸ſ������� clarification_answer_snapshot������ decision_facts ����ʦ"
            "�Ѿ�����ȷ�ϵ�ӲԼ�����������½��͡����ǻ��ٴ�ѯ��ͬһ���⡣"
        )
        response = await self._call_llm(
            prompt,
            system_prompt=(
                "���Ǹ�У�γ��ܱ�����Ӱ�����ʦ�����ڿγ̴�١��̰������塢"
                "PPT�����֮��׷����������������������ٻأ��㸺�����������жϣ�"
                "������ʦԭ���������ж�ԭ�򣬲��ѽṹ���������ݵ����ֿ���"
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            max_tokens=4200,
            max_input_tokens=11000,
            max_attempts=1,
            reject_truncated=True,
            raise_on_failure=True,
            json_mode=True,
            model_role="teacher_course_change_impact",
            wait_for_capacity=True,
        )
        parsed = self._extract_json(response or "")
        return parsed if isinstance(parsed, dict) else None

