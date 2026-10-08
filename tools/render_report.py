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
必填字段一个都不能少，缺了直接报错退出，**不猜默认值**；uncovered 是唯一的可选字段
（缺省视为空列表，它表示"这题没覆盖到"，缺失与"没有未覆盖题"在报告里是同一种呈现）。
"""

from __future__ import annotations

import argparse
import json
import os
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

#: 可选字段（当前只有一个）
OPTIONAL_FIELDS = ("uncovered",)

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
#: 允许为 null 的字段：被跳过的题（"未覆盖"）没有分数，
#: 用 null 表示"不计分、也不进分母"，而不是用 0 顶替。
NULLABLE_FIELDS = {("answers", "score")}
ACTION_FIELDS = {
    "id": str,
    "name": str,
    "tier": str,
    "gap_ids": str,
    "now": str,
    "todo": list,
    "accept": str,
    "eta": str,
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


def _require(mapping: dict, fields: dict, where: str, *, allow_null: tuple = ()) -> None:
    for key, expected in fields.items():
        if key not in mapping:
            raise InputError(f"缺字段：{where}.{key}（类型应为 {expected.__name__}）")
        value = mapping[key]
        if value is None and key in allow_null:
            continue  # 显式允许 null：表示"未覆盖"，不是错误
        if not _type_ok(value, expected):
            hint = "或 null（表示该题未覆盖）" if key in allow_null else ""
            raise InputError(
                f"字段类型错：{where}.{key} 期望 {expected.__name__}{hint}，"
                f"实际是 {type(value).__name__}"
            )


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
            nullable = tuple(k for (grp, k) in NULLABLE_FIELDS if grp == name)
            _require(item, fields, f"{name}[{i}]", allow_null=nullable)

    for i, item in enumerate(data["next_steps"]):
        if not isinstance(item, str):
            raise InputError(f"next_steps[{i}] 必须是字符串（当前 {type(item).__name__}）")

    for i, item in enumerate(data["actions"]):
        for j, step in enumerate(item["todo"]):
            if not isinstance(step, str):
                raise InputError(f"actions[{i}].todo[{j}] 必须是字符串（当前 {type(step).__name__}）")

    uncovered = data.get("uncovered", [])
    if not isinstance(uncovered, list):
        raise InputError("uncovered 必须是数组（题号字符串列表）")
    for i, item in enumerate(uncovered):
        if not isinstance(item, str):
            raise InputError(f"uncovered[{i}] 必须是字符串（当前 {type(item).__name__}）")
    data["uncovered"] = uncovered

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
    """红线依据里的题号也写成 1-2 这种形式，和逐题明细的题号列对齐。"""
    import re as _re

    return _re.sub(
        r"\b[ABCD][0-9]{1,2}\b",
        lambda m: short_id(m.group(0)),
        text,
    )


def capsule_ids(text: str) -> str:
    """把一句话里裸写的题号（A1、B4、D2…）逐个换成胶囊。

    报告里常有一句"重点对比题号 A1 A2 A4 A5 B1 B4 B5 D2 D4"，
    九个短码连在一起就是一片字母噪声。换成胶囊之后能一眼数出几个。"""
    import re as _re

    def repl(m):
        return capsule(short_id(m.group(0)))

    return _re.sub(r"\b[ABCD][0-9]{1,2}\b", repl, text)


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


def capsule(text: str, tone: str = "plain") -> str:
    """把题号、指标号这类短码做成胶囊，别让它混在正文里当普通文字读。"""
    color = {"plain": _C_DIM, "accent": _C_ACCENT, "err": _C_ERR, "warn": _C_WARN}.get(tone, _C_DIM)
    body = single_line(text)
    return (
        '<span style="display:inline-block;padding:1px 8px;margin:0 2px;'
        f'border:1px solid {_C_LINE};border-radius:999px;background:{_C_FILL};'
        f'color:{color};font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        f'white-space:nowrap">{body}</span>'
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
    subtitle = (
        f"{single_line(data['date'])} · {headline['level']} {single_line(headline['level_name'])}"
        f" · 总分 {int(headline['raw_score'])}/100"
    )
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
    uncovered = data["uncovered"]
    uncovered_text = "、".join(inline(x) for x in uncovered) if uncovered else "无"
    rows = [
        f"机构：{inline(data['org'])}",
        f"规模：{inline(data['scale'])}",
        f"访谈日期：{inline(data['date'])}",
        f"受访者角色：{inline(data['interviewee'])}",
        f"依据：{inline(data['evidence'])}",
        f"未覆盖题：{uncovered_text}",
    ]
    return "## 报告信息\n\n```kv cols=2\n" + "\n".join(rows) + "\n```\n"


def headline_panel(data: dict) -> str:
    """结论面板：全报告唯一的视觉重心。

    等级用大字，总分用小字——读者第一眼要看到的是"我站在哪一档"，
    不是那个精确到个位的分数。原来的写法把等级和分数塞进同一行，
    还带一个红框，没有任何东西跳出来当重心。
    """
    h = data["headline"]
    level = one_line(h["level"])
    level_name = one_line(h["level_name"])
    capped = one_line(h["capped_reason"])
    score = int(h["raw_score"])

    out = [
        "## 结论",
        "",
        # 大字给等级，小字给总分与结论。读者第一眼要看到的是"我站在哪一档"。
        big(level, 64) + "&nbsp;&nbsp;" + big(level_name, 26, _C_DIM),
        "",
        small(f"总分 {score}／100　") + small(one_line(h["summary"])),
        "",
    ]
    # 红线与等级的关系必须说清：命中就说压到了哪一档，没命中也要明确说等级没被压，
    # 否则读者分不清"没命中"和"没检查"。
    if capped:
        out += ["```callout err 红线把等级压住了", capped, "```"]
    else:
        out += [
            "```callout info 红线没有压等级",
            f"四条红线一条没碰，{level} 这个等级是实打实的。",
            "```",
        ]
    return "\n".join(out) + "\n"


def level_gauge(current: str) -> str:
    """L1–L4 四档列出来，当前档打标记。四个级别的门槛不解释就没人看得懂。"""
    lines = [
        "| 等级 | 百分制区间 | 这个等级的样子 | |",
        "|---|---|---|---|",
    ]
    for lid, low, high, name, desc in LEVEL_BANDS:
        here = "**你在这里**" if lid == current else ""
        lines.append(f"| **{lid} {name}** | {low}–{high} | {desc} | {here} |")
    return "\n".join(lines)


def score_panel(data: dict) -> str:
    """分数与等级：先给四档刻度，再给四张维度得分卡。

    维度得分直接显示 18 分制的原始分。六个问题、每题 0–3 分，满分就是 18，
    不需要先折算成 100 再平均——折一次再折回来只会让读者怀疑"是不是加权了"。
    """
    h = data["headline"]
    level = one_line(h["level"])
    score = int(h["raw_score"])

    out = [
        "## 分数与等级 {span=2}",
        "",
        level_gauge(level),
        "",
        "### 四个维度各得多少",
        "",
        # 维度给 18 分制的原始分：6 道题、每题 0–3 分，满分就是 18。
        # 总分给百分制：四个维度合计满分 72 分，折合成 100 分制再评级。
        small("每个维度 6 道题、每题 0–3 分，所以满分 18 分。四个维度合计 72 分，折合成百分制后定级。"),
        "",
    ]

    for dim in data["dimensions"]:
        # dim["score"] 是 0–100 的百分制；六个问题每题满分 3 分，
        # 所以乘以 0.18 就回到 18 分制的原始分。不显示 0–100 再平均，
        # 免得读者怀疑是不是又加了一层权重。
        raw_dim = round(int(dim["score"]) * 0.18)
        out += [
            f"**{capsule('维度' + str({'A': 1, 'B': 2, 'C': 3, 'D': 4}.get(dim['id'], dim['id'])))}"
            f"　{one_line(dim['name'])}**",
            "",
            big(str(raw_dim), 40, _C_ACCENT) + small("／18"),
            "",
            f"{one_line(dim['gap'])}",
            "",
        ]
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
        lines.append(
            f"| {cell(red['name'])} "
            f"| {cell(red['verdict'])} "
            f"| {cell(compact_basis(red['basis']))} |"
        )
    return "\n".join(lines) + "\n"


def uncovered_panel(data: dict) -> str:
    uncovered = data["uncovered"]
    if not uncovered:
        return ""
    listed = "、".join(one_line(x) for x in uncovered)
    return (
        "\n## 证据强度\n\n```callout warn 有题没答\n"
        + f"{listed} 这几题受访者跳过了。跳过不计 0 分也不计满分，该维度的分数仅供参考。"
        + "\n```\n"
    )


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
        lines.append(
            f"| {capsule(short_id(ans['id']))} | {small(f'{score}/3', 13, color)} "
            f"| {cell(ans['quote'])} | {cell(ans['basis'])} |"
        )
    uncovered = [a["id"] for a in data["answers"] if a["score"] is None]
    tail = ""
    if uncovered:
        tail = (
            f"其中 {'、'.join(uncovered)} 未覆盖，既不计 0 分也不计满分，"
            "该维度的证据强度因此弱一些。"
        )
    lines += [
        "",
        f"> 共 {len(data['answers'])} 题，每题 0–3 分。{tail}",
    ]
    return "\n".join(lines) + "\n"


def priority_flow(actions: list) -> str:
    """优先序图。

    两个坑都绕开了：
    - 节点名直接写文本（`A -> B: label`），不用 `A[x]` 那种方括号写法；
    - 标签只标**跨档那次跳转**（`A -> B: P1` 读作"从这往后进入 P1"）。
      同档内相邻的两个动作不标——档位已经由 group 框说清楚了，
      每条边都标一遍反而看不清哪一步是真正的换挡点。
    """
    nodes = [f"{one_line(a['id'])} {one_line(a['name'])}" for a in actions]
    lines = []
    for i in range(len(nodes) - 1):
        nxt_tier = actions[i + 1]["tier"]
        if nxt_tier != actions[i]["tier"]:
            lines.append(f"{nodes[i]} -> {nodes[i + 1]}: {nxt_tier}")
        else:
            lines.append(f"{nodes[i]} -> {nodes[i + 1]}")
    seen: dict[str, list[str]] = {}
    for node, act in zip(nodes, actions):
        seen.setdefault(act["tier"], []).append(node)
    for tier in ("P0", "P1", "P2"):
        if tier in seen:
            lines.append(f"group {tier}: " + ", ".join(seen[tier]))
    return "\n".join(lines)


def actions_panel(data: dict) -> str:
    actions = sort_actions(data["actions"])
    out = ["## 该做什么，按先后排 {span=2}", ""]

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
            f"> 一共 {len(actions)} 个动作。P0 先做，P1 跟上，P2 排在后面。",
            "",
        ]

    for i, act in enumerate(actions, start=1):
        # 涉及题号收成一行小字。审计要能追溯到题，但它是给复核的人看的，
        # 不该抢在动作本身前面——所以放在标题下面，用最小的字号。
        ids = one_line(act["gap_ids"]).split()
        shown = " ".join(capsule(short_id(x)) for x in ids[:8])
        if len(ids) > 8:
            shown += small(f" 等 {len(ids)} 题", 12)
        out += [
            f"### {i}. {one_line(act['name'])}　{capsule(act['id'])}" + capsule(act["tier"], "accent"),
            "",
            small("涉及 " + shown, 12),
            "",
            one_line(act["now"]),
            "",
        ]
        if act["todo"]:
            out += [f"{j}. {one_line(step)}" for j, step in enumerate(act["todo"], start=1)]
            out.append("")
        out += [
            f"做到这一步算完成。{one_line(act['accept'])}",
            "",
            f"预计 {one_line(act['eta'])}。",
            "",
        ]
    return "\n".join(out) + "\n"


def roadmap_panel(data: dict) -> str:
    # span=2：四段周次的标题与交付说明在 1/3 宽列里会被压成竖排单字
    lines = ["## 90 天怎么排 {span=2}", "", "```timeline"]
    for row in data["roadmap"]:
        weeks = inline(row["weeks"])
        action = inline(row["action"])
        deliverable = inline(row["deliverable"])
        accept = inline(row["accept"])
        note = f"交付 {deliverable} ｜ 验收 {accept}"
        lines.append(f"{weeks} | {action} | {note}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def metrics_panel(data: dict) -> str:
    # span=2：三列表格放进 1/3 宽的列会被压成逐字换行，必须给足宽度
    lines = [
        "## 八个关键数字 {span=2}",
        "",
        "| 指标 | 数值 | 从哪来 |",
        "|---|---|---|",
    ]
    unknown_count = 0
    for metric in data["metrics"]:
        # 不放 ok / warn：am 会把它们换成 ✓ / ! 徽章，而读者要的是数字本身。
        value = cell(metric["value"])
        if is_unknown(metric["value"]):
            unknown_count += 1
            value = small("还不知道", 13, _C_WARN)
        lines.append(
            f"| {capsule(plain_id(metric['id']))} {cell(plain_name(metric['name']))} "
            f"| {value} | {cell(metric['note'])} |"
        )
    total = len(data["metrics"])
    lines += ["", f"> 八个数字里，{total - unknown_count} 个拿到了，{unknown_count} 个还不知道。"]

    if unknown_count:
        lines.append(
            "> 每个「还不知道」都写清了该去哪张报表取数。不估算，也不用行业均值顶替。"
        )
    return "\n".join(lines) + "\n"


def build_draft(data: dict, *, theme: str, template: str, style: str) -> str:
    # 面板顺序就是阅读顺序。宽表格（分数、红线、逐题、动作、路线图、指标）各占 2 列，
    # 剩下的窄栏留给"证据强度"这类单句提示。不再用「一、二、三」给面板编号——
    # am 会自动给面板分配 A、B、C 字母，两套编号并排出现是重复（去 AI 味规则第 6 条）。
    panels = [
        header_panel(data),
        uncovered_panel(data),
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
        print(f"html : {html_path}  ({html_path.stat().st_size} B)")

        if args.png is not None:
            png_path = Path(args.png) if args.png else html_path.with_suffix(".png")
            png_path.parent.mkdir(parents=True, exist_ok=True)
            tool = resolve_image_tool(args.image_tool)
            code = run_command(
                [
                    node,
                    str(tool),
                    str(html_path),
                    "-o",
                    str(png_path),
                    "--width",
                    "1440",
                    "--scale",
                    "2",
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
