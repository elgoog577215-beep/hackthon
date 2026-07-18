"""Student-facing projection for structured solution values."""

from __future__ import annotations

from typing import Any


FIELD_LABELS = {
    "zero_vector_in_set": "零向量属于集合",
    "sum": "向量和",
    "scalar_multiple": "数乘结果",
    "basis": "一组基",
    "dimension": "维数",
    "preorder": "前序遍历",
    "inorder": "中序遍历",
    "postorder": "后序遍历",
    "bfs_order": "广度优先遍历",
    "dfs_order": "深度优先遍历",
    "dot_product": "内积",
    "norms_squared": "模长平方",
    "normalized_basis": "标准正交基",
    "target_coordinates": "目标向量的基坐标",
    "coefficients": "坐标系数",
    "reconstructed": "重构结果",
    "dependent": "是否线性相关",
    "relation": "线性关系",
    "rank": "秩",
    "determinant": "行列式",
    "kernel_basis": "核空间的一组基",
    "image_basis": "像空间的一组基",
    "invertible": "是否可逆",
    "eigenvalues": "特征值",
    "eigenvectors": "特征向量",
    "dominant_eigenvalue": "主特征值",
    "solution": "解",
    "residual": "残差",
    "normal_residual": "正规方程检验",
    "singular_values": "奇异值",
    "best_rank_one": "最佳秩一近似",
    "spectral_error": "近似误差",
    "first_direction": "第一个方向",
    "second_orthogonal_direction": "第二个正交方向",
    "second_projection_coefficient": "投影系数",
    "orthogonal_dot_product": "正交性内积检查",
    "condition_probability": "条件概率",
    "probability": "概率",
    "numerator_count": "满足目标事件的结果数",
    "denominator_count": "条件事件的结果数",
    "favorable_count": "有利结果数",
    "sample_space_size": "样本空间大小",
    "range_check": "概率范围检查",
    "product": "矩阵乘积",
    "left_determinant": "左矩阵行列式",
    "output": "输出",
    "stdout": "标准输出",
    "print_return_value": "print 返回值",
    "recommended_option": "推荐方案",
    "score": "得分",
}

SEQUENCE_FIELDS = {
    "preorder",
    "inorder",
    "postorder",
    "bfs_order",
    "dfs_order",
}


def present_solution_value(
    value: Any,
    field_name: str | None = None,
) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(int(value) if isinstance(value, float) and value.is_integer() else value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(
            f"{FIELD_LABELS.get(str(key), _fallback_label(str(key)))}："
            f"{present_solution_value(item, str(key))}"
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return "无"
        if field_name in SEQUENCE_FIELDS:
            return " → ".join(present_solution_value(item) for item in value)
        if all(isinstance(item, (list, tuple)) for item in value):
            return "；".join(_present_vector(item) for item in value)
        if all(isinstance(item, (int, float)) for item in value):
            return _present_vector(value)
        return "、".join(present_solution_value(item) for item in value)
    return str(value)


def present_solution_representation(
    representation: Any,
) -> dict[str, str] | None:
    if not isinstance(representation, dict):
        return None
    kind = str(representation.get("kind") or "")
    if kind == "reasoning_path":
        return None
    content = representation.get("content")
    if content in (None, "", [], {}):
        return None
    return {
        "kind": kind or "text",
        "content": present_solution_value(content),
    }


def _present_vector(values: list[Any] | tuple[Any, ...]) -> str:
    return f"({', '.join(present_solution_value(item) for item in values)})"


def _fallback_label(field_name: str) -> str:
    words = field_name.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "结果"
