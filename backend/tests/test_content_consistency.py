"""
内容一致性验证测试
测试内容-学科-主题的一致性检测
"""

import pytest
from content_consistency_validator import content_validator, ContentMismatchType
from discipline_config import DisciplineType


class TestContentConsistency:
    """内容一致性测试类"""
    
    def test_language_course_with_physics_content(self):
        """测试语言课程包含物理内容时的检测"""
        mismatches = content_validator.validate_content_consistency(
            course_name="英语语法原理与应用",
            course_topic="语法规则",
            discipline_type=DisciplineType.HUMANITIES,
            generated_content="麦克斯韦方程组描述了电磁场的基本规律。电场和磁场满足波动方程...",
            node_name="语法基础"
        )
        
        # 应该检测到学科不匹配
        assert len(mismatches) > 0
        assert any(m.type == ContentMismatchType.DISCIPLINE_MISMATCH for m in mismatches)
        
        # 应该有严重级别的警告
        critical_issues = [m for m in mismatches if m.severity == "critical"]
        assert len(critical_issues) > 0
    
    def test_math_course_with_grammar_content(self):
        """测试数学课程包含语法内容时的检测"""
        mismatches = content_validator.validate_content_consistency(
            course_name="高等数学",
            course_topic="微积分",
            discipline_type=DisciplineType.NATURAL_SCIENCE,
            generated_content="语法是语言的规则系统，包括词法和句法两个方面。主语和谓语必须保持一致...",
            node_name="导数概念"
        )
        
        # 应该检测到学科不匹配
        assert len(mismatches) > 0
        assert any(m.type == ContentMismatchType.DISCIPLINE_MISMATCH for m in mismatches)
    
    def test_correct_language_content(self):
        """测试正确的语言课程内容"""
        mismatches = content_validator.validate_content_consistency(
            course_name="英语语法原理与应用",
            course_topic="语法规则",
            discipline_type=DisciplineType.HUMANITIES,
            generated_content="英语语法包括词法和句法两大部分。词法研究词的构成、分类和变化规则...",
            node_name="语法基础"
        )
        
        # 不应该有严重问题
        critical_issues = [m for m in mismatches if m.severity == "critical"]
        assert len(critical_issues) == 0
    
    def test_topic_relevance_detection(self):
        """测试主题相关性检测"""
        mismatches = content_validator.validate_content_consistency(
            course_name="Python编程基础",
            course_topic="Python语言",
            discipline_type=DisciplineType.ENGINEERING,
            generated_content="Java是一种广泛使用的编程语言，具有跨平台特性。它由Sun公司开发...",
            node_name="Python简介"
        )
        
        # 应该检测到主题不匹配
        assert any(m.type == ContentMismatchType.TOPIC_MISMATCH for m in mismatches)
    
    def test_validation_report_generation(self):
        """测试验证报告生成"""
        mismatches = content_validator.validate_content_consistency(
            course_name="英语语法",
            course_topic="语法",
            discipline_type=DisciplineType.HUMANITIES,
            generated_content="麦克斯韦方程组...",
            node_name="语法基础"
        )
        
        report = content_validator.generate_validation_report(mismatches)
        
        assert report["status"] in ["fail", "warning", "info"]
        assert "message" in report
        assert "summary" in report
        assert "issues" in report
        assert report["summary"]["total"] == len(mismatches)


class TestDisciplineKeywords:
    """学科关键词测试类"""
    
    def test_natural_science_keywords(self):
        """测试自然科学关键词检测"""
        content = "根据牛顿第二定律 F=ma，我们可以推导出运动方程..."
        
        mismatches = content_validator.validate_content_consistency(
            course_name="英语语法",
            course_topic="语法",
            discipline_type=DisciplineType.HUMANITIES,
            generated_content=content,
            node_name="测试"
        )
        
        # 应该检测到物理关键词
        assert any("物理" in m.message or "自然科学" in m.message for m in mismatches)
    
    def test_humanities_keywords(self):
        """测试人文科学关键词检测"""
        content = "语法规则包括主谓一致、时态呼应等基本原则..."
        
        mismatches = content_validator.validate_content_consistency(
            course_name="英语语法",
            course_topic="语法",
            discipline_type=DisciplineType.HUMANITIES,
            generated_content=content,
            node_name="测试"
        )
        
        # 不应该有严重问题
        critical_issues = [m for m in mismatches if m.severity == "critical"]
        assert len(critical_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
