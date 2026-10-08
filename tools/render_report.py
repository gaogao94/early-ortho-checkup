#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_report.py — 早矫管理体检报告：report.json → shadcn 风格 HTML（可选 PNG）。

为什么需要它：报告里的组件语法（frontmatter / kv / callout / flow / timeline / 表格）
如果每次都由模型手写，会长得不一样、也会写错。这个脚本把「数据 → 组件语法」这一步
固定下来：同一份 report.json 永远渲染出同一份 draft，模型只负责产出 JSON。

用法：
    python tools/render_report.py report.json [-o out.html] [--png [out.png]]
                                 [--am PATH] [--node PATH] [--theme shadcn]
                                 [--template sheet] [--style 80|off|strict] [--dry-run]

    -o 省略时写到 %TEMP%\\eoc_reports\\<报告名>.html（不写进仓库）。
    --png 不带值时输出与 HTML 同名的 .png。
    --dry-run 只打印 draft 与将执行的命令，不调用 node / am。

退出码：
    0  成功（产物路径打在最后一行）
    1  am 渲染或截图失败（am 自己的 stdout/stderr 已原样透传）
    2  输入/参数错误（缺字段、字段类型错、找不到文件）

只在标准库上运行（Python 3.8+），不装任何依赖。

输入 report.json 的字段见 REQUIRED_FIELDS / OPTIONAL_FIELDS：
必填字段一个都不能少，缺了直接报错退出，**不猜默认值**；24 题必须全部作答，缺一题不出报告
（缺省视为空列表，它表示"这题没覆盖到"，缺失与"没有未覆盖题"在报告里是同一种呈现）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

__version__ = "1.0.0"

# --------------------------------------------------------------------------- #
# 常量：字段契约 / 状态词 / 外壳命令
# --------------------------------------------------------------------------- #

#: 必填字段 → 允许的 Python 类型。注意 bool 是 int 的子类，下面单独挡掉。
REQUIRED_FIELDS = {
    "org": str,
    "scale": str,
    "date": str,
    "interviewee": str,
    "evidence": str,
    "headline": dict,
    "dimensions": list,
    "redlines": list,
    "answers": list,
    "actions": list,
    "roadmap": list,
    "metrics": list,
    "next_steps": list,
}

HEADLINE_FIELDS = {
    "level": str,
    "level_name": str,
    "raw_score": int,
    "capped_reason": str,  # 需要它来判"红线是否真的降级"，所以必填
    "summary": str,
}

DIMENSION_FIELDS = {"id": str, "name": str, "score": int, "gap": str}
REDLINE_FIELDS = {"id": str, "name": str, "verdict": str, "basis": str}
ANSWER_FIELDS = {"id": str, "score": int, "quote": str, "basis": str}
#: 报告要求 24 题全部作答。缺一题就不出报告——见下面的 check_completeness()。
ALL_QUESTION_IDS = tuple(
    f"{dim}{n}" for dim in "ABCD" for n in range(1, 7)
)
#: 可选字段：缺了不算错。曾经必填、现在不再显示的也放这里，老 JSON 不用改。
OPTIONAL_ACTION_FIELDS = {"title", "eta"}
ACTION_FIELDS = {
    "id": str,
    "name": str,  # 动作的契约名，与 playbook 一致
    "tier": str,
    "gap_ids": str,
    "now": str,
    "todo": list,
    "accept": str,
}
ROADMAP_FIELDS = {"weeks": str, "action": str, "deliverable": str, "accept": str}
METRIC_FIELDS = {"id": str, "name": str, "value": str, "note": str}

#: 红线结论 → 表格状态词（am 会把状态词渲染成 ✓ / ✗ / ! 徽章）
VERDICT_STATUS = {"命中": "no", "未命中": "ok", "信息不足": "warn"}

#: 档位 → 排序序号（P0 → P1 → P2）
TIER_RANK = {"P0": 0, "P1": 1, "P2": 2}

#: 维度分档位（来自 SKILL.md「等级」表的 0–30 / 31–55 / 56–80 / 81–100）
SCORE_BANDS = (
    (0, 30, "no", "L1 档"),
    (31, 55, "warn", "L2 档"),
    (56, 80, "warn", "L3 档"),
    (81, 100, "ok", "L4 档"),
)

#: 等级看板的四行。等级名要让人一眼看懂处境，不用抽象名词——
#: "运转中" 这种自造词读者猜不出含义，是用户明确反馈过的问题。
LEVEL_BANDS = (
    ("L1", 0, 30, "无标准", "没有标准、没有计划时长、没有账，全凭医生个人"),
    ("L2", 31, 55, "刚起步", "有零散做法，但不留痕、不可复算"),
    ("L3", 56, 80, "有体系", "有标准能执行、数据可查，结案复核还有缺口"),
    ("L4", 81, 100, "能自转", "标准、审核、留痕、复核、激励、财务全部到位"),
)

UNKNOWN_PREFIX = "未知"

#: am CLI 的默认位置（%TEMP% 在 Windows 上可能是 ...\Temp\1，所以两个都试）
AM_RELATIVE = Path("amwh") / "skills" / "answer-me-with-html" / "scripts" / "am.mjs"

#: 找不到 node 时依次尝试的候选路径
NODE_CANDIDATES = (
    r"C:\Program Files\nodejs\node.exe",
    r"C:\Program Files (x86)\nodejs\node.exe",
)

#: 与 render_report.py 同目录的出图工具
HTML_TO_IMAGE_NAME = "html_to_image.mjs"

EXIT_OK, EXIT_RUNTIME, EXIT_INPUT = 0, 1, 2


class InputError(Exception):
    """输入或参数不合法 → 退出码 2。"""


