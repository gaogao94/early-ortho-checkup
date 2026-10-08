#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""early_ortho_metrics.py —— 早矫病例脱敏 CSV 自查工具（纯标准库）

只做一件事：读一张脱敏的病例 CSV，算出 K1–K8 里**能由数据得出**的算术指标。
数据缺失（列不存在、整列为空、单元格为空或无法解析）一律打印「未知」，并写明
该从哪个字段 / 报表取证。本工具不猜数，也不用 0 顶替缺失值。

不做什么：不读也不需要姓名、电话、身份证等个人信息；不做诊断；不给医疗、
法律、会计结论。

用法示例：

    python early_ortho_metrics.py --csv cases.csv
    python early_ortho_metrics.py --csv cases.csv --status-active 在治 --status-closed 已结案
    python early_ortho_metrics.py --csv 导出_2026Q3.csv --as-of 2026-09-30 \\
        --col-case-id 病例号 --col-plan-end-date 计划结束日期 --col-fee 实收金额

列名默认为 case_id / doctor / status / start_date / plan_end_date / actual_end_date /
visits / chair_minutes / restarts / fee / material_cost，可用 --col-* 覆盖。
日期支持 YYYY-MM-DD 与 YYYY/M/D；文件编码按 UTF-8 读，带 BOM 也认。
月份折算统一按 365.25 / 12 = 30.4375 天。

虚构样例 CSV 与完整示例命令见本文件末尾注释。
"""

import argparse
import csv
import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

DAYS_PER_MONTH = 30.4375  # 365.25 / 12，全部「月」口径都用它折算，便于复算

# (字段键, 默认列名, 该字段缺失时的取证建议)
FIELDS = (
    ("case_id", "case_id", "病例管理系统 · 病例列表"),
    ("doctor", "doctor", "病例管理系统 · 经治医生字段"),
    ("status", "status", "病例管理系统 · 病例状态（在治 / 结案）字段"),
    ("start_date", "start_date", "病例详情 · 开始治疗日期"),
    ("plan_end_date", "plan_end_date", "方案或病例详情 · 计划结束日期"),
    ("actual_end_date", "actual_end_date", "结案记录 · 结案日期"),
    ("visits", "visits", "挂号或就诊记录 · 按病例汇总的就诊次数"),
    ("chair_minutes", "chair_minutes", "椅位或叫号系统 · 椅位占用分钟数"),
    ("restarts", "restarts", "病例管理系统 · 重启 / 二次治疗标识"),
    ("fee", "fee", "收费系统 · 按病例汇总的收费金额"),
    ("material_cost", "material_cost", "耗材出入库或加工件台账（精确到病例）"),
)

DATE_FIELDS = ("start_date", "plan_end_date", "actual_end_date")
NUM_FIELDS = ("visits", "chair_minutes", "restarts", "fee", "material_cost")

DEFAULT_COL = {key: col for key, col, _ in FIELDS}
SOURCE = {key: src for key, _, src in FIELDS}

NO_MEDICAL_JUDGEMENT = (
    "本工具不做医疗判断。以上只是对一张 CSV 的算术汇总；是否构成临床、"
    "财务或合规问题，请由相应专业人员判断。"
)

EPILOG = """\
示例：
  python early_ortho_metrics.py --csv cases.csv
  python early_ortho_metrics.py --csv cases.csv --as-of 2026-09-30 --status-active 在治
  python early_ortho_metrics.py --csv 导出.csv --col-case-id 病例号 --col-plan-end-date 计划结束日期

