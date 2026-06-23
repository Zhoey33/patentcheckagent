"""这个文件用于读取固定版本的专利审查提示词模板。"""

from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "check_patent.md"


def load_check_patent_prompt() -> str:
    """Load the patent check prompt template from the backend prompts directory."""

    return PROMPT_PATH.read_text(encoding="utf-8")