def force_utf8_stdio() -> None:
    """把 stdout/stderr 切成 UTF-8。

    Windows 控制台默认是 GBK（cp936），draft 里的 ✓ / ✗ / ! 与 emoji 一 print
    就 UnicodeEncodeError；而 am 的输出本身也是 UTF-8，透传时同样会炸。
    errors="replace" 是兜底：字体缺字也不要让整个渲染失败。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 例如 stream 已经被重定向成不支持重配置的对象：不致命，继续跑
            pass


# --------------------------------------------------------------------------- #
# 文本安全：表格 / 组件里的特殊字符
# --------------------------------------------------------------------------- #


def one_line(text) -> str:
    """把任意值压成单行文本，并转义 Markdown 表格的竖线。"""
    if text is None:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = " ".join(part.strip() for part in s.split("\n"))
    s = " ".join(s.split())  # 折叠连续空白
    # 先转义反斜杠，再转义竖线，避免把已有的 \| 变成 \\|
    s = s.replace("\\", "\\\\").replace("|", "\\|")
    return s.strip()


def inline(text) -> str:
    """单行文本，供不支持竖线转义的组件（kv / timeline / flow）使用。

    竖线换成全角 ｜：这些组件用 `|` 当分隔符，写 \\| 并不保证被还原，
    换成全角字符既不会截断，读者也看不出来。
    """
    return one_line(text).replace("\\|", "｜")


def cell(text, limit: int | None = None) -> str:
    s = one_line(text)
    if limit is not None and len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def single_line(text) -> str:
    """仅供 frontmatter 使用：不加表格转义，不截断。"""
    if text is None:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(s.split())


def has_text(text) -> bool:
    return bool(str(text).strip())


def is_unknown(value) -> bool:
    """'未知' 判定：空值或以「未知」开头的值（如「未知（缺字段：xxx）」）。"""
    s = one_line(value).replace("\\|", "|")
    return (not s) or s.startswith(UNKNOWN_PREFIX)


def score_band(score: int):
    for low, high, status, label in SCORE_BANDS:
        if low <= score <= high:
            return status, label
    return ("warn", "超出 0–100")


def fmt_score(score) -> str:
    return f"{int(score)}/100"


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #


def _type_ok(value, expected) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)


def _require(mapping: dict, fields: dict, where: str) -> None:
    for key, expected in fields.items():
        if key not in mapping:
            raise InputError(f"缺字段：{where}.{key}（类型应为 {expected.__name__}）")
        if not _type_ok(mapping[key], expected):
            raise InputError(
                f"字段类型错：{where}.{key} 期望 {expected.__name__}，"
                f"实际是 {type(mapping[key]).__name__}"
            )


def check_completeness(data: dict) -> None:
    """24 题必须全部作答，缺一题就不出报告。

    这是硬门禁，不是提醒。"不知道"是答案（按锚点判分），"没答"不是答案：
    缺了任何一题，维度分、等级、红线都得打折说明，交出去的会是一份
    到处写着"仅供参考"的报告——那种报告不如不出。
    """
    got = [a["id"] for a in data["answers"]]
    missing = [q for q in ALL_QUESTION_IDS if q not in got]
    extra = [q for q in got if q not in ALL_QUESTION_IDS]
    if missing or extra:
        lines = [
            "输入错误：报告要求 24 题全部作答，现在这份不完整，无法生成报告。",
            "",
            f"  应有 {len(ALL_QUESTION_IDS)} 题，实际给了 {len(got)} 题。",
        ]
        if missing:
            lines.append("  还缺这些题：" + "、".join(missing))
        if extra:
            lines.append("  多出这些题号（不在题库里）：" + "、".join(extra))
        lines += [
            "",
            "  怎么办：回去把缺的题问掉。答不上来可以让受访者说\"不知道\"——",
            "  \"不知道\"按锚点判分（通常是 0 档），是有效答案。",
        ]
        raise InputError("\n".join(lines))


def validate_report(data) -> dict:
    if not isinstance(data, dict):
        raise InputError("report.json 的顶层必须是一个 JSON 对象")

    for key, expected in REQUIRED_FIELDS.items():
        if key not in data:
            raise InputError(f"缺字段：{key}（类型应为 {expected.__name__}）")
        if not _type_ok(data[key], expected):
            raise InputError(
                f"字段类型错：{key} 期望 {expected.__name__}，"
                f"实际是 {type(data[key]).__name__}"
            )

    _require(data["headline"], HEADLINE_FIELDS, "headline")

    for name, fields in (
        ("dimensions", DIMENSION_FIELDS),
        ("redlines", REDLINE_FIELDS),
        ("answers", ANSWER_FIELDS),
        ("actions", ACTION_FIELDS),
        ("roadmap", ROADMAP_FIELDS),
        ("metrics", METRIC_FIELDS),
    ):
        for i, item in enumerate(data[name]):
            if not isinstance(item, dict):
                raise InputError(f"{name}[{i}] 必须是对象")
            required = {k: v for k, v in fields.items() if k not in OPTIONAL_ACTION_FIELDS} \
                if name == "actions" else fields
            _require(item, required, f"{name}[{i}]")

    for i, item in enumerate(data["next_steps"]):
        if not isinstance(item, str):
            raise InputError(f"next_steps[{i}] 必须是字符串（当前 {type(item).__name__}）")

    for i, item in enumerate(data["actions"]):
        for j, step in enumerate(item["todo"]):
            if not isinstance(step, str):
                raise InputError(f"actions[{i}].todo[{j}] 必须是字符串（当前 {type(step).__name__}）")

    check_completeness(data)

    for i, item in enumerate(data["actions"]):
        if item["tier"] not in TIER_RANK:
            raise InputError(
                f"actions[{i}].tier 只能是 P0 / P1 / P2，实际是 {item['tier']!r}"
            )

    for i, item in enumerate(data["redlines"]):
        if item["verdict"] not in VERDICT_STATUS:
            raise InputError(
                f"redlines[{i}].verdict 只能是 命中 / 未命中 / 信息不足，"
                f"实际是 {item['verdict']!r}"
            )

    for name in ("dimensions", "redlines", "answers", "metrics"):
        if not data[name]:
            raise InputError(f"{name} 不能为空数组——报告结构要求这一节有内容")

    return data


#: K1–K8 对读者没有意义，页面上写成"指标1–指标8"
def plain_id(mid: str) -> str:
    """把契约里的短码翻成读者认得的说法。

    契约层（question-bank / playbook / report.json）继续用 A1、R2、K4、ACT-3，
    那是编号一致性的基础；但它们不该原样出现在给老板看的页面上。
    A1 到这一步读作"维度1 第1题"。"""
    if len(mid) >= 2 and mid[0] in "ABCD" and mid[1:].isdigit():
        return f"维度{'ABCD'.index(mid[0]) + 1} 第{mid[1:]}题"
    if len(mid) >= 2 and mid[0] in "RK" and mid[1:].isdigit():
        return ("红线" if mid[0] == "R" else "指标") + mid[1:]
    if mid.startswith("ACT-"):
        return "动作" + mid[4:]
    return mid


def compact_basis(text: str) -> str:
    """依据里出现的题号与红线号也要可读。

    读者的视野里不该出现 R3、K4、A1 这类契约短码——题号写成 A1，
    红线写成「无周期标准」那条，指标写成「指标4」。
    """
    import re as _re

    def repl(m):
        code = m.group(0)
        if code[0] in "ABCD":
            return code  # 题号保留 A1 形式：有分类感，读者能看出属于哪个维度
        return plain_id(code)

    return _re.sub(r"\b[ABCDRK][0-9]{1,2}\b", repl, text)


def capsule_ids(text: str) -> str:
    """把一句话里裸写的题号（A1、B4、D2…）逐个换成胶囊。

    报告里常有一句"重点对比题号 A1 A2 A4 A5 B1 B4 B5 D2 D4"，
    九个短码连在一起就是一片字母噪声。换成胶囊之后能一眼数出几个。
    题号保留 A1 原样，不改写成 1-1——带维度字母读者才知道它属于哪一块。"""
    import re as _re

    return _re.sub(
        r"\b[ABCD][0-9]{1,2}\b",
        lambda m: capsule(m.group(0)),
        text,
    )


def short_id(qid: str) -> str:
    """逐题明细的题号列：写成 1-1 这种形式，一眼看出是第几个维度的第几题。"""
    if len(qid) >= 2 and qid[0] in "ABCD" and qid[1:].isdigit():
        return f"{'ABCD'.index(qid[0]) + 1}-{qid[1:]}"
    return qid


def plain_ids(text: str) -> str:
    """把一行里出现的所有短码逐个换成可读说法（用于"涉及题号"这类字段）。"""
    import re as _re

    def repl(m):
        return plain_id(m.group(0))

    return _re.sub(r"\b([ABCDR K])([0-9]{1,2})\b|\bACT-([0-9])\b", lambda m: (
        f"维度{'ABCD'.index(m.group(1)) + 1} 第{m.group(2)}题" if m.group(1) in "ABCD" and m.group(1)
        else (f"红线{m.group(2)}" if m.group(1) == "R"
              else (f"指标{m.group(2)}" if m.group(1) == "K"
                    else f"动作{m.group(3)}"))
    ), text)


def _unused_plain_id(mid: str) -> str:
    return "指标" + mid[1:] if mid.startswith("K") and mid[1:].isdigit() else mid


def plain_name(name: str) -> str:
    """指标名说人话。

    "计划 vs 实际时长" 不是指标名——读者拿不到"多少"这个量。斜杠也一并去掉：
    "A / B" 读起来像两个东西，其实是一个指标的两个面，用顿号更自然。
    按最长匹配优先，避免 "实际时长" 里的 "时长" 先被替换。
    """
    fixes = (
        ("计划 vs 实际时长", "计划疗程与实际疗程差多少"),
        ("计划 vs 实际", "计划与实际"),
        ("椅位时长 / 每例次数", "每次占椅位多久、每例来几次"),
        ("重启率 / 二次治疗率", "重启或二次治疗的比例"),
        (" / ", "、"),
    )
    for old, new in fixes:
        name = name.replace(old, new)
    return name


def sort_actions(actions: list) -> list:
    """按档位 P0→P1→P2 排；同档保持 report.json 里的数组顺序。"""
    indexed = list(enumerate(actions))
    indexed.sort(key=lambda pair: (TIER_RANK[pair[1]["tier"]], pair[0]))
    return [act for _, act in indexed]


# --------------------------------------------------------------------------- #
# 行内样式（am 允许行内 <span>，实测 style 属性原样保留）
# --------------------------------------------------------------------------- #

#: 颜色取自 shadcn 主题的 token，深浅色模式都能看清
_C_INK = "#09090b"
_C_DIM = "#71717a"
_C_LINE = "#e4e4e7"
_C_FILL = "#f4f4f5"
_C_ACCENT = "#2563eb"
_C_ERR = "#dc2626"
_C_WARN = "#d97706"
_C_OK = "#16a34a"


#: 档位标签的配色。用 tag 的形状（带底色的圆角块）而不是纯文字，
#: 一眼分出"哪几件先做"。
_TIER_TAG = {
    "P0": ("#fef2f2", "#dc2626", "先做"),
    "P1": ("#fffbeb", "#d97706", "接着做"),
    "P2": ("#f4f4f5", "#71717a", "以后做"),
}


def tier_tag(tier: str) -> str:
    """档位做成 tag。比 P0/P1/P2 好懂，也比纯灰字醒目。"""
    bg, fg, label = _TIER_TAG.get(tier, ("#f4f4f5", "#71717a", tier))
    return (
        f'<span style="display:inline-block;padding:2px 10px;margin-left:10px;'
        f'border-radius:6px;background:{bg};color:{fg};font-size:12px;font-weight:700;'
        f'vertical-align:2px">{label}</span>'
    )


def capsule(text: str, tone: str = "plain") -> str:
    """把题号、指标号这类短码做成 tag，别让它混在正文里当普通文字读。

    用正文字体，不用等宽字体：等宽体在中文报告里显得像代码，
    而且"指标2"这种中文标签在等宽体下字形是外挂的。
    """
    bg, fg = {
        "plain": (_C_FILL, _C_DIM),
        "accent": ("#eff6ff", _C_ACCENT),
        "err": ("#fef2f2", _C_ERR),
        "warn": ("#fffbeb", _C_WARN),
    }.get(tone, (_C_FILL, _C_DIM))
    body = single_line(text)
    return (
        '<span style="display:inline-block;padding:1px 8px;margin:0 2px;'
        f'border-radius:6px;background:{bg};color:{fg};'
        f'font-size:12px;font-weight:600;white-space:nowrap">{body}</span>'
    )


def big(text: str, size: int = 56, color: str = _C_INK) -> str:
    """视觉重心：等级、维度得分这类要一眼看到的数字。"""
    return (
        f'<span style="font-size:{size}px;font-weight:800;letter-spacing:-1px;'
        f'line-height:1;color:{color}">{single_line(text)}</span>'
    )


def small(text: str, size: int = 13, color: str = _C_DIM) -> str:
    return f'<span style="font-size:{size}px;color:{color}">{single_line(text)}</span>'


def raw_total(data: dict) -> tuple[int, int]:
    """原始分与满分。六个问题、每题 0–3 分，所以每个维度满分 18，四个维度共 72。"""
    scored = [a["score"] for a in data["answers"] if a["score"] is not None]
    full = len(scored) * 3
    return sum(int(s) for s in scored), full


def pct(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


# --------------------------------------------------------------------------- #
# draft 生成
# --------------------------------------------------------------------------- #


def frontmatter_block(data: dict, theme: str, template: str, style: str) -> str:
    headline = data["headline"]
    title = f"{single_line(data['org'])} · 早矫管理体检报告"
    subtitle = f"{single_line(data['date'])}"
    # 自定义键只用 ASCII：am 的 frontmatter 解析对非 ASCII 键不友好。
    # style 不写在这里——它已经由 --style 传给 am，写两处只会互相打架。
    lines = [
        "---",
        f"template: {template}",
        f"theme: {theme}",
        f"title: {title}",
        f"subtitle: {subtitle}",
        "cols: 3",
        "---",
    ]
    return "\n".join(lines)


def header_panel(data: dict) -> str:
    """报告信息只留三条：机构、规模、访谈日期。

    不用 kv 组件——它排出来是"标签 + 值"的表格样子（左侧等宽小标签、右侧值），
    信息少的时候看着多余。直接写三行文字，跟正文一个样式。
    """
    # 三行：机构 / 规模 / 日期 各一行。
    # 窄栏（990 视口下这个面板约 290px）里"3 名正畸医生 / 年新接约 180 例"会折行，
    # 但三行各自独立，折了也不串行；把日期并进第二行反而会在宽屏下显得挤。
    rows = [
        "机构：" + inline(data["org"]),
        "规模：" + inline(data["scale"]),
        "访谈日期：" + inline(data["date"]),
    ]
    # 占 1 列：990 视口下正好把结论面板放在右边，形成"侧栏 + 主栏"。
    # 占满整宽会把结论挤到下一行，那份报告的视觉重心就没了。
    #
    # 三行写成 <br> 分隔的整段文字，不用 Markdown 的硬换行（行尾两个空格）：
    # 硬换行会让每行成为独立段落，窄栏里"规模"那行会被断成两段。
    body = "<br>".join(rows)
    return "## 报告信息\n\n" + body + "\n"


def level_of_score(score: int) -> str:
    """按总分反推未封顶时的等级，用来说清"本来是哪一档"。返回"L2 刚起步"这样的整串。"""
    for lid, low, high, name, _desc in LEVEL_BANDS:
        if low <= score <= high:
            return f"{lid} {name}"
    return "更低一档"


def headline_panel(data: dict) -> str:
    """结论面板：全报告唯一的视觉重心。

    只放大字等级、一句结论、一条红线说明，不放任何解释性文字。
    "总分 31／100" 这类短句在报告头已经出现过，这里再来一遍只是占高度。
    """
    h = data["headline"]
    level = one_line(h["level"])
    level_name = one_line(h["level_name"])
    score = int(h["raw_score"])
    hits = [r for r in data["redlines"] if r["verdict"] == "命中"]

    out = [
        "## 结论",
        "",
        # 视觉重心就在这一行：等级越大越好，总分跟在其后。
        # 这是全报告唯一放大字的地方，读者第一眼必须落在"我站在哪一档"。
        big(level, 92)
        + "&nbsp;&nbsp;&nbsp;"
        + big(level_name, 42, _C_INK)
        + "&nbsp;&nbsp;&nbsp;"
        + small(f"{score} 分", 26),
        "",
    ]

    # 红线与等级的关系一句话说完。标题只说发生了什么，不解释"压"是什么意思——
    # 细节留给正文那一句。
    if hits:
        names = "、".join(one_line(r["name"]) for r in hits)
        out += [
            f"```callout err 命中 {len(hits)} 条红线，等级降低",
            f"按总分本来能到 {level_of_score(score)} 档。{names} 属于一票否决，等级只算 {level}。",
            "```",
        ]
    else:
        out += [
            "```callout info 四条红线全部通过",
            f"没有一票否决的问题，{level} 这个等级是实打实的。",
            "```",
        ]
    return "\n".join(out) + "\n"


def level_gauge(current: str, score: int) -> str:
    """四档刻度。当前档整行加底色，一眼看到自己站在哪。

    不再单列"你在这里"——整行高亮比一个标记更省一列宽度。
    """
    lines = [
        "| 等级 | 这一档的样子 | 分数段 |",
        "|---|---|---|",
    ]
    hl = "background:#eff6ff"
    for lid, low, high, name, desc in LEVEL_BANDS:
        if lid == current:
            lines.append(
                f'| <span style="{hl};display:block;font-weight:800">{lid} {name}</span> '
                f'| <span style="{hl};display:block">{desc}</span> '
                f'| <span style="{hl};display:block">{low}–{high}</span> |'
            )
        else:
            lines.append(f"| **{lid} {name}** | {desc} | {low}–{high} |")
    return "\n".join(lines)


def dim_bar(dim: dict) -> str:
    """一行一个维度：竖杠 + 编号名 + 得分 + 一句话缺口。

    第 2 次改法的两个毛病都修掉了：
    - 竖杠原来撑满整行（比字高出一大截），现在 inline-block 加 padding，
      高度跟着文字走；
    - 得分和 /18 原来被 min-width 撑开，看起来是跟标题挤在一起。

    维度名前面用竖杠而不是胶囊——四五个胶囊排在一起像一排按钮，
    读不出它们是并列的维度。
    """
    order = "ABCD".index(dim["id"]) + 1 if dim["id"] in "ABCD" else dim["id"]
    raw_dim = round(int(dim["score"]) * 0.18)
    gap = one_line(dim.get("gap") or dim.get("desc") or "")
    bar = (
        f"display:inline-block;border-left:3px solid {_C_ACCENT};"
        f"padding:2px 0 2px 10px;margin:5px 0"
    )
    head = f'<span style="font-weight:700">维度{order}｜{one_line(dim["name"])}</span>'
    tail = (
        f'<span style="font-size:19px;font-weight:800;color:{_C_ACCENT};'
        f'padding:0 6px 0 12px">{raw_dim}</span>'
        f'<span style="font-size:12px;color:{_C_DIM}">/18　</span>'
    )
    return f'<span style="{bar}">{head}{tail}{gap}</span>'


def score_panel(data: dict) -> str:
    """分数与等级：先给四档刻度，再给四行维度得分。

    维度分显示 18 分制的原始分（6 题 × 每题 0–3 分）。不折成 100 再平均——
    多一次换算只会让读者怀疑"是不是又加了权重"。
    """
    h = data["headline"]
    out = [
        "## 分数与等级 {span=2}",
        "",
        level_gauge(one_line(h["level"]), int(h["raw_score"])),
        "",
        "### 四个维度各得多少",
        "",
    ]
    for dim in data["dimensions"]:
        out += [dim_bar(dim), ""]
    return "\n".join(out) + "\n"


def redlines_panel(data: dict) -> str:
    """四条红线。结论列只写结果词，不能写状态词——am 会把 ok/no/warn 换成徽章。"""
    lines = [
        "## 四条红线 {span=2}",
        "",
        "| 红线 | 结论 | 依据 |",
        "|---|---|---|",
    ]
    for red in data["redlines"]:
        # 命中的整条标红：四条里哪几条出问题，应该一眼扫到，不用逐个读"命中"两个字
        if red["verdict"] == "命中":
            name = f'<span style="color:{_C_ERR};font-weight:700">{one_line(red["name"])}</span>'
            verdict = f'<span style="color:{_C_ERR};font-weight:700">{one_line(red["verdict"])}</span>'
        elif red["verdict"] == "信息不足":
            name = f'<span style="color:{_C_WARN}">{one_line(red["name"])}</span>'
            verdict = f'<span style="color:{_C_WARN}">{one_line(red["verdict"])}</span>'
        else:
            name = cell(red["name"])
            verdict = cell(red["verdict"])
        lines.append(f"| {name} | {verdict} | {cell(compact_basis(red['basis']))} |")
    return "\n".join(lines) + "\n"


def answers_panel(data: dict) -> str:
    lines = [
        "## 逐题明细 {span=2}",
        "",
        "| 题号 | 分数 | 受访者关键原话 | 判分依据 |",
        "|---|---|---|---|",
    ]
    for ans in data["answers"]:
        # score == null：该题被跳过（"未覆盖"）。既不算 0 分也不算满分，
        # 与 SKILL.md「跳过的题不给分、也不进分母」一致。
        # 同样不放状态词：判分列要显示的是"几分之几"，不是图标。
        if ans["score"] is None:
            lines.append(
                f"| {capsule(short_id(ans['id']))} | {small('未覆盖', 13, _C_WARN)} "
                f"| {cell(ans['quote'])} | {cell(ans['basis'])} |"
            )
            continue
        score = int(ans["score"])
        color = _C_OK if score >= 3 else (_C_ERR if score <= 0 else _C_WARN)
        # 只写"3 分"不写"3/3"：每题都是 0–3 分，满分固定，重复写没有信息量。
        lines.append(
            f"| {capsule(ans['id'])} | {small(f'{score} 分', 13, color)} "
            f"| {cell(ans['quote'])} | {cell(ans['basis'])} |"
        )
    return "\n".join(lines) + "\n"


def priority_flow(actions: list) -> str:
    """优先序图。

    节点名只写序号加短标题：流程图里塞长句子会让每格都折行，
    而且这一节的标题已经写过同样的字。契约名（ACT-2 结果要核）不出现在图上，
    那是内部编号，读者不需要看到两套名字。
    """
    labels = []
    for i, act in enumerate(actions, start=1):
        title = one_line(act.get("title") or act["name"])
        labels.append(f"{i} {title[:14]}")
    lines = []
    for i in range(len(labels) - 1):
        nxt = actions[i + 1]["tier"]
        if nxt != actions[i]["tier"]:
            # 只标跨档那次跳转：同档相邻的都标，就看不出哪一步是真正的换挡点
            lines.append(f"{labels[i]} -> {labels[i + 1]}: {nxt}")
        else:
            lines.append(f"{labels[i]} -> {labels[i + 1]}")
    seen: dict[str, list[str]] = {}
    for label, act in zip(labels, actions):
        seen.setdefault(act["tier"], []).append(label)
    for tier in ("P0", "P1", "P2"):
        if tier in seen:
            lines.append(f"group {tier}: " + ", ".join(seen[tier]))
    return "\n".join(lines)


def actions_panel(data: dict) -> str:
    """该做什么。

    每个动作是一个待办，所以标题必须是待办的说法："结束病例要过一遍复核"，
    不是"结果要核"——后者是名词词组，读不出是要人去做事。
    标题下面加一条分隔线，六个动作连排时不至于糊成一片。
    """
    actions = sort_actions(data["actions"])
    out = ["## 该做什么 {span=2}", ""]

    # 下一步并进这一节开头：原来它是独立一节，和这里的动作列表说的是同一件事
    steps = data["next_steps"]
    if steps:
        body = "\n".join(f"{i}. {capsule_ids(one_line(s))}" for i, s in enumerate(steps, start=1))
        out += ["```callout warn 这周就开始", body, "```", ""]

    if actions:
        out += [
            "```flow LR",
            priority_flow(actions),
            "```",
            "",
            "---",
            "",
        ]

    for i, act in enumerate(actions, start=1):
        if i > 1:
            out += ["---", ""]
        title = one_line(act.get("title") or act["name"])
        # 档位做成 tag：先做 / 接着做 / 以后做。比 P0/P1/P2 好懂，
        # 也比一行灰字醒目——六个动作里哪几件先做，一眼能分出来。
        out += [
            f"### {i}. {title}{tier_tag(act['tier'])}",
            "",
            one_line(act["now"]),
            "",
        ]
        if act["todo"]:
            out += [f"{j}. {one_line(step)}" for j, step in enumerate(act["todo"], start=1)]
            out.append("")
        out += [f"做到这一步算完成。{one_line(act['accept'])}", ""]
    return "\n".join(out) + "\n"


def roadmap_panel(data: dict) -> str:
    """90 天怎么排用表格，不用 timeline。

    timeline 把每条的时间标题居中、正文塞在下面，四段并排时读者看不出
    下面那行灰字属于哪一段。表格天然左对齐、逐列对应，不会串行。
    """
    lines = [
        "## 90 天怎么排 {span=2}",
        "",
        "| 时间 | 要做什么 | 交付什么 | 怎样算做完 |",
        "|---|---|---|---|",
    ]
    for row in data["roadmap"]:
        lines.append(
            f"| {cell(row['weeks'])} | {cell(row['action'])} "
            f"| {cell(row['deliverable'])} | {cell(row['accept'])} |"
        )
    return "\n".join(lines) + "\n"


def metrics_panel(data: dict) -> str:
    # span=2：三列表格放进 1/3 宽的列会被压成逐字换行，必须给足宽度
    lines = [
        "## 八个关键数字 {span=2}",
        "",
        "| 指标 | 数值 | 从哪来 |",
        "|---|---|---|",
    ]
    for metric in data["metrics"]:
        # 不放 ok / warn：am 会把它们换成 ✓ / ! 徽章，而读者要的是数字本身。
        value = cell(metric["value"])
        if is_unknown(metric["value"]):
            value = small("还不知道", 13, _C_WARN)
        lines.append(
            f"| {capsule(plain_id(metric['id']))} {cell(plain_name(metric['name']))} "
            f"| {value} | {cell(metric['note'])} |"
        )
    # 表下不再加解释：哪几个"还不知道"表里一眼看得到，取证方式就在右边那一列。
    return "\n".join(lines) + "\n"


def build_draft(data: dict, *, theme: str, template: str, style: str) -> str:
    # 面板顺序就是阅读顺序。宽表格（分数、红线、逐题、动作、路线图、指标）各占 2 列，
    # 剩下的窄栏留给"证据强度"这类单句提示。不再用「一、二、三」给面板编号——
    # am 会自动给面板分配 A、B、C 字母，两套编号并排出现是重复（去 AI 味规则第 6 条）。
    panels = [
        header_panel(data),
        headline_panel(data),
        score_panel(data),
        redlines_panel(data),
        answers_panel(data),
        actions_panel(data),
        roadmap_panel(data),
        metrics_panel(data),
    ]
    body = "\n".join(p for p in panels if p.strip())
    return frontmatter_block(data, theme, template, style) + "\n\n" + body.strip() + "\n"


# --------------------------------------------------------------------------- #
# 外部命令
# --------------------------------------------------------------------------- #


def default_am_path() -> Path:
    candidates = []
    for env_name in ("TEMP", "TMP", "TMPDIR"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / AM_RELATIVE)
    candidates.append(Path(tempfile.gettempdir()) / AM_RELATIVE)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def find_node(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("node")
    if found:
        return found
    for candidate in NODE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    dsh_node = Path(os.environ.get("DSH_HOME", "")) / "dsh-runtimes"
    if dsh_node.is_dir():
        hits = sorted(dsh_node.glob("*/dependencies/node*/node.exe"))
        hits += sorted(dsh_node.glob("*/dependencies/node.exe"))
        if hits:
            return str(hits[0])
    raise InputError(
        "找不到 node。请用 --node <path> 指定，或把 node 加进 PATH"
        "（已试 node、C:\\Program Files\\nodejs\\node.exe、DSH 自带 node）"
    )


def fmt_cmd(argv: list) -> str:
    """把命令行格式化成可以直接粘进 pwsh / cmd 的一行。"""
    out = []
    for part in argv:
        s = str(part)
        out.append(f'"{s}"' if (" " in s or "\t" in s) else s)
    return " ".join(out)


def run_command(argv: list, label: str) -> int:
    printable = [str(a) for a in argv]
    print(f"$ {fmt_cmd(printable)}", flush=True)
    try:
        proc = subprocess.run(
            printable,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        print(f"✗ {label} 启动失败：{exc}", file=sys.stderr)
        return EXIT_RUNTIME
    # 原样透传子进程的输出（含 am 的 STE 警告），不要吞掉
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    if out:
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    if err:
        sys.stderr.write(err)
        if not err.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()
    if proc.returncode != 0:
        # am 的 STE 警告只走提示、不算失败；这里是非零退出，才算失败
        print(f"✗ {label} 退出码 {proc.returncode}", file=sys.stderr)
        return EXIT_RUNTIME
    return EXIT_OK


# --------------------------------------------------------------------------- #
# am 产物的后处理
# --------------------------------------------------------------------------- #

#: 统一字体：am 的 base CSS 把表头、键值标签、面板角标设成等宽字体，
#: 中文报告里这些中文标签会显示成外挂字形，整页看起来有两种字体。
#: 只覆盖 font-family，字号/行高/颜色不动；code/pre/kbd 继续用等宽。
_FONT_OVERRIDE = (
    '<style id="eoc-uniform-font">'
    ".am-md th, .am-kv dt, .am-panel-meta, .am-head-meta b "
    "{ font-family: var(--font-sans) !important; }"
    "</style>"
)

#: am 的页脚署名。印在成品图上像水印，对读报告的人也没有信息量。
#: 本仓库在 README 与文件头保留了完整署名（am 是 MIT，允许修改）。
_COLOPHON_RE = re.compile(r'<footer class="am-colophon">[\s\S]*?</footer>')

#: 锁定页面宽度。
#:
#: 报告不是网站，一致性比自适应重要：这份文件会被打开、转发、导出成图，
#: 三种场景必须看到同一个版式。锁死宽度之后，浏览器里、别人的电脑上、
#: 导出的 PNG 全都是同一个排版，不会再出现"我这边看是并排、你那边是上下"。
#:
#: 990 必须与 html_to_image.mjs 的 --css-width 默认值保持一致，
#: 否则图与页面又会分叉（那个值是按"图缩到阅读宽度时字号 1:1"定的）。
_LOCK_WIDTH = 990

_WIDTH_LOCK = (
    f'<style id="eoc-width-lock">'
    # 只在"容器宽度与窗口宽度一致"的区间里锁宽。
    #
    # am 的运行时有一段列平衡脚本，按 grid 容器的实际宽度重排面板。如果容器被写死
    # 成 990px 而窗口更宽，两者对不上，平衡脚本会算错：实测 1920 窗口下报告信息被
    # 压成 1 列、结论被挤到它下面，版面彻底散掉（只写 max-width 也一样会散，因为
    # 容器仍然是 990 而窗口是 1920）。
    #
    # 所以锁宽只覆盖"窄窗"区间：窗口不超过 {_LOCK_WIDTH + 40}px 时，把 sheet 钉在
    # 990px 居中 —— 这正是出图与阅读的宽度。窗口更宽时撤掉约束，让 am 按它自己的
    # 算法正常排三栏，避免版面散掉。代价是宽屏打开时排版会变（面板位置重排），
    # 但内容与阅读顺序不变；要"完全一致"的场合请用导出的 PNG。
    f"@media (max-width: {_LOCK_WIDTH + 40}px) {{"
    f" .am-sheet {{ width: {_LOCK_WIDTH}px; max-width: {_LOCK_WIDTH}px; margin: 0 auto; }} }}"
    f"</style>"
)


def clean_page(path: Path) -> int:
    """给 am 产出的页面做几道清理，就地改写。返回改动次数。"""
    html = path.read_text(encoding="utf-8")
    original = html
    changes = 0

    stripped = _COLOPHON_RE.sub("", html)
    if stripped != html:
        html = stripped
        changes += 1

    for style_id, style in (("eoc-uniform-font", _FONT_OVERRIDE), ("eoc-width-lock", _WIDTH_LOCK)):
        if f'id="{style_id}"' not in html:
            html = (
                html.replace("</head>", style + "</head>", 1)
                if "</head>" in html
                else style + html
            )
            changes += 1

    if html != original:
        path.write_text(html, encoding="utf-8", newline="\n")
    return changes


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def resolve_image_tool(explicit: str | None) -> Path:
    """找出 html_to_image.mjs。

    正常情况它和本脚本同在 tools/ 下；但如果有人把 render_report.py 复制到别处跑，
    相对路径就会落空，所以再退回 cwd。找不到时报的错要能直接照着修。
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise InputError(f"--image-tool 指向的文件不存在：{path}")
        return path
    tried = []
    here = Path(__file__).resolve().parent / HTML_TO_IMAGE_NAME
    tried.append(here)
    if here.is_file():
        return here
    cwd = Path.cwd() / HTML_TO_IMAGE_NAME
    tried.append(cwd)
    if cwd.is_file():
        return cwd
    raise InputError(
        "找不到出图工具 html_to_image.mjs，已试："
        + "、".join(str(p) for p in tried)
        + "。用 --image-tool <path> 指定（它应与本脚本同在 tools/ 下）"
    )


