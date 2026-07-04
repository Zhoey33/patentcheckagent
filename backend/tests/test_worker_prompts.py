"""这个文件用于验证 Worker 构造的模型提示词不会携带无关阶段内容。"""

from app.worker import (
    build_stage_one_messages,
    build_stage_two_messages,
    extract_stage_one_bridge,
)

PROMPT = """
# 专利权利要求书与说明书检查

## 第一阶段：权利要求书检查与特征分解
第一阶段规则正文。

## 第二阶段：说明书检查
第二阶段规则正文。

## 三、说明书附图检查清单
附图规则正文。

## 四、说明书摘要检查清单
摘要规则正文。

## 五、输出格式
输出格式正文。

## 严重程度定义
严重程度正文。

## 工作指令
工作指令正文。
"""
PROMPT = PROMPT + "\n".join(f"无关长规则{i}。" for i in range(200))


def test_stage_one_prompt_excludes_later_stage_rules() -> None:
    messages = build_stage_one_messages(PROMPT, {"claims": "权利要求文本"}, "人工智能")
    system_content = messages[0]["content"]

    assert "第一阶段规则正文" in system_content
    assert "输出格式正文" in system_content
    assert "严重程度正文" in system_content
    assert "第二阶段规则正文" not in system_content
    assert "附图规则正文" not in system_content
    assert len(system_content) < len(PROMPT)


def test_stage_two_prompt_excludes_stage_one_rules() -> None:
    messages = build_stage_two_messages(
        PROMPT,
        {"specification": "说明书文本", "drawings": "", "abstract": ""},
        "人工智能",
        "### 技术特征分解与需说明书解释项清单\n| 权利要求编号 | 技术特征 |\n|---|---|\n| 权1 | A |",
    )
    system_content = messages[0]["content"]

    assert "第二阶段规则正文" in system_content
    assert "附图规则正文" in system_content
    assert "摘要规则正文" in system_content
    assert "输出格式正文" in system_content
    assert "第一阶段规则正文" not in system_content
    assert len(system_content) < len(PROMPT)


def test_stage_two_uses_bridge_section_instead_of_full_stage_one_report() -> None:
    stage_one_result = """
# 专利文件检查报告

### 问题项（按严重程度排序）
这里是一大段第一阶段问题解释，不应整体传入第二阶段。

### 技术特征分解与需说明书解释项清单
| 权利要求编号 | 技术特征摘录 | 需说明书解释的内容 |
|---|---|---|
| 权1 | A | 解释A |

## 第二阶段：说明书检查
后续内容。
"""

    bridge = extract_stage_one_bridge(stage_one_result)
    messages = build_stage_two_messages(
        PROMPT,
        {"specification": "说明书文本", "drawings": "", "abstract": ""},
        "人工智能",
        stage_one_result,
    )
    user_content = messages[1]["content"]

    assert "解释A" in bridge
    assert "这里是一大段第一阶段问题解释" not in user_content
    assert "解释A" in user_content


def test_stage_two_prompt_mentions_visual_attachments_when_present() -> None:
    messages = build_stage_two_messages(
        PROMPT,
        {"specification": "说明书文本", "drawings": "", "abstract": ""},
        "人工智能",
        "### 技术特征分解与需说明书解释项清单\n| 权1 | A |",
        visual_attachment_count=2,
    )
    user_content = messages[1]["content"]

    assert "附加了 2 张实际图像" in user_content
    assert "图1" in user_content
