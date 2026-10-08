# -*- coding: utf-8 -*-
"""验收：STE 警告只允许两类已知可接受项，其余一律失败。

允许的两类：

1. `paragraph-length` 落在结论大字行上 —— am 把中文分号当句末，且它的 `clean()`
   只剥标签不剥 `&nbsp;`，于是把一行大字切成了 7 段。**误报**，
   见 `reference/html-report.md` 的「已知的 STE 误报」。
2. `word ... "大概"` 落在**受访者原话**里 —— 原话不得改写，
   见 `reference/writing-style.md`。同一句词若出现在依据或正文里，**不算可接受**。

用法：

    python tools/render_report.py report.json -o out.html > render.txt 2>&1
    python tools/check_ste_allowlist.py render.txt report.json

**`render.txt` 必须同时接 stdout 和 stderr** —— am 的 STE 警告走的是 **stdout**（不是
stderr）。只用 `2>` 接会得到一个空文件，检查器于是"全部通过"，是假绿。
这条坑踩过一次，所以专门写在这里。

退出码：0 全部可接受；1 有不可接受的警告；2 用法错误
"""
from __future__ import annotations

import io
import json
import re
import sys

#: 允许的规则名。加规则必须同时改这里和 reference/html-report.md，说明为什么可接受。
ALLOWED_RULES = {"paragraph-length"}
#: 允许的「词」警告，但必须同时出现在受访者原话里才算可接受
ALLOWED_WORDS = {"大概"}

#: 警告行长这样，**注意开头有缩进**：`  L76 [word] not recommended: "大概" → use "约"`
_WARN_RE = re.compile(r"^\s*L(\d+)\s+\[([^\]]+)\]\s*(.*)$")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2

    out_text = io.open(argv[1], encoding="utf-8").read()
    data = json.load(io.open(argv[2], encoding="utf-8"))
    quotes = " ".join(a.get("quote", "") for a in data.get("answers", []))

    warnings = []
    for line in out_text.splitlines():
        m = _WARN_RE.match(line)
        if m:
            warnings.append((m.group(1), m.group(2), m.group(3)))

    print(f"  STE 警告 {len(warnings)} 条：")
    bad = []
    for lineno, rule, msg in warnings:
        if rule in ALLOWED_RULES:
            print(f"    ✓ L{lineno} [{rule}] 已知误报（大字行被当段落切句）")
            continue
        if rule == "word":
            hit = next((w for w in ALLOWED_WORDS if w in msg), None)
            if hit and hit in quotes:
                print(f"    ✓ L{lineno} [{rule}] 「{hit}」在受访者原话里，不得改写")
                continue
            if hit:
                print(f"    ✗ L{lineno} [{rule}] 「{hit}」不在原话里，应当改掉：{msg[:56]}")
                bad.append((lineno, rule, msg))
                continue
        print(f"    ✗ L{lineno} [{rule}] 不可接受：{msg[:64]}")
        bad.append((lineno, rule, msg))

    if bad:
        print(f"\n  ✗ 有 {len(bad)} 条不可接受的 STE 警告")
        return 1
    print("\n  ✓ STE 警告全部在允许清单内")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