def default_html_path(json_path: Path) -> Path:
    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir())
    return base / "eoc_reports" / (json_path.stem + ".html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_report.py",
        description="把早矫体检报告 JSON 渲染成 shadcn 风格的 HTML（可选 PNG）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python tools/render_report.py report.json\n"
            "  python tools/render_report.py report.json -o out/report.html --png\n"
            "  python tools/render_report.py report.json --dry-run\n"
        ),
    )
    # 注意：help / epilog 会被 argparse 当 %-格式串处理，所以字面量百分号要写 %%，
    # 否则 --help 直接抛 ValueError: unsupported format character。
    parser.add_argument("report", help="report.json 路径")
    parser.add_argument(
        "-o", "--out", help="输出 HTML 路径（默认写到系统临时目录 eoc_reports/ 下）"
    )
    parser.add_argument(
        "--png",
        nargs="?",
        const="",
        default=None,
        metavar="OUT.PNG",
        help="同时导出 PNG；不带值时输出与 HTML 同名的 .png",
    )
    parser.add_argument("--am", help="am.mjs 路径（默认取系统临时目录下的 amwh 安装）")
    parser.add_argument("--node", help="node 可执行文件路径（默认 PATH 里的 node）")
    parser.add_argument(
        "--image-tool",
        help="html_to_image.mjs 路径（默认与本脚本同在 tools/ 下）",
    )
    parser.add_argument("--theme", default="shadcn", help="am 主题（默认 shadcn）")
    parser.add_argument("--template", default="sheet", help="am 模板（默认 sheet）")
    parser.add_argument(
        "--style",
        default="80",
        choices=("80", "off", "strict"),
        help="am 的 STE 检查档位（默认 80，只警告）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印 draft 与命令，不调用 am")
    parser.add_argument("--dump-draft", action="store_true", help="把 draft 打到 stdout")
    parser.add_argument("--version", action="version", version=f"render_report.py {__version__}")
    return parser


