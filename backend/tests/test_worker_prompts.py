"""原文件及完整 Skill 快照传递契约。"""

from pathlib import Path

from app.models.patent_check_file import PatentCheckFile
from app.models.patent_check_task import PatentCheckTask
from app.services.skill_service import builtin_skill_files, materialize_skill
from app.worker import build_file_review_prompt, prepare_original_files


def test_stage_prompts_pass_paths_without_compiling_document_text():
    files = {"claims": "inputs/claims.pdf", "specification": "inputs/specification.docx"}
    one = build_file_review_prompt("stage_one", files, "机械")
    two = build_file_review_prompt("stage_two", files, "机械")
    assert "inputs/claims.pdf" in one
    assert "specification.docx" not in one
    assert "inputs/claims.pdf" in two and "inputs/specification.docx" in two
    assert "stage-one.md" in two


def test_original_bytes_and_skill_references_are_available_to_codex(tmp_path):
    upload = tmp_path / "scan.pdf"
    data = b"%PDF-1.4 image-only fixture\x00\xff"
    upload.write_bytes(data)
    workspace = tmp_path / "work"
    workspace.mkdir()
    task = PatentCheckTask(
        files=[
            PatentCheckFile(file_role=role, stored_path=str(upload))
            for role in ("claims", "specification")
        ]
    )
    paths = prepare_original_files(task, workspace)
    assert (workspace / paths["claims"]).read_bytes() == data
    assert (workspace / paths["specification"]).read_bytes() == data
    assert len(list((workspace / "inputs").iterdir())) == 2
    files = builtin_skill_files()
    entry = materialize_skill({"files": files}, workspace)
    assert entry.relative_to(workspace) == Path(".agents/skills/check-patent/SKILL.md")
    for relative, content in files.items():
        assert (entry.parent / relative).read_text() == content
