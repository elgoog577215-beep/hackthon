from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EssayTaskItem(BaseModel):
    id: str
    filename: str
    task_id: str
    status: str
    total_pages: int | None
    create_time: str


class EssayTaskReport(BaseModel):
    task_id: str
    overall_score: str
    summary: str
    check_domains: list[dict]
    reference_issues: list | None
    recommendations: list[str] | None


EssayExportScope = Literal["summary_only", "summary_problem_pages", "full"]


class ReportExportRequest(BaseModel):
    task_ids: list[str]
    export_scope: EssayExportScope = Field(
        default="summary_only",
        description=(
            "summary_only: 仅汇总（总体评价、检查详情、参考文献问题、修改建议）；"
            "summary_problem_pages: 汇总 + 有问题的逐页；"
            "full: 完整报告（含全部逐页）"
        ),
    )


class EssayScoreCounts(BaseModel):
    qualified: int = 0
    need_revision: int = 0
    unqualified: int = 0


class EssayDomainProblemStat(BaseModel):
    domain: str
    paper_count: int
    percentage: float


class EssayOverviewOtherStatus(BaseModel):
    processing: int = 0
    failed: int = 0


class EssayOverview(BaseModel):
    """当前用户全部历史中，已完成论文的汇总统计（不含处理中/检查失败）。"""

    total_completed: int
    score_counts: EssayScoreCounts
    score_known: int
    top_problem_domains: list[EssayDomainProblemStat]
    other_status: EssayOverviewOtherStatus
