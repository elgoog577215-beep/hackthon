"""
学科检测回归测试套件
确保学科检测的准确性和稳定性
"""

import pytest
from discipline_config import detect_discipline_type, DisciplineType, get_discipline_config


class TestDisciplineDetection:
    """学科检测测试类"""
    
    # 测试用例：课程名称 -> 期望的学科类型
    TEST_CASES = [
        # 人文科学类
        ("英语语法原理与应用", DisciplineType.HUMANITIES),
        ("英语写作技巧", DisciplineType.HUMANITIES),
        ("日语入门", DisciplineType.HUMANITIES),
        ("法语精读", DisciplineType.HUMANITIES),
        ("德语语法", DisciplineType.HUMANITIES),
        ("西班牙语会话", DisciplineType.HUMANITIES),
        ("语言学导论", DisciplineType.HUMANITIES),
        ("西方哲学史", DisciplineType.HUMANITIES),
        ("文学批评", DisciplineType.HUMANITIES),
        ("艺术鉴赏", DisciplineType.HUMANITIES),
        ("修辞学", DisciplineType.HUMANITIES),
        ("翻译理论与实践", DisciplineType.HUMANITIES),
        
        # 工程技术类
        ("Python编程基础", DisciplineType.ENGINEERING),
        ("数据结构", DisciplineType.ENGINEERING),
        ("机器学习", DisciplineType.ENGINEERING),
        ("深度学习", DisciplineType.ENGINEERING),
        ("软件工程", DisciplineType.ENGINEERING),
        ("算法设计", DisciplineType.ENGINEERING),
        ("计算机网络", DisciplineType.ENGINEERING),
        ("数据库系统", DisciplineType.ENGINEERING),
        ("Java程序设计", DisciplineType.ENGINEERING),
        ("React前端开发", DisciplineType.ENGINEERING),
        ("人工智能导论", DisciplineType.ENGINEERING),
        
        # 自然科学类
        ("高等数学", DisciplineType.NATURAL_SCIENCE),
        ("大学物理", DisciplineType.NATURAL_SCIENCE),
        ("有机化学", DisciplineType.NATURAL_SCIENCE),
        ("生物化学", DisciplineType.NATURAL_SCIENCE),
        ("量子力学", DisciplineType.NATURAL_SCIENCE),
        ("电磁学", DisciplineType.NATURAL_SCIENCE),
        ("微积分", DisciplineType.NATURAL_SCIENCE),
        ("线性代数", DisciplineType.NATURAL_SCIENCE),
        
        # 社会科学类
        ("社会学概论", DisciplineType.SOCIAL_SCIENCE),
        ("心理学基础", DisciplineType.SOCIAL_SCIENCE),
        ("经济学原理", DisciplineType.SOCIAL_SCIENCE),
        ("政治学", DisciplineType.SOCIAL_SCIENCE),
        ("传播学", DisciplineType.SOCIAL_SCIENCE),
        ("教育学", DisciplineType.SOCIAL_SCIENCE),
        
        # 应用技能类
        ("摄影技巧", DisciplineType.APPLIED_SKILL),
        ("烹饪艺术", DisciplineType.APPLIED_SKILL),
        ("书法入门", DisciplineType.APPLIED_SKILL),
        ("绘画基础", DisciplineType.APPLIED_SKILL),
        ("乐器演奏", DisciplineType.APPLIED_SKILL),
        
        # 传播类
        ("新闻写作", DisciplineType.COMMUNICATION),
        ("公共关系", DisciplineType.COMMUNICATION),
        ("广告学", DisciplineType.COMMUNICATION),
        ("媒体研究", DisciplineType.COMMUNICATION),
    ]
    
    @pytest.mark.parametrize("course_name,expected", TEST_CASES)
    def test_discipline_detection(self, course_name, expected):
        """测试学科检测准确性"""
        result = detect_discipline_type(course_name)
        assert result == expected, f"'{course_name}' 应该被识别为 {expected.value}, 但实际是 {result.value}"
    
    def test_no_false_positives(self):
        """测试不会产生明显的误分类"""
        # 语言类课程不应该被识别为自然科学
        language_courses = ["英语语法", "日语", "法语", "德语", "西班牙语"]
        for course in language_courses:
            result = detect_discipline_type(course)
            assert result != DisciplineType.NATURAL_SCIENCE, f"'{course}' 不应该被识别为自然科学"
            assert result in [DisciplineType.HUMANITIES, DisciplineType.COMMUNICATION], f"'{course}' 应该属于人文或传播类"


class TestDisciplineConfig:
    """学科配置测试类"""
    
    def test_all_disciplines_have_required_sections(self):
        """测试所有学科都有必需的内容板块"""
        for dtype in DisciplineType:
            config = get_discipline_config(dtype)
            assert len(config.content_sections) >= 4, f"{dtype.value} 应该有至少4个内容板块"
            
            # 检查是否有板块定义
            section_names = [s.name for s in config.content_sections]
            assert len(section_names) == len(set(section_names)), f"{dtype.value} 有重复的内容板块"
    
    def test_humanities_has_language_sections(self):
        """测试人文科学类有适合语言学习的板块"""
        config = get_discipline_config(DisciplineType.HUMANITIES)
        section_names = [s.name for s in config.content_sections]
        
        # 应该包含适合语言学习的板块
        language_related = ["实例", "例", "应用", "练习"]
        has_language_section = any(
            any(lr in name for lr in language_related) 
            for name in section_names
        )
        assert has_language_section, "人文科学应该包含实例/应用相关的内容板块"
    
    def test_natural_science_has_math_sections(self):
        """测试自然科学类有数学相关内容"""
        config = get_discipline_config(DisciplineType.NATURAL_SCIENCE)
        section_names = [s.name for s in config.content_sections]
        
        # 应该包含定理、证明等数学相关内容
        math_related = ["定理", "证明", "推导", "公式"]
        has_math_section = any(
            any(mr in name for mr in math_related) 
            for name in section_names
        )
        assert has_math_section, "自然科学应该包含定理/证明相关的内容板块"


class TestContentValidation:
    """内容验证测试类"""
    
    def test_content_discipline_mismatch_detection(self):
        """测试内容-学科不匹配检测"""
        # 模拟检测：如果课程名是语言类但内容包含物理公式，应该报警
        language_course = "英语语法"
        physics_content = "麦克斯韦方程组 电磁波 电场磁场"
        
        # 这里可以添加更复杂的检测逻辑
        physics_keywords = ["电磁", "麦克斯韦", "电场", "磁场", "波动方程"]
        has_physics = any(kw in physics_content for kw in physics_keywords)
        
        # 语言课程不应该包含物理内容
        assert not has_physics, f"'{language_course}' 不应该包含物理相关内容"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
