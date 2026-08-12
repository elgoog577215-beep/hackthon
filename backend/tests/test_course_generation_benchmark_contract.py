from __future__ import annotations

from pathlib import Path

from models import CourseGenerationRequest
from scripts.course_generation_benchmark import load_manifest, summarize_runs
from scripts.course_prompt_contract_benchmark import (
    build_report as build_prompt_contract_report,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks" / "course_generation_v2" / "manifest.json"


def test_fixed_benchmark_contains_complete_cross_discipline_courses():
    manifest = load_manifest(MANIFEST)
    scenarios = manifest["scenarios"]

    assert {item["discipline"] for item in scenarios} >= {
        "mathematics",
        "natural_science",
        "humanities_social",
    }
    assert any(item["expected_sections"] == 8 for item in scenarios)
    assert sum(item["expected_sections"] == 12 for item in scenarios) >= 2
    assert all(item["expected_chapters"] == 4 for item in scenarios)
    assert all(CourseGenerationRequest.model_validate(item["request"]) for item in scenarios)
    assert len(manifest["teacher_rubric"]["dimensions"]) >= 8
    assert len(manifest["failure_set"]) >= 8
    assert manifest["release_gates"]["success_rate"] == 0.98


def test_benchmark_summary_does_not_claim_release_before_twenty_12_section_runs():
    runs = [{
        "success": True,
        "milestones_seconds": {
            "first_outline": 20,
            "formal_lesson_plan": 50,
            "first_section_content": 80,
            "complete_course": 150,
        },
        "output_contract": {"actual_sections": 12},
    }]
    summary = summarize_runs(runs, {
        "success_rate": 0.98,
        "minimum_runs_12_sections": 20,
    })

    assert summary["success_rate"] == 1.0
    assert summary["p50_seconds"]["complete_course"] == 150
    assert summary["release_gate"]["success_rate_passed"] is True
    assert summary["release_gate"]["sample_size_passed"] is False
    assert summary["release_gate"]["status"] == "not_claimable_until_all_gates_pass"


def test_offline_prompt_benchmark_separates_contract_coverage_from_model_quality():
    manifest = load_manifest(MANIFEST)
    report = build_prompt_contract_report(manifest)

    assert report["all_production_contracts_passed"] is True
    assert "不代表真实模型内容质量或延迟" in report["scope"]
    assert len(report["comparisons"]) == (
        len(manifest["scenarios"])
        + len(manifest["prompt_contract_scenarios"])
    )
    assert {item["subject_variant_id"] for item in report["comparisons"]} >= {
        "engineering_computing_foundations",
        "science_physical_engineering_design",
    }
    for comparison in report["comparisons"]:
        generic = comparison["variants"]["generic_role_only"]
        structured = comparison["variants"][
            "structured_without_execution_control"
        ]
        production = comparison["variants"]["production_contract"]
        assert production["budget_passed"] is True
        assert production["passed_dimensions"] == production["dimension_count"]
        assert generic["passed_dimensions"] < structured["passed_dimensions"]
        assert structured["passed_dimensions"] < production["passed_dimensions"]
        assert production["passed_dimensions"] > generic["passed_dimensions"]
