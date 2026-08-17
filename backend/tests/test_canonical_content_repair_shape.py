"""块级公式围栏形状修复的回归测试。

语料不是编的：每个 `SPLIT_*` 常量都是从 8 门真实课程里逐字取出的片段，
对应打印关卡实测报出的那 8 个失败节点、共 27 处拆分。

最要紧的一条是 `test_empty_display_block_no_longer_swallows_following_content`
——空 `$$` 对会吞掉后续正文与标题。它最容易复发也最难被发现：
`$$` 总数是**偶数**，所以任何奇偶校验都看不见；页面上表现为"公式后面少了
一段"，而不是报错。
"""

from canonical_content_repair import (
    repair_display_math_shape,
    repair_split_display_math,
)

# 《量子力学》2.4 一维无限深势阱：前缀 + cases，尾部多一个空块。
SPLIT_CASES = """其势能函数定义如下：

$$
V(x) =

$$
\\begin{cases}
0, & \\text{当 } 0 < x < L \\\\
\\infty, & \\text{当 } x \\leq 0 \\text{ 或 } x \\geq L
\\end{cases}
$$

$$

此势阱具有无限深的性质。

## 深度原理
"""

# 《量子力学》1.9 算子代数：泡利矩阵被拆成 7 段的链式形态。
SPLIT_CHAIN = """考虑泡利矩阵：

$$
\\sigma_x =
$$
\\begin{pmatrix} 0 & 1 \\\\ 1 & 0 \\end{pmatrix}
$$
, \\quad \\sigma_y =
$$
\\begin{pmatrix} 0 & -i \\\\ i & 0 \\end{pmatrix}
$$
.
$$

它们满足对易关系。
"""

# 《高等代数》6.1 高斯消元：\\left[ 与 \\right] 被 $$ 从 array 环境上切开。
SPLIT_ARRAY = """将其写成增广矩阵的形式：

$$
\\left[
$$
\\begin{array}{cc|c}
1 & 2 & 3 \\\\
4 & 5 & 6
\\end{array}
$$
\\right]
$$

继续消元。
"""

# 《线性代数》1.7.6：前缀为空的变体（`$$` 紧接着就是环境）。
SPLIT_EMPTY_PREFIX = """基础解系为：

$$

$$
\\begin{bmatrix} -3 \\\\ 0 \\\\ 1 \\end{bmatrix}
$$

$$

这两个向量张成解空间。
"""


def _display_blocks(text: str) -> list[str]:
    """取出所有 `$$...$$` 块的内容，用于断言合并结果。"""
    parts = text.split("$$")
    return [parts[index].strip() for index in range(1, len(parts), 2)]


def test_prefix_and_environment_are_merged_into_one_block():
    """`V(x) =` 与 `\\begin{cases}` 必须回到同一组 `$$` 里。"""
    repaired = repair_display_math_shape(SPLIT_CASES)
    blocks = _display_blocks(repaired)

    assert len(blocks) == 1, f"应只剩一个公式块，实际 {len(blocks)}：{blocks}"
    assert "V(x) =" in blocks[0]
    assert "\\begin{cases}" in blocks[0]
    assert "\\end{cases}" in blocks[0]


def test_empty_display_block_no_longer_swallows_following_content():
    """本文件最重要的一条：空 `$$` 对会吞掉后面的正文和标题。

    多出来的空 `$$` 对开启一个没有闭合的数学块，把后续正文连同 `##` 标题
    一起吸进公式。受控实验证实过：带空对的那份 `## 深度原理` 标题被摧毁，
    不带的完全正常。

    这条最容易复发也最难被发现——`$$` 总数是偶数，奇偶校验看不见它；
    症状是"公式后面少了一段"，不是报错。所以这里同时断言三件事：
    没有空块、正文还在、标题还在，而且它们都在公式**外面**。
    """
    repaired = repair_display_math_shape(SPLIT_CASES)

    # 1. 不再有内容为空的块
    assert not [block for block in _display_blocks(repaired) if not block]
    # 2. 正文与标题仍然存在
    assert "此势阱具有无限深的性质。" in repaired
    assert "## 深度原理" in repaired
    # 3. 且位于所有 `$$` 块之外——被吞进公式时它们会出现在块内容里
    for block in _display_blocks(repaired):
        assert "此势阱具有无限深的性质。" not in block
        assert "## 深度原理" not in block


