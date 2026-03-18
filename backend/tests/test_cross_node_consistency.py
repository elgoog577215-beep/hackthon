"""
跨节点一致性检查测试

测试 ContentConsistencyValidator 的 check_cross_node_consistency 方法，
包括重复案例检测、矛盾定义检测和断裂引用检测。
"""

import pytest
from content_consistency_validator import ContentConsistencyValidator
from knowledge_graph import GlobalKnowledgeGraph


class TestDuplicateExampleDetection:
    """重复案例检测测试"""

    def test_detects_duplicate_examples_across_nodes(self):
        """跨节点的相似案例应被检测为重复"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": (
                    "**案例**：在一个电商平台中，用户下单后系统需要进行库存检查、"
                    "支付处理和物流调度三个步骤，这是一个典型的分布式事务场景。"
                ),
            },
            {
                "node_id": "node_2",
                "node_name": "第二章",
                "node_content": (
                    "**案例**：在一个电商平台中，用户下单后系统需要进行库存检查、"
                    "支付处理和物流调度三个步骤，这是一个典型的分布式事务应用。"
                ),
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        dup_issues = [i for i in issues if i.issue_type == "duplicate_example"]
        assert len(dup_issues) >= 1
        assert dup_issues[0].auto_fixable is True
        assert "node_1" in dup_issues[0].node_ids
        assert "node_2" in dup_issues[0].node_ids

    def test_no_duplicate_for_different_examples(self):
        """不同的案例不应被标记为重复"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": (
                    "**案例**：在银行转账系统中，从账户A向账户B转账需要保证原子性，"
                    "即要么两个账户同时更新，要么都不更新，这是ACID事务的核心要求。"
                ),
            },
            {
                "node_id": "node_2",
                "node_name": "第二章",
                "node_content": (
                    "**案例**：社交媒体平台的推荐算法通过分析用户的浏览历史、"
                    "点赞记录和社交关系来预测用户可能感兴趣的内容，提升用户体验。"
                ),
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        dup_issues = [i for i in issues if i.issue_type == "duplicate_example"]
        assert len(dup_issues) == 0

    def test_skips_same_node_examples(self):
        """同一节点内的案例不应被标记为跨节点重复"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": (
                    "**案例**：在电商平台中用户下单后系统需要进行库存检查和支付处理\n\n"
                    "**示例**：在电商平台中用户下单后系统需要进行库存检查和支付处理"
                ),
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        dup_issues = [i for i in issues if i.issue_type == "duplicate_example"]
        assert len(dup_issues) == 0


class TestContradictingDefinitionDetection:
    """矛盾定义检测测试"""

    def test_detects_contradicting_definitions(self):
        """同一术语在不同节点有不同定义应被检测"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": "**多态**：指同一个方法调用在不同对象上有不同的行为表现",
            },
            {
                "node_id": "node_2",
                "node_name": "第二章",
                "node_content": "**多态**：指一种数据类型可以存储多种不同类型的值的能力",
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        contra_issues = [i for i in issues if i.issue_type == "contradicting_definition"]
        assert len(contra_issues) >= 1
        assert contra_issues[0].severity == "critical"
        assert contra_issues[0].auto_fixable is False

    def test_no_contradiction_for_similar_definitions(self):
        """相似的定义不应被标记为矛盾"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": "**封装**：将数据和操作数据的方法绑定在一起，隐藏内部实现细节",
            },
            {
                "node_id": "node_2",
                "node_name": "第二章",
                "node_content": "**封装**：将数据和操作数据的方法绑定在一起，对外隐藏内部实现细节",
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        contra_issues = [i for i in issues if i.issue_type == "contradicting_definition"]
        assert len(contra_issues) == 0


class TestBrokenReferenceDetection:
    """断裂引用检测测试"""

    def test_detects_broken_reference(self):
        """引用不存在的章节应被检测"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章 基础概念",
                "node_content": "关于高级用法，参见《第五章 高级特性》中的详细说明。",
            },
        ]
        section_titles = ["第一章 基础概念", "第二章 进阶内容"]

        issues = validator.check_cross_node_consistency(nodes, section_titles=section_titles)
        broken_issues = [i for i in issues if i.issue_type == "broken_reference"]
        assert len(broken_issues) >= 1
        assert broken_issues[0].auto_fixable is True

    def test_no_broken_reference_for_valid_title(self):
        """引用存在的章节不应被标记为断裂"""
        validator = ContentConsistencyValidator()
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章 基础概念",
                "node_content": "关于进阶内容，参见《第二章 进阶内容》中的详细说明。",
            },
        ]
        section_titles = ["第一章 基础概念", "第二章 进阶内容"]

        issues = validator.check_cross_node_consistency(nodes, section_titles=section_titles)
        broken_issues = [i for i in issues if i.issue_type == "broken_reference"]
        assert len(broken_issues) == 0


class TestKnowledgeGraphIntegration:
    """知识图谱集成测试"""

    def test_detects_duplicate_with_knowledge_graph(self):
        """通过知识图谱检测与已注册案例的重复"""
        kg = GlobalKnowledgeGraph()
        kg.register_example(
            title="电商平台分布式事务",
            summary=(
                "在一个电商平台中，用户下单后系统需要进行库存检查、"
                "支付处理和物流调度三个步骤，这是一个典型的分布式事务场景。"
            ),
            node_id="existing_node",
        )

        validator = ContentConsistencyValidator(knowledge_graph=kg)
        nodes = [
            {
                "node_id": "new_node",
                "node_name": "新章节",
                "node_content": (
                    "**案例**：在一个电商平台中，用户下单后系统需要进行库存检查、"
                    "支付处理和物流调度三个步骤，这是一个典型的分布式事务场景。"
                ),
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        dup_issues = [i for i in issues if i.issue_type == "duplicate_example"]
        assert len(dup_issues) >= 1

    def test_detects_contradiction_with_knowledge_graph(self):
        """通过知识图谱检测与已注册概念的矛盾定义"""
        kg = GlobalKnowledgeGraph()
        kg.register_concept(
            name="多态",
            definition="指同一个方法调用在不同对象上有不同的行为表现",
            node_id="existing_node",
        )

        validator = ContentConsistencyValidator(knowledge_graph=kg)
        nodes = [
            {
                "node_id": "new_node",
                "node_name": "新章节",
                "node_content": "**多态**：指一种数据类型可以存储多种不同类型的值的能力",
            },
        ]

        issues = validator.check_cross_node_consistency(nodes)
        contra_issues = [i for i in issues if i.issue_type == "contradicting_definition"]
        assert len(contra_issues) >= 1

    def test_broken_reference_uses_knowledge_graph_concepts(self):
        """知识图谱中的概念应作为有效引用"""
        kg = GlobalKnowledgeGraph()
        kg.register_concept(
            name="设计模式",
            definition="软件设计中常见问题的通用解决方案",
            node_id="concept_node",
        )

        validator = ContentConsistencyValidator(knowledge_graph=kg)
        nodes = [
            {
                "node_id": "node_1",
                "node_name": "第一章",
                "node_content": "关于更多信息，参见《设计模式》中的详细说明。",
            },
        ]

        issues = validator.check_cross_node_consistency(
            nodes, section_titles=["第一章"]
        )
        broken_issues = [i for i in issues if i.issue_type == "broken_reference"]
        assert len(broken_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
