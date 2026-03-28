from src.schemas import CodePatch, EngineerOutput, PMOutput, ReviewerOutput


def test_pm_output_roundtrip():
    data = {
        "requirements": ["要件1"],
        "tasks": ["タスク1"],
        "acceptance_criteria": ["条件1"],
    }
    output = PMOutput.model_validate(data)
    assert output.requirements == ["要件1"]
    assert output.model_dump() == data


def test_engineer_output_roundtrip():
    data = {
        "design_notes": "設計メモ",
        "code_patches": [
            {"file_path": "app.py", "patch": "print('hello')", "description": "追加"},
        ],
        "assumptions": ["前提1"],
    }
    output = EngineerOutput.model_validate(data)
    assert len(output.code_patches) == 1
    assert isinstance(output.code_patches[0], CodePatch)


def test_reviewer_output_pass():
    output = ReviewerOutput(review_result="PASS", issues=[], fix_instructions=[])
    assert output.review_result == "PASS"


def test_reviewer_output_fail():
    output = ReviewerOutput(
        review_result="FAIL",
        issues=["問題1"],
        fix_instructions=["修正1"],
    )
    assert output.review_result == "FAIL"
    assert len(output.issues) == 1


def test_pm_output_json_schema_has_required_fields():
    schema = PMOutput.model_json_schema()
    assert "requirements" in schema["properties"]
    assert "tasks" in schema["properties"]
    assert "acceptance_criteria" in schema["properties"]