本文件末尾附有一份虚构样例 CSV，可直接照抄成 cases.csv 试用。
本工具不做医疗判断，也不联网、不上传任何数据。
"""


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

def parse_date(text):
    """支持 YYYY-MM-DD 与 YYYY/M/D（个位数月日也认）。无法解析返回 None。"""
    s = (text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(text):
    """去掉千分位与常见货币符号后转 float。无法解析返回 None。"""
    s = (text or "").strip()
    if not s:
        return None
    for ch in (",", "，", "¥", "￥", "元", " "):
        s = s.replace(ch, "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_parser():
    parser = argparse.ArgumentParser(
        prog="early_ortho_metrics.py",
        description=(
            "早矫病例脱敏 CSV 自查工具：只计算 K1–K8 中可由数据得出的算术指标。"
            "数据缺失一律报「未知」并给出取证方式，绝不猜数、不用 0 顶替。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("--csv", required=True, metavar="PATH",
                        help="脱敏病例 CSV 的路径（UTF-8，带不带 BOM 均可）")
    parser.add_argument("--as-of", default=date.today().isoformat(), metavar="YYYY-MM-DD",
                        help="统计截止日期，默认今天")
    parser.add_argument("--status-active", default="在治", metavar="VALUE",
                        help="状态列中代表「在册 / 在治」的取值，默认：在治")
    parser.add_argument("--status-closed", default="已结案", metavar="VALUE",
                        help="状态列中代表「已结案」的取值，默认：已结案")
    for key, default_col, src in FIELDS:
        parser.add_argument(
            "--col-" + key.replace("_", "-"),
            dest="col_" + key,
            default=default_col,
            metavar="NAME",
            help="%s 对应的列名（默认：%s；缺该列时的取证建议：%s）" % (key, default_col, src),
        )
    return parser


def read_table(path, colmap):
    """读 CSV。返回 (table, error_message)。table = {header, index, rows}。"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return None, "文件是空的，连表头都没有。"
            header = [h.strip() for h in header]
            index = {}
            for key, _col, _src in FIELDS:
                name = (colmap.get(key) or "").strip()
                index[key] = header.index(name) if name in header else None
            rows = []
            for lineno, raw in enumerate(reader, start=2):
                if not raw or all((cell or "").strip() == "" for cell in raw):
                    continue
                row = {"_line": lineno}
                for key, _col, _src in FIELDS:
                    i = index[key]
                    row[key] = raw[i].strip() if (i is not None and i < len(raw)) else None
                rows.append(row)
    except OSError as exc:
        return None, "读不了这个文件：%s" % exc
    except UnicodeDecodeError:
        return None, "文件不是 UTF-8（含 BOM 也认）；请另存为 UTF-8 后重试。"
    except csv.Error as exc:
        return None, "CSV 解析失败：%s" % exc
    return {"header": header, "index": index, "rows": rows}, None


def collect(table, key, parser):
    """按字段取值。返回 {present, ok:[(row, value)], bad:[行号], blank: 个数}。"""
    result = {"present": table["index"].get(key) is not None, "ok": [], "bad": [], "blank": 0}
    if not result["present"]:
        return result
    for row in table["rows"]:
        raw = row.get(key)
        if raw is None or raw == "":
            result["blank"] += 1
            continue
        value = parser(raw)
        if value is None:
            result["bad"].append(row["_line"])
            continue
        result["ok"].append((row, value))
    return result


def as_map(collected):
    return {row["_line"]: value for row, value in collected["ok"]}


# --------------------------------------------------------------------------
# 输出小工具
# --------------------------------------------------------------------------

def unknown(colmap, key, present):
    """统一的「未知」文案：缺列与列存在但无可用数据分开说，都带取证建议。

    key 可以是单个字段键，也可以是一组字段键。
    """
    keys = [key] if isinstance(key, str) else list(key)
    cols = "、".join(colmap.get(k) or DEFAULT_COL[k] for k in keys)
    srcs = "；".join(SOURCE[k] for k in keys)
    tail = "（该列存在但无可用数据）" if (present and len(keys) == 1) else ""
    return "未知（缺少字段: %s%s，建议从 %s 导出）" % (cols, tail, srcs)


def half_up(value, digits=0):
    """四舍五入半上（ROUND_HALF_UP），让读者拿计算器复算时对得上。

    统一经 Decimal(str(x)) 走十进制，避免二进制浮点在正好 .5 的平局上被
    银行家舍入（例如 9750.125 应显示 9750.13，而不是 9750.12）。
    """
    if value is None:
        return None
    return Decimal(str(float(value))).quantize(Decimal(1).scaleb(-digits),
                                               rounding=ROUND_HALF_UP)


def money(value):
    return "未知" if value is None else "¥%s" % format(half_up(value, 2), ",.2f")


