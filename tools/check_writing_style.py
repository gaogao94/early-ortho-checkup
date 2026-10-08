#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_writing_style.py — 检查报告草稿里的 AI 味与可读性问题。

用法：
    python tools/check_writing_style.py <draft.md>            # 检查一份草稿
    python tools/check_writing_style.py <report.json>         # 先渲染成草稿再检查
    python tools/check_writing_style.py --render report.json  # 同上（显式）

退出码：0 = 通过；1 = 有问题；2 = 用法或输入错误。

规则来自 reference/writing-style.md，只检查**能机检**的那部分。判断类问题
（比喻贴不贴切、段落是否论证充分）不在范围内，机器判不了。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

# --- 规则表 ---------------------------------------------------------------- #
# 每条：编号、说明、正则、例外说明。正则按行匹配。
RULES: list[tuple[str, str, str, str]] = [
    (
        "colon-scaffold",
        "提示语引出的冒号（现状：/要做的事：/验收标准：/结论：这类栏目式写法）",
        r"(现状|要做的事|验收标准|预计见效时间|结论|核心是|关键在于|原因如下|本质上|换句话说|一句话总结|这意味着|这表明|这说明)[：:]",
        "改成完整句子，把内容直接说出来",
    ),
    (
        "empty-list-lead",
        "空转句：一行以冒号收尾，只为宣布下面有列表",
        r"^\s*[^\n|`#]{0,30}[：:]\s*$",
        "把这句话写成有内容的判断，或删掉",
    ),
    (
        "em-dash",
        "破折号滥用",
        r"——",
        "直接写完整句子，或用逗号、句号",
    ),
    (
        "reversal",
        "翻案腔（不是……而是……／并非……而是……／看似……实则……）",
        r"(不是|并非|不在于|与其说)[^。；\n]{0,20}(而是|而在于)|看似[^。\n]{0,20}实则|表面[^。\n]{0,20}实际",
        "直接从正面下判断，先给判断再给依据",
    ),
    (
        "starter-cliche",
        "禁用起手式",
        r"(说白了|说穿了|先说结论|只做一件事)",
        "删掉起手式，直接给判断",
    ),
    (
        "ordinal-heading",
        "序数词当小标题（一、二、三 通篇编号）",
        r"^#{2,4}\s*[一二三四五六七八九十]+、",
        "删掉编号，保留小标题文字",
    ),
    (
        "road-sign",
        "句首连接词当路标（然而／此外／与此同时／总而言之 开头）",
        r"^\s*(然而|因此|此外|与此同时|换言之|总而言之)[，,]",
        "把连接词移到主语后面，或换成「不过」「其实」",
    ),
    (
        "translation-shell",
        "翻译腔前置话题壳（对于……来说／就……而言／关于……）",
        r"^\s*(对于[^，。\n]{0,12}来说|就[^，。\n]{0,12}而言|关于[^，。\n]{0,12}[，,])",
        "把对象直接放到主语位置，删掉壳子",
    ),
    (
        "too-many-parentheses",
        "括号里的补充说明太多（一行两个以上）",
        r"(（[^）]*）[^\n]{0,40}){2,}",
        "把补充说明并进句子，或另起一句",
    ),
    (
        "dense-enumeration",
        "顿号串起三项以上，一行内出现两处以上",
        r"(、[^，。；\n]{0,12}){2,}[^。\n]{0,20}(、[^，。；\n]{0,12}){2,}",
        "能概括就别逐项列举；必须保留时改变其中一项的句法",
    ),
]

#: 不检查的行：表格分隔、代码块围栏、am 组件行、标题行（标题里的冒号是允许的）
SKIP_LINE = re.compile(r"^\s*(\||```|---|~~~|>|\*\*[^*]+\*\*：)")
#: 允许的冒号用法：引出人物原话、网址、时间（06:30）、机器字段
ALLOW_COLON = re.compile(r"(说|问|答)[：:]|https?[：:]|\d{1,2}:\d{2}|case_id[：:]")


def load_draft(path: str) -> str:
    """接受草稿 .md 或报告 .json。给 .json 时直接读同目录同名 .draft.md。"""
    if path.endswith(".json"):
        cand = path[: -len(".json")] + ".draft.md"
        if not os.path.exists(cand):
            raise SystemExit(
                f"✗ 找不到 {cand}。先渲染：python tools/render_report.py {path} --dry-run > 草稿"
            )
        path = cand
    return io.open(path, encoding="utf-8").read()


def in_fence(lines: list[str]) -> list[bool]:
    """标出每一行是否在 ``` 围栏内（代码块不参与文案检查）。"""
    flags, inside = [], False
    for line in lines:
        if line.lstrip().startswith("```"):
            flags.append(True)
            inside = not inside
            continue
        flags.append(inside)
    return flags


def check(text: str) -> list[tuple[str, int, str, str, str]]:
    """返回 [(规则编号, 行号, 行内容, 说明, 改法)]。"""
    lines = text.splitlines()
    fenced = in_fence(lines)
    hits = []
    for i, line in enumerate(lines, start=1):
        if fenced[i - 1]:
            continue
        if SKIP_LINE.match(line):
            continue
        if len(line) > 200:  # 单行过长通常是被压平的表格，跳过
            continue
        for rid, desc, pat, fix in RULES:
            m = re.search(pat, line)
            if not m:
                continue
            if rid in ("colon-scaffold", "empty-list-lead") and ALLOW_COLON.search(line):
                continue
            hits.append((rid, i, line.strip()[:90], desc, fix))
    return hits


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    if not os.path.exists(path):
        print(f"✗ 找不到文件：{path}")
        return 2

    try:
        text = load_draft(path)
    except SystemExit as exc:
        print(exc)
        return 2

    hits = check(text)
    print(f"文案检查：{os.path.basename(path)}")
    print(f"  规则 {len(RULES)} 条，命中 {len(hits)} 处")
    if not hits:
        print("  ✓ 通过")
        return 0

    by_rule: dict[str, list] = {}
    for h in hits:
        by_rule.setdefault(h[0], []).append(h)
    for rid, group in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        desc, fix = group[0][3], group[0][4]
        print(f"\n  [{rid}] {desc}  ×{len(group)}")
        print(f"    改法：{fix}")
        for _, ln, content, _, _ in group[:4]:
            print(f"    L{ln}: {content}")
        if len(group) > 4:
            print(f"    …还有 {len(group) - 4} 处")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
