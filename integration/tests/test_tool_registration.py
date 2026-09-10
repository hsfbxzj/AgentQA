from __future__ import annotations

from pathlib import Path

from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory
from deerflow.tools import get_available_tools


def test_deerflow_loads_agentqa_tools_from_config() -> None:
    tools = get_available_tools(groups=["agentqa"], include_mcp=False)
    tool_names = {tool.name for tool in tools}

    assert "agentqa_create_test_plan" in tool_names
    assert "agentqa_execute_test_plan" in tool_names
    assert "agentqa_compare_test_reports" in tool_names

    execute_tool = next(tool for tool in tools if tool.name == "agentqa_execute_test_plan")
    assert set(execute_tool.tool_call_schema.model_fields) == {"plan_json", "approved"}
    compare_tool = next(tool for tool in tools if tool.name == "agentqa_compare_test_reports")
    assert set(compare_tool.tool_call_schema.model_fields) == {"baseline_report_json", "current_report_json"}


def test_agentqa_skill_declares_its_required_tools() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    skill = parse_skill_file(
        repository_root / "skills" / "public" / "agentqa-api-testing" / "SKILL.md",
        SkillCategory.PUBLIC,
    )

    assert skill is not None
    assert skill.name == "agentqa-api-testing"
    assert skill.allowed_tools is not None
    assert {"agentqa_create_test_plan", "agentqa_execute_test_plan", "agentqa_compare_test_reports", "ask_clarification"} <= set(skill.allowed_tools)