def months(value):
    return "未知" if value is None else "%.1f 个月" % half_up(value, 1)


def ratio(part, whole):
    if not whole:
        return "—"
    return "%.1f%%" % half_up(100.0 * part / whole, 1)


def mean(values):
    return sum(values) / len(values) if values else None


def line(label, value):
    print("  %s: %s" % (label, value))


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------

METRIC_LABELS = {
    "K1": "在册早矫病例数",
    "K2": "超计划时长（延期）病例占比",
    "K3": "计划结束时长 / 实际结束时长",
    "K4": "平均延期月数",
    "K5": "计划外复诊率",
    "K6": "平均椅位占用时长 / 每例就诊次数",
    "K7": "重启率 / 二次治疗率",
    "K8": "单例就诊次单价",
}


def render(args, as_of, table, colmap):
    rows = table["rows"]
    present = {key: table["index"].get(key) is not None for key, _c, _s in FIELDS}

    dates = {key: collect(table, key, parse_date) for key in DATE_FIELDS}
    nums = {key: collect(table, key, parse_number) for key in NUM_FIELDS}
    status = collect(table, "status", lambda s: s.strip())
    status_of = as_map(status)
    plan_end = as_map(dates["plan_end_date"])
    actual_end = as_map(dates["actual_end_date"])
    start = as_map(dates["start_date"])

    print("早矫病例数据自查 · K1–K8（可由数据得出的部分）")
    print("=" * 64)
    line("数据文件", args.csv)
    line("统计截止", "%s（--as-of）" % as_of.isoformat())
    line("状态口径", "在册 =「%s」；已结案 =「%s」" % (args.status_active, args.status_closed))
    line("数据行数", "%d 行（空行与空白单元格不计为 0）" % len(rows))

    # ---------------- 底数 ----------------
    print("")
    print("[底数]")
    active_rows = closed_rows = None
    status_usable = present["status"] and bool(status["ok"])
    if status_usable:
        active_rows = [r for r in rows if status_of.get(r["_line"]) == args.status_active]
        closed_rows = [r for r in rows if status_of.get(r["_line"]) == args.status_closed]
        print("  K1 %s: %d" % (METRIC_LABELS["K1"], len(active_rows)))
        line("已结案病例数", "%d" % len(closed_rows))
        others = {}
        blanks = 0
        for row in rows:
            value = status_of.get(row["_line"])
            if value in (args.status_active, args.status_closed):
                continue
            if value is None:
                blanks += 1
                continue
            others[value] = others.get(value, 0) + 1
        if others:
            shown = "，".join("%s×%d" % (k, v) for k, v in sorted(others.items()))
            line("其他状态", "%s（未计入在册 / 已结案）" % shown)
        if blanks:
            line("状态为空", "%d 例（无法判断在册 / 已结案，未计入任何一类）" % blanks)
    else:
        # 列不存在，或整列都是空值：都算「未知」，绝不用 0 顶替
        missing = unknown(colmap, "status", present["status"])
        print("  K1 %s: %s" % (METRIC_LABELS["K1"], missing))
        line("已结案病例数", missing)

    # ---------------- 超期与延期 ----------------
    print("")
    print("[超期与延期]")
    if active_rows is None:
        print("  K2 %s: %s" % (METRIC_LABELS["K2"], unknown(colmap, "status", present["status"])))
    elif not dates["plan_end_date"]["present"]:
        print("  K2 %s: %s" % (METRIC_LABELS["K2"], unknown(colmap, "plan_end_date", False)))
    else:
        with_plan = [r for r in active_rows if r["_line"] in plan_end]
        overdue = [r for r in with_plan if plan_end[r["_line"]] < as_of]
        line("K2 " + METRIC_LABELS["K2"], "%d / %d = %s"
             % (len(overdue), len(active_rows), ratio(len(overdue), len(active_rows))))
        if len(with_plan) < len(active_rows):
            line("（提示）", "另有 %d 例在册病例缺计划结束日期，无法判断是否超期"
                 "（仍留在分母，未计入分子）" % (len(active_rows) - len(with_plan)))

    # K4 —— 分两组分别给，避免把「还在拖的」和「已结案但晚了的」混成一个数
    if dates["plan_end_date"]["present"]:
        if active_rows is not None:
            late_active = [plan_end[r["_line"]] for r in active_rows if r["_line"] in plan_end
                           and plan_end[r["_line"]] < as_of]
            if late_active:
                avg = mean([(as_of - d).days / DAYS_PER_MONTH for d in late_active])
                line("K4 在册超期病例平均已超期", "%s（n=%d；= 截止日 − 计划结束日，按 30.4375 天/月折算）"
                     % (months(avg), len(late_active)))
            else:
                line("K4 在册超期病例平均已超期",
                     "0 例（按 %s 口径，没有计划结束日早于截止日的在册病例）" % as_of.isoformat())
        else:
            line("K4 在册超期病例平均已超期", unknown(colmap, "status", present["status"]))
        if closed_rows is not None and dates["actual_end_date"]["present"]:
            late_closed = []
            for row in closed_rows:
                lid = row["_line"]
                if lid in plan_end and lid in actual_end and actual_end[lid] > plan_end[lid]:
                    late_closed.append((actual_end[lid] - plan_end[lid]).days / DAYS_PER_MONTH)
            if late_closed:
                line("K4 已结案病例平均延期", "%s（n=%d，只含结案日晚于计划结束日的病例）"
                     % (months(mean(late_closed)), len(late_closed)))
            else:
                line("K4 已结案病例平均延期", "0 例（已结案病例里没有晚于计划结束日结案的）")
        else:
            if closed_rows is None:
                line("K4 已结案病例平均延期", unknown(colmap, "status", present["status"]))
            else:
                line("K4 已结案病例平均延期",
                     unknown(colmap, "actual_end_date", present["actual_end_date"]))
    else:
        print("  K4 %s: %s" % (METRIC_LABELS["K4"], unknown(colmap, "plan_end_date", False)))

    # K3 —— 计划时长 vs 实际时长
    if dates["start_date"]["present"] and dates["plan_end_date"]["present"]:
        plan_days = []
        reversed_dates = 0
        for row in rows:
            lid = row["_line"]
            if lid in start and lid in plan_end:
                delta = (plan_end[lid] - start[lid]).days
                if delta < 0:
                    reversed_dates += 1
                else:
                    plan_days.append(delta)
        if plan_days:
            line("K3 计划结束时长均值", "%s（n=%d，= 计划结束日 − 开始日）"
                 % (months(mean([d / DAYS_PER_MONTH for d in plan_days])), len(plan_days)))
        else:
            line("K3 计划结束时长均值", unknown(colmap, "plan_end_date", True))
        if reversed_dates:
            line("（提示）", "%d 例计划结束日早于开始日，日期可疑，已排除出均值" % reversed_dates)
    else:
        line("K3 计划结束时长均值",
             unknown(colmap, [k for k in ("start_date", "plan_end_date") if not present[k]], False))

    if closed_rows is None:
        line("K3 实际结束时长均值", unknown(colmap, "status", present["status"]))
    elif not (present["start_date"] and present["actual_end_date"]):
        line("K3 实际结束时长均值",
             unknown(colmap, [k for k in ("start_date", "actual_end_date") if not present[k]], False))
    else:
        actual_days = []
        for row in closed_rows:
            lid = row["_line"]
            if lid in start and lid in actual_end:
                delta = (actual_end[lid] - start[lid]).days
                if delta >= 0:
                    actual_days.append(delta / DAYS_PER_MONTH)
        if actual_days:
            line("K3 实际结束时长均值", "%s（n=%d，仅已结案病例，= 结案日 − 开始日）"
                 % (months(mean(actual_days)), len(actual_days)))
        else:
            line("K3 实际结束时长均值", unknown(colmap, "actual_end_date", True))

    # ---------------- 效率 ----------------
    print("")
    print("[效率]")
    if nums["visits"]["present"]:
        visits = [v for _r, v in nums["visits"]["ok"]]
        if visits:
            line("K6 每例平均就诊次数", "%.1f 次/例（n=%d）"
                 % (half_up(mean(visits), 1), len(visits)))
        else:
            line("K6 每例平均就诊次数", unknown(colmap, "visits", True))
    else:
        line("K6 每例平均就诊次数", unknown(colmap, "visits", False))

    if nums["chair_minutes"]["present"]:
        chairs = [v for _r, v in nums["chair_minutes"]["ok"]]
        if chairs:
            line("K6 椅位占用时长合计", "%.0f 分钟" % half_up(sum(chairs), 0))
            line("K6 每例平均椅位占用", "%.1f 分钟（n=%d）"
                 % (half_up(mean(chairs), 1), len(chairs)))
        else:
            line("K6 椅位占用时长", unknown(colmap, "chair_minutes", True))
    else:
        line("K6 椅位占用时长", unknown(colmap, "chair_minutes", False))

    # ---------------- 质量 ----------------
    print("")
    print("[质量（只算 CSV 里已有标识的部分）]")
    if nums["restarts"]["present"]:
        restarts = [v for _r, v in nums["restarts"]["ok"]]
        if restarts:
            affected = sum(1 for v in restarts if v > 0)
            line("K7 重启病例", "%d / %d = %s（该字段合计重启 %.0f 次）"
                 % (affected, len(restarts), ratio(affected, len(restarts)),
                    half_up(sum(restarts), 0)))
        else:
            line("K7 重启率", unknown(colmap, "restarts", True))
    else:
        line("K7 重启率", unknown(colmap, "restarts", False))
    line("K5 计划外复诊率",
         "未知（本工具不读取「计划外处理标识」字段，无法把托槽脱落、钢丝扎嘴等分出来；"
         "建议从 就诊记录 · 计划外处理标识 导出后单独统计）")

    # ---------------- 收入与成本 ----------------
    print("")
    print("[收入与成本]")
    fees = as_map(nums["fee"])
    visit_map = as_map(nums["visits"])
    fee_rows = [r for r in rows if r["_line"] in fees]
    if nums["fee"]["present"] and fee_rows:
        fee_sum = sum(fees.values())
        line("K8 单例收入均值", "%s（n=%d）" % (money(fee_sum / len(fee_rows)), len(fee_rows)))
        both = [r for r in fee_rows if r["_line"] in visit_map]
        total_visits = sum(visit_map[r["_line"]] for r in both)
        total_fee = sum(fees[r["_line"]] for r in both)
        if both and total_visits > 0:
            line("K8 单例就诊次单价（收入侧）",
                 "%s = 收入合计 %s ÷ 就诊次数合计 %.0f 次（n=%d 例）"
                 % (money(total_fee / total_visits), money(total_fee),
                    half_up(total_visits, 0), len(both)))
            per_case = [fees[r["_line"]] / visit_map[r["_line"]]
                        for r in both if visit_map[r["_line"]] > 0]
            if per_case:
                line("  按例计算再平均", "%s（n=%d，与上面的汇总口径可能有差）"
                     % (money(mean(per_case)), len(per_case)))
        else:
            line("K8 单例就诊次单价（收入侧）",
                 unknown(colmap, "visits", present["visits"]))
    else:
        line("K8 单例收入均值", unknown(colmap, "fee", present["fee"]))
        line("K8 单例就诊次单价（收入侧）", unknown(colmap, "fee", present["fee"]))

    mats = as_map(nums["material_cost"])
    if nums["material_cost"]["present"] and mats:
        mat_sum = sum(mats.values())
        line("成本侧（粗略）", "材料成本合计 %s；每例平均 %s（n=%d）"
             % (money(mat_sum), money(mat_sum / len(mats)), len(mats)))
        if nums["visits"]["present"]:
            shared = [r for r in rows if r["_line"] in mats and r["_line"] in visit_map]
            shared_visits = sum(visit_map[r["_line"]] for r in shared)
            shared_cost = sum(mats[r["_line"]] for r in shared)
            if shared_visits > 0:
                line("  材料成本 / 就诊次数", "%s（只摊到同时有材料成本与就诊次数的 %d 例）"
                     % (money(shared_cost / shared_visits), len(shared)))
        both_cost = [r for r in rows if r["_line"] in mats and r["_line"] in fees]
        if both_cost:
            inc = sum(fees[r["_line"]] for r in both_cost)
            cost = sum(mats[r["_line"]] for r in both_cost)
            line("  粗略毛利（仅扣材料）", "%s = 收入 %s − 材料 %s（n=%d）"
                 % (money(inc - cost), money(inc), money(cost), len(both_cost)))
            if inc > 0:
                line("  粗略毛利率", "%.1f%%" % half_up(100.0 * (inc - cost) / inc, 1))
            line("  注意", "成本侧只含材料成本，未含人工、椅位与其它分摊，不等于真实毛利")
        else:
            line("  粗略毛利（仅扣材料）",
                 "未知（材料成本与收费金额没有能对上的同一病例，建议核对两边的病例号）")
    else:
        line("成本侧（粗略）", unknown(colmap, "material_cost", present["material_cost"]))

    # ---------------- 数据质量 ----------------
    print("")
    print("[数据质量]")
    notes = []
    for key in DATE_FIELDS + NUM_FIELDS:
        item = dates[key] if key in dates else nums[key]
        if not item["present"]:
            notes.append("字段 %s：CSV 里没有这一列" % (colmap.get(key) or DEFAULT_COL[key]))
            continue
        if item["bad"]:
            shown = "、".join(str(n) for n in item["bad"][:5])
            more = "，等" if len(item["bad"]) > 5 else ""
            notes.append("字段 %s：%d 行无法解析（行号 %s%s），已跳过，不按 0 计"
                         % (colmap.get(key) or DEFAULT_COL[key], len(item["bad"]), shown, more))
        if item["blank"] and not item["ok"]:
            notes.append("字段 %s：整列为空" % (colmap.get(key) or DEFAULT_COL[key]))
    if not notes:
        notes.append("参与计算的字段都能正常解析。")
    for note in notes:
        print("  - %s" % note)

    print("")
    print("-" * 64)
    print(NO_MEDICAL_JUDGEMENT)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")  # 控制台编码不支持中文时也不炸
        except (ValueError, OSError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    as_of = parse_date(args.as_of)
    if as_of is None:
        parser.error("--as-of 需要 YYYY-MM-DD 或 YYYY/M/D 格式，收到：%s" % args.as_of)
    if args.status_active == args.status_closed:
        parser.error("--status-active 与 --status-closed 不能是同一个取值：%s" % args.status_active)

    colmap = {key: getattr(args, "col_" + key) for key, _c, _s in FIELDS}
    table, error = read_table(args.csv, colmap)
    if error:
        print("错误：%s" % error, file=sys.stderr)
        return 2
    if not table["rows"]:
        print("错误：%s 里除了表头没有数据行。" % args.csv, file=sys.stderr)
        return 2

    render(args, as_of, table, colmap)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# --------------------------------------------------------------------------
# 虚构样例 CSV（照抄成 cases.csv 即可试用；数据全部虚构，勿替换为真实数据）
#
# case_id,doctor,status,start_date,plan_end_date,actual_end_date,visits,chair_minutes,restarts,fee,material_cost
# C0001,医生A,已结案,2024/3/5,2025-09-05,2025-10-20,16,880,0,16800,2100
# C0002,医生A,在治,2025-01-12,2026-07-12,,9,450,0,15000,
# C0003,医生B,在治,2024-11-02,2026-05-02,,22,1210,1,19800,2600
# C0004,医生B,在治,2025-06-18,2027-06-18,,6,300,0,18000,
# C0005,医生C,已结案,2023/9/1,2025-03-01,2025-02-10,14,700,0,12800,1500
# C0006,医生C,在治,2025-03-30,2026-09-30,,4,200,0,16000,
#
# 示例命令（列名与上面一致，所以不用写 --col-*）：
#   python early_ortho_metrics.py --csv cases.csv --as-of 2026-10-01 \
#       --status-active 在治 --status-closed 已结案
#
# 如果导出的表头是中文，用 --col-* 映射，例如：
#   python early_ortho_metrics.py --csv 导出.csv --as-of 2026-09-30 \
#       --col-case-id 病例号 --col-plan-end-date 计划结束日期 --col-fee 实收金额
# --------------------------------------------------------------------------