def test_chained_split_formula_is_merged_as_one():
    """泡利矩阵那种一条公式被拆成 7 段的链式形态。

    最初的实现按「成对」合并，正是漏掉了这种链式变体（以及空前缀变体），
    8 个节点只修好 1 个。所以这条单独守住。
    """
    repaired = repair_display_math_shape(SPLIT_CHAIN)
    blocks = _display_blocks(repaired)

    assert len(blocks) == 1, f"链式公式应合并为一块，实际 {len(blocks)}"
    assert "\\sigma_x" in blocks[0]
    assert "\\sigma_y" in blocks[0]
    assert blocks[0].count("\\begin{pmatrix}") == 2
    assert "它们满足对易关系。" in repaired


def test_sized_delimiters_stay_with_their_environment():
    """`\\left[` / `\\right]` 必须和 array 环境在同一块内。

    被切开时 KaTeX 看到的是「只有 \\left[ 没有 \\right]」，必然报错。
    """
    repaired = repair_display_math_shape(SPLIT_ARRAY)
    blocks = _display_blocks(repaired)

    assert len(blocks) == 1
    assert "\\left[" in blocks[0]
    assert "\\right]" in blocks[0]
    assert "\\begin{array}" in blocks[0]


def test_empty_prefix_variant_is_repaired():
    """前缀为空的变体：`$$` 之后直接就是环境。"""
    repaired = repair_display_math_shape(SPLIT_EMPTY_PREFIX)
    blocks = _display_blocks(repaired)

    assert len(blocks) == 1
    assert "\\begin{bmatrix}" in blocks[0]
    assert "这两个向量张成解空间。" in repaired
    for block in blocks:
        assert "这两个向量张成解空间。" not in block


def test_well_formed_content_is_left_untouched():
    """修复必须是保守的：本来就对的内容一个字都不能改。"""
    good = """正文说明。

$$
V(x) = \\begin{cases}
0, & x < L \\\\
\\infty, & x \\ge L
\\end{cases}
$$

后续正文。

## 标题
"""
    assert repair_display_math_shape(good) == good


def test_inline_math_is_not_touched():
    """行内 `$...$` 不参与块级修复。"""
    text = "波函数在 $x \\leq 0$ 区域为零，其中 $k^2 = 2mE/\\hbar^2$。"
    assert repair_display_math_shape(text) == text


def test_code_fences_are_protected():
    """代码块里的 `$` 不是公式分隔符。

    课程正文里到处是代码块，把 Python 字符串里的 `$` 当成分隔符会毁掉正文。
    打印关卡上踩过一次同类误伤（`reverse_string("1234!@#$")`）。
    """
    text = '''说明：

```python
print("1234!@#$")
print("$#@!4321")
```

结束。
'''
    assert repair_display_math_shape(text) == text


def test_repair_is_idempotent():
    """修复过的内容再修一次不应继续变化。"""
    once = repair_display_math_shape(SPLIT_CASES)
    assert repair_display_math_shape(once) == once


def test_repair_never_drops_prose():
    """任何情况下都不能丢正文——这是修复的底线。"""
    for source in (SPLIT_CASES, SPLIT_CHAIN, SPLIT_ARRAY, SPLIT_EMPTY_PREFIX):
        repaired = repair_display_math_shape(source)
        for line in source.split("\n"):
            stripped = line.strip()
            # 只检查自然语言行：公式行会被合并、`$$` 行会被删，这是预期的。
            if not stripped or stripped.startswith("$$") or "\\" in stripped:
                continue
            assert stripped in repaired, f"丢失正文：{stripped!r}"


def test_split_repair_reports_no_change_for_plain_text():
    """没有块级公式时原样返回，避免无谓改写。"""
    text = "这一节没有任何公式，只有说明文字。"
    assert repair_split_display_math(text) == text