def main(argv=None) -> int:
    # 必须最先执行：argparse 的 --help / 报错信息里也有中文和 ✓，
    # 在 GBK 控制台上晚一步就会 UnicodeEncodeError。
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    try:
        json_path = Path(args.report)
        if not json_path.is_file():
            raise InputError(f"找不到输入文件：{json_path}")
        try:
            raw = json_path.read_text(encoding="utf-8-sig")  # 容错 BOM
        except OSError as exc:
            raise InputError(f"读不了输入文件：{json_path}（{exc}）")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(f"report.json 不是合法 JSON：{exc}")
        data = validate_report(data)

        draft = build_draft(data, theme=args.theme, template=args.template, style=args.style)

        html_path = Path(args.out) if args.out else default_html_path(json_path)
        draft_path = html_path.with_suffix(".draft.md")

        if args.dry_run:
            print("=== dry-run：只生成 draft 与命令，不调用 am ===")
            print(f"draft: {draft_path}")
            print(f"html : {html_path}")
            if args.png is not None:
                print(f"png  : {Path(args.png) if args.png else html_path.with_suffix('.png')}")
            print()
            print("--- draft ---")
            print(draft, end="" if draft.endswith("\n") else "\n")
            print("--- end draft ---")
            print()
            print("将执行的命令：")
            node = args.node or "<node>"
            am = args.am or str(default_am_path())
            print(
                "  "
                + fmt_cmd(
                    [
                        node,
                        am,
                        "render",
                        str(draft_path),
                        "-o",
                        str(html_path),
                        "--theme",
                        args.theme,
                        "--template",
                        args.template,
                        "--style",
                        args.style,
                        "--no-open",
                    ]
                )
            )
            if args.png is not None:
                png_path = Path(args.png) if args.png else html_path.with_suffix(".png")
                try:
                    tool_display = str(resolve_image_tool(args.image_tool))
                except InputError:
                    tool_display = f"<{HTML_TO_IMAGE_NAME}>"
                print(
                    "  "
                    + fmt_cmd(
                        [
                            node,
                            tool_display,
                            str(html_path),
                            "-o",
                            str(png_path),
                            "--width",
                            "1440",
                            "--scale",
                            "2",
                        ]
                    )
                )
            return EXIT_OK

        node = find_node(args.node)
        am_path = Path(args.am) if args.am else default_am_path()
        if not am_path.is_file():
            raise InputError(f"找不到 am.mjs：{am_path}（用 --am <path> 指定）")

        html_path.parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 无 BOM；换行统一成 \n
        draft_path.write_text(draft, encoding="utf-8", newline="\n")

        if args.dump_draft:
            print("--- draft ---")
            print(draft, end="" if draft.endswith("\n") else "\n")
            print("--- end draft ---")

        print(f"draft: {draft_path}")
        code = run_command(
            [
                node,
                str(am_path),
                "render",
                str(draft_path),
                "-o",
                str(html_path),
                "--theme",
                args.theme,
                "--template",
                args.template,
                "--style",
                args.style,
                "--no-open",
            ],
            label="am render",
        )
        if code != EXIT_OK:
            return code

        if not html_path.is_file():
            print(f"✗ am 报告成功但没找到产物：{html_path}", file=sys.stderr)
            return EXIT_RUNTIME
        # am 生成的页面要过两道清理，HTML 与 PNG 都基于清理后的版本，
        # 否则"浏览器里看到的"和"导出图"会不一致。
        changed = clean_page(html_path)
        size = html_path.stat().st_size
        print(f"html : {html_path}  ({size} B)" + (f"  已清理 {changed} 处" if changed else ""))

        if args.png is not None:
            png_path = Path(args.png) if args.png else html_path.with_suffix(".png")
            png_path.parent.mkdir(parents=True, exist_ok=True)
            tool = resolve_image_tool(args.image_tool)
            # 宽高交给 html_to_image.mjs 的默认值（1728 CSS 宽 / 1.5 倍）。
            # 不要在这里写死 --width：am 的页面在 1100px 以下把 3 列塌成 2 列，
            # 写小了导出的图就和浏览器里看到的排版不一致。
            code = run_command(
                [
                    node,
                    str(tool),
                    str(html_path),
                    "-o",
                    str(png_path),
                ],
                label="html_to_image",
            )
            if code != EXIT_OK:
                return code
            if not png_path.is_file():
                print(f"✗ 截图工具报告成功但没找到产物：{png_path}", file=sys.stderr)
                return EXIT_RUNTIME
            print(f"png  : {png_path}  ({png_path.stat().st_size} B)")

        print("产物：")
        print(f"  {html_path}")
        if args.png is not None:
            png_path = Path(args.png) if args.png else html_path.with_suffix(".png")
            print(f"  {png_path}")
        return EXIT_OK

    except InputError as exc:
        print(f"✗ 输入错误：{exc}", file=sys.stderr)
        return EXIT_INPUT
    except KeyboardInterrupt:
        print("✗ 已中断", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UnicodeEncodeError as exc:  # 极老的控制台且 reconfigure 失败时兜底
        # 只写 ASCII：这段代码跑到的前提就是当前 stdout 编不了非 ASCII
        sys.exit(
            "[render_report] console encoding cannot print the output: "
            f"{exc}. Try `chcp 65001` or PYTHONIOENCODING=utf-8."
        )
