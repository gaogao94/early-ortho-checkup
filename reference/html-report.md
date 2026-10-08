# HTML 报告规范（answer-me-with-html）

本文件规定《早矫管理体检报告》的 **HTML 版**怎么生成。执行 SKILL.md 第 5 步出报告时读它。

- 渲染器：`answer-me-with-html`（`am`）0.4.15，单文件 Node CLI，不需要安装依赖。
- 本文件出现的每一段 `kv` / `callout` / `flow` / `timeline` / 表格状态词都用真实 CLI 跑过；命令与原始输出见 §9。**未实测的写法一律不写进本文件**；个别无法确认的点会明确标注"不确定"。
- 报告数据一律虚构或来自受访者自述，**不得**出现真实患者信息。

---

## 1. 什么时候出 HTML，什么时候只出 Markdown

**判据（一句话）**：报告要发给别人看（老板、合伙人、店长）、要留存或转发、或者要让对方点开一个文件就懂 → 出 HTML；只在对话里给受访者本人看 → 只出 Markdown。

**默认动作**：先在对话里给 Markdown 报告（SKILL.md 的骨架）。出现下面任一条时，**追加**一份 HTML，并把文件路径给受访者：

| 触发条件 | 例子 |
|---|---|
| 受访者说要把报告给老板/合伙人/店长看 | "我想发给我们院长" |
| 报告要留存、归档、跨设备打开 | "存个档，下季度对比" |
| 需要一屏看清结论再看细节 | "给我一页纸能看完的" |

**内容一致性（硬约束）**：

- HTML 与 Markdown 是**同一份数据的两种呈现**，不是两份报告。等级、四维分、总分、红线结论、动作顺序、K1–K8 数值、逐题判分必须逐字一致。
- HTML 里**不得**出现 Markdown 报告里没有的结论、数字或建议。
- 生成顺序固定：先把 Markdown 报告写完（含全部数字与判分账目）→ 再从同一份账目写 draft。**draft 的数字直接抄 Markdown，不重算、不四舍五入第二次。**

---

## 2. 主题与模板固定值

draft 的 frontmatter 固定写：

```yaml
template: sheet
theme: shadcn
cols: 3
```

| 键 | 固定值 | 理由 |
|---|---|---|
| `theme` | `shadcn` | 圆角卡片、细边框、克制阴影，适合"给老板看的经营报告"。`blueprint` 是工程图纸风、`paper` 是纸面手稿风，都不适合经营结论 |
| `template` | `sheet` | 一屏概览式多面板网格。报告是"看结论"不是"读长文" |
| `cols` | `3` | sheet 的最大列数。本报告 9 个面板（含 1 个无标题栏的报告头）在 3 列下排满，没有半空行（实测） |
| `title` | 早矫管理体检报告 | 固定标题 |
| `subtitle` | `<机构名> · <访谈日期> · 结论 <等级> <名称>` | 副标题是给人一眼看的结论行 |
| `mode` | **不写** | 默认 `auto` 跟随阅读者系统；页面右上角有主题切换按钮。要固定浅色可写 `mode: light`（实测可渲染） |
| `lang` | **不写** | draft 是中文，am 自动按中文做 STE 检查 |

**`doc` 模板是备选**，判据：报告要当长文**按顺序读**（深挖某个维度、附大量访谈摘录）时用 `doc`；常规的 9 面板体检报告用 `sheet`。用法是把 `template` 换成 `doc`，其余不变。同一份 draft 在 `doc` 下实测渲染正常（见 §9 CMD2），面板数与组件统计不变。

**不要手写 `span`。** sheet 在浏览器里按内容自动给宽面板整行宽度：实测本报告的四维得分、优先改进动作、八个关键指标、逐题明细四个面板被自动加上 `am-span-wide`。手写 `span` 只会干扰。

---

## 3. 面板映射表

Markdown 报告的 8 个部分加报告头，映射到 8 个面板。**面板编号由 am 自动分配（A、B、C…），draft 里不要再写「一、二、三」**——两套编号并排是重复。

| # | 面板标题 | 组件 | 为什么用这个组件 |
|---|---|---|---|
| A | `## 报告信息 {bare}` | `kv cols=2` | 机构、规模、日期、受访者、依据是键值对，不是叙述；`{bare}` 去掉标题栏，正好当页眉块 |
| B | `## 结论` | `callout info` + 命中红线时的 `callout err` | 结论必须第一眼看到。红线是"质"的判断，单独用红条标出来 |
| C | `## 分数与等级 {span=2}` | Markdown 表格 + 维度竖杠行 | 报告里唯一需要"一眼看懂处境"的地方：L1–L4 四档列全、当前档整行高亮；下面接四行维度得分 |
| D | `## 四条红线 {span=2}` | Markdown 表格 | 4 条红线逐条给"命中 / 未命中"，**命中的整条标红** |
| E | `## 逐题明细 {span=2}` | Markdown 表格 | 24 行明细，表格是唯一合适的形式 |
| F | `## 该做什么 {span=2}` | `callout warn` + `flow LR` + 分隔线 | 开头一条"这周就开始"，然后 `flow` 表达顺序，每个动作一个待办小节、档位用 tag |
| G | `## 90 天怎么排 {span=2}` | Markdown 表格 | 四列左对齐，一行一个阶段。**不要用 `timeline`**：它把标题居中、正文塞在下面，四段并排时读不出下面那行属于哪一段 |
| H | `## 八个关键数字 {span=2}` | Markdown 表格 | 8 行 × 3 列，未知的数值列写"还不知道" |

**为什么"下一步"没有单独一节**：它和「该做什么」说的是同一件事——下一步就是动作清单里的第一件。单开一节会让读者看到两遍相似的内容，所以它并入 F 的面板开头。

**面板数量**：固定 8 个（有红线命中时结论区多一条 callout，不增加面板数）。**超过 9 个必须拆页**，不要把两份内容塞进一页。

**24 题必须全部作答。** 报告要求答题完整，缺一题就不生成——所以页面里不会出现"未覆盖""证据不足""仅供参考"这类打折说明。`tools/render_report.py` 有一道硬门禁：`answers` 不足 24 题会直接报错退出（exit 2），并列出缺哪几题。

**面板顺序**：严格按上表 A → B → C → D → E → F → G → H 写（报告信息 → 结论 → 分数等级 → 红线 → 逐题 → 动作 → 路线图 → 指标）。理由：判断在前、明细在后。不要为了排版好看调换顺序，顺序本身是结论优先的体现。

**列宽靠 `{span=2}` 控制，不是靠改 cols**：`cols` 固定写 3。三列表格（分数、红线、逐题、动作、路线图、指标）各占 2 列，否则会被压成逐字换行（实测过：K 指标表在 1/3 宽列下每个字一行）。只有报告头这类键值块留在 1 列宽的窄栏里。

### 视觉重心只有一处：结论面板

整份报告只允许一个地方抢眼球，就是结论面板。那里等级用 64px 大字，等级名 26px，总分和结论用 13px 小字——**字号差本身就是层级**。全篇其余地方一律用正文号。

判断办法：把页面缩小到 25%，还看得清的那个东西就应该是等级。如果同时有好几处在大喊，就等于没有重心。

### 不要状态词徽章

am 会把表格单元格里的 `ok` / `no` / `warn` 换成 ✓ / ✗ / ! 徽章。**本报告一律不用**：结论列直接写「命中」「未命中」，得分列直接写 `2 分`，指标列直接写数值。读者要看的是判断结果和数字，不是一排图标。

需要颜色时用行内 `<span style="color:…">`，不用徽章。`tools/render_report.py` 已经把这条写进实现，渲染后 `am-badge` 出现次数应当是 0（可 grep 校验）。

### 短码做成 tag

行内 `<span>` 的 `style` 属性 am 会原样保留（实测），所以题号、指标号、档位都做成 tag：

```html
<span style="display:inline-block;padding:1px 8px;border-radius:6px;
background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600">A1</span>
```

三条规则：

1. **题号保留维度字母。** 页面上一律写 `A1`、`B4`、`D2`——不要换成 `1-1`。带字母才知道属于哪个维度。
2. **指标号和动作号换成中文说法。** `K4` 写「指标4」，`ACT-3` 只出现在流程图的短标题里，动作标题用待办的说法（"结束病例要过一遍复核"），不出现 `ACT-3` 这个编号。
3. **一句话里的裸题号也要包起来。** 「重点对比题号 A1 A2 A4 A5 B1 B4 B5 D2 D4」九个短码连在一起就是一片字母噪声，换成 tag 才能一眼数出几个。

**字体用正文字体，不要等宽体。** 等宽体在中文报告里像代码，中文标签字形也是外挂的。

### 单位口径：维度用 18 分制，总分用百分制

- 每个维度 6 道题、每题 0–3 分，所以维度分显示 **x／18** 的原始分。
- 总分显示 **百分制**（四个维度合计 72 分折合 100 分），等级按百分制区间判定。
- 面板里必须写清这层换算（"每个维度 6 道题、每题 0–3 分，所以满分 18 分。四个维度合计 72 分，折合成百分制后定级。"）。

**不要**把维度分先折成 0–100 再平均出总分——多一次换算只会让读者怀疑"是不是又加了权重"。

**没有"未覆盖题"这个面板。** 报告要求 24 题全部作答，缺一题直接不生成，所以页面上不存在"证据不足""仅供参考"这类打折说明。渲染器会拦住不完整的输入。

**每个面板一个主题**：一个面板只回答一个问题。不要把"红线诊断"和"逐题明细"合成一个面板。

**红线命中的呈现**：走**两条**——结论面板里的 `callout err`（把命中的红线与封顶结果说在一起，最醒目）+ 面板 D 的表格（逐条给"命中 / 未命中"，命中的整条标红）。callout 只在真有命中时出现，它承载的是"这次体检有坏消息"这个信号，不是复述表格。不要把每条红线各开一个 callout。

**`callout` 计数是自检信号**：无红线命中时 2 条（结论区的"没有一票否决的问题" + 该做什么开头的"这周就开始"）；有红线命中时同样是 2 条，只是第一条变成 `err`。对不上说明面板少写或多写了。

---

## 4. 颜色约定：不用徽章，用行内颜色

am 会把表格单元格开头的 `ok` / `no` / `warn` 渲染成 ✓ / ✗ / ! 徽章。**本报告一个都不用。**

理由：读者要看的是判断结果和数字，不是一排图标。一屏十几个 ✓✗! 会把注意力从内容上带走；红线命中的信息用颜色表达比用图标表达更直接。

**替代做法**：需要强调时用行内 `<span style="color:…">`。

| 位置 | 怎么表达 |
|---|---|
| 红线表：命中的那条 | 行名与结论都用 `<span style="color:#dc2626;font-weight:700">` 标红 |
| 红线表：未命中 | 不标色，正文色 |
| 逐题明细：得分 | `3 分` 绿、`1–2 分` 琥珀、`0 分` 红，只给数字上色 |
| 指标表：还不知道 | 数值列写 `<span style="color:#d97706">还不知道</span>` |
| 当前等级那一行 | 整行加 `background:#eff6ff` 底色 |

**校验办法**：渲染后 grep 生成的 HTML，`am-badge` 出现次数必须是 0。

**不写状态词的地方**：`flow`、`timeline`、`kv` 三个组件里不要写状态词——它们不做徽章替换，写了就是把 `ok`、`no` 这些词原样显示给读者。

---

## 5. 完整 draft 骨架

**不要手抄这一节。** 生产路径是 `tools/render_report.py`：它从 `report.json` 生成 draft、
调 am 渲染、导出 PNG。这一节给出的是**它实际产出的样子**，用来对照检查渲染器有没有跑对。

虚构数据：康桥口腔门诊（总分 31、命中 R2/R3/R4、封顶 L1、四维 39/28/39/17）。

生成命令：

```bash
python tools/render_report.py docs/example-run.json -o /tmp/report.html --png --dump-draft
```

实测产出（`case1_kangqiao_L1.draft.md`，渲染 8 面板、0 徽章）：

````markdown
---
template: sheet
theme: shadcn
title: 康桥口腔门诊 · 早矫管理体检报告
subtitle: 2026-10-08
cols: 3
---

## 报告信息

```kv cols=2
机构：康桥口腔门诊
规模：3 名正畸医生 / 年新接约 180 例
访谈日期：2026-10-08
受访者角色：老板兼医疗主管，姓周
依据：24 题访谈自述，加上数据自查工具跑出的一份 243 例在册病例汇总
```

## 结论

<span style="font-size:64px;font-weight:800;letter-spacing:-1px;line-height:1;color:#09090b">L1</span>&nbsp;&nbsp;<span style="font-size:26px;font-weight:800;letter-spacing:-1px;line-height:1;color:#71717a">无标准</span>&nbsp;&nbsp;<span style="font-size:20px;color:#71717a">31 分</span>

```callout err 这 3 项问题把等级拉低了
按总分数本来能到 L2 刚起步 档。但 无周期标准、结束无人核、提成一次性发 属于一票否决的问题，所以等级只算 L1。
```

## 分数与等级 {span=2}

| 等级 | 这一档的样子 | 分数段 |
|---|---|---|
| <span style="background:#eff6ff;display:block;font-weight:800">L1 无标准</span> | <span style="background:#eff6ff;display:block">没有标准、没有计划时长、没有账，全凭医生个人</span> | <span style="background:#eff6ff;display:block">0–30</span> |
| **L2 刚起步** | 有零散做法，但不留痕、不可复算 | 31–55 |
| **L3 有体系** | 有标准能执行、数据可查，结案复核还有缺口 | 56–80 |
| **L4 能自转** | 标准、审核、留痕、复核、激励、财务全部到位 | 81–100 |

### 四个维度各得多少

<span style="display:inline-block;border-left:3px solid #2563eb;padding:2px 0 2px 10px;margin:5px 0"><span style="font-weight:700">维度1｜标准与分级</span><span style="font-size:19px;font-weight:800;color:#2563eb;padding:0 6px 0 12px">7</span><span style="font-size:12px;color:#71717a">/18　</span>无成文过程标准，难度与能力分级不存在，产能上限没量化</span>

<span style="display:inline-block;border-left:3px solid #2563eb;padding:2px 0 2px 10px;margin:5px 0"><span style="font-weight:700">维度2｜方案审核与结案</span><span style="font-size:19px;font-weight:800;color:#2563eb;padding:0 6px 0 12px">5</span><span style="font-size:12px;color:#71717a">/18　</span>方案只口头过一眼，结束无复核，终点定在拆托槽</span>

<span style="display:inline-block;border-left:3px solid #2563eb;padding:2px 0 2px 10px;margin:5px 0"><span style="font-weight:700">维度3｜记录与过程数据</span><span style="font-size:19px;font-weight:800;color:#2563eb;padding:0 6px 0 12px">7</span><span style="font-size:12px;color:#71717a">/18　</span>重启率与延期从未统计，椅位时长未进系统，计划外处理混在常规记录里</span>

<span style="display:inline-block;border-left:3px solid #2563eb;padding:2px 0 2px 10px;margin:5px 0"><span style="font-weight:700">维度4｜财务与激励</span><span style="font-size:19px;font-weight:800;color:#2563eb;padding:0 6px 0 12px">3</span><span style="font-size:12px;color:#71717a">/18　</span>提成一次发完，绩效不挂结束质量，预收款全额计收入，算不出单例毛利</span>


## 四条红线 {span=2}

| 红线 | 结论 | 依据 |
|---|---|---|
| 底数不清 | 未命中 | A1 判 2：在册数能导出，超期数要临时统计 |
| <span style="color:#dc2626;font-weight:700">无周期标准</span> | <span style="color:#dc2626;font-weight:700">命中</span> | A2 判 1：只有口头的 18 个月，答完 A2 给不出可核延期数字；B5 也只给终点定义 |
| <span style="color:#dc2626;font-weight:700">结束无人核</span> | <span style="color:#dc2626;font-weight:700">命中</span> | B4 判 0：结束由经治医生口头判定，无书面复核 |
| <span style="color:#dc2626;font-weight:700">提成一次性发</span> | <span style="color:#dc2626;font-weight:700">命中</span> | D2 判 0：收款次月一次性发全额提成 |

## 逐题明细 {span=2}

| 题号 | 分数 | 受访者关键原话 | 判分依据 |
|---|---|---|---|
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A1</span> | <span style="font-size:13px;color:#d97706">2 分</span> | 在册 243 例。超期数没统计过，印象里不少 | 在册数能导出，超期数要临时统计 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A2</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 计划一般按 18 个月跟家长说，平均延期没算过 | 只有口头印象，无成文标准、无延期统计 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A3</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 没写成文字，基本都是我跟另外两个医生平时聊出来的共识 | 有内部共识，无成文文件 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A4</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 没有正式分级，就是看谁手上不忙、谁擅长这类 | 医生心里有数，无成文分级 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A5</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 谁能力强我知道，靠年头和平时看的病例 | 分级在管理者印象里，无客观数据 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A6</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 一个月进来 20 个我们也能接，就是大家都累点 | 知道会吃不消，未量化产能上限 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B1</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 新病例基本我都会看一眼，微信上说一下 | 有非正式招呼，没有审核记录 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B2</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 主要看诊断对不对；具体做多久医生自己跟家长谈 | 看诊断，目标与计划时长不固定 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B3</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 最近半年开始写了，老病例没写 | 有意识、覆盖新病例，无固定间隔要求 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B4</span> | <span style="font-size:13px;color:#dc2626">0 分</span> | 医生觉得可以了就拆，拆完跟我说一声，发个前后对比照 | 无复核，经治医生口头判定→ R3 命中 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B5</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 拆完托槽就算结束，保持器阶段归前台跟 | 默认拆托槽为结束，保持器不在管理范围 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B6</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 医生觉得不对会跟我说，没有固定流程 | 有口头说明，无记录、无触发条件 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C1</span> | <span style="font-size:13px;color:#d97706">2 分</span> | 复诊都挂号的，但偶尔钢丝扎嘴来弄一下就不挂了 | 有要求、执行有漏洞、无人核查 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C2</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 会写主诉和处理，掉托槽这类没单独标 | 有记录但随意，计划外混在常规里 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C3</span> | <span style="font-size:13px;color:#d97706">2 分</span> | 报表能看到每个病例来过几次，椅位时长没进系统 | 能看到部分指标，椅位时长缺 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C4</span> | <span style="font-size:13px;color:#dc2626">0 分</span> | 重启率、延期都没统计过，医疗主管说历史上重启过 8 例 | 两个数都没统计 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C5</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 有的医生会跟家长讲进度，有的不太讲 | 有对照进度行为但不固定 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">C6</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 耗材有采购记录，加工件记在门诊账上，没到病例 | 出入库只到门店层级 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D1</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 收款就全额开票算收入了 | 无预收款概念，一直这么算 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D2</span> | <span style="font-size:13px;color:#dc2626">0 分</span> | 提成收款次月一次性发完 | 一次性发全额→ R4 命中 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D3</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 每个月看新接多少例、到账多少；预收款没单独看 | 知道欠服务，未量化、无月度对比 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D4</span> | <span style="font-size:13px;color:#dc2626">0 分</span> | 绩效跟收入和接诊量挂钩，结束快慢不挂钩 | 绩效只跟新接病例数和收入挂钩 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D5</span> | <span style="font-size:13px;color:#d97706">1 分</span> | 大概算过，收费减材料，人工和椅位没算进去 | 粗略估算，不含人工与椅位 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D6</span> | <span style="font-size:13px;color:#dc2626">0 分</span> | 没算过就诊次单价 | 没有这个概念 |

## 该做什么 {span=2}

```callout warn 这周就开始
1. 导出 243 例在册病例，补上「计划结束日期」一列。算出超期病例数和平均延期月数，顺带补齐 K1 缺的另一半
2. 结案状态从「拆托槽」改成「首次保持器复诊通过」。统计口径与绩效结算口径同步改
3. 建议 2026-12-08 重跑本问卷，重点对比题号 <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A1</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A2</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A4</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">A5</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B1</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B4</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">B5</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D2</span> <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">D4</span>，看三条红线是否解除。
```

```flow LR
1 结束病例要过一遍复核 -> 2 先把底数、标准、分级补起来
2 先把底数、标准、分级补起来 -> 3 提成改成按节点发: P1
3 提成改成按节点发 -> 4 把每个病例赚不赚钱算清楚: P2
4 把每个病例赚不赚钱算清楚 -> 5 每次复诊对着阶段目标看进度
5 每次复诊对着阶段目标看进度 -> 6 每次来都留下记录
group P0: 1 结束病例要过一遍复核, 2 先把底数、标准、分级补起来
group P1: 3 提成改成按节点发
group P2: 4 把每个病例赚不赚钱算清楚, 5 每次复诊对着阶段目标看进度, 6 每次来都留下记录
```

---

### 1. 结束病例要过一遍复核<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#fef2f2;color:#dc2626;font-size:12px;font-weight:700;vertical-align:2px">先做</span>

结束由经治医生口头判定；终点定在拆托槽；重启率与延期从未统计；绩效不挂结束质量。

1. 结案状态从「拆托槽」改成「首次保持器复诊通过」。系统状态、统计口径、绩效结算三处同步改
2. 结束复核表落地，先只保留四项：脱矿率、新发龋率、按期完成率、患者主观感受。
3. 重启率与延期月数按月出数，进入管理复盘。
4. 复核结果进入医生绩效。

做到这一步算完成。改口径后第一个月：在册病例的超期数与平均延期月数能随口报出；至少 3 个结案病例走过书面复核。

---

### 2. 先把底数、标准、分级补起来<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#fef2f2;color:#dc2626;font-size:12px;font-weight:700;vertical-align:2px">先做</span>

没有成文的过程管理标准；难度与能力分级不存在；产能上限没量化；方案只口头过一眼。

1. 导出 243 例在册病例清单，补上「计划结束日期」一列，算出超期病例数与平均延期月数。
2. 出第一版病例难度分级与医生能力分级，对应到「谁能接什么」。
3. 第一版方案审核表固定三项：诊断依据、治疗目标、计划结束时长。
4. 定一条承接容量线：每个医生在册病例上限。

做到这一步算完成。底数表能对上系统；至少 3 个新病例走完审核并留下记录；分级能解释上个月病例分给了谁、为什么。

---

### 3. 提成改成按节点发<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#fffbeb;color:#d97706;font-size:12px;font-weight:700;vertical-align:2px">接着做</span>

提成在收款次月一次性发完；绩效不挂按期结束与结束质量。

1. 提成改分期：收款发一部分、中期发一部分、病例结束且质控合格发尾款。
2. 尾款占比定在能形成约束的水平（例如不低于三成），规则写进薪酬制度并公示。
3. 绩效里加入按期完成率与结束质量，权重可观。

做到这一步算完成。薪酬规则公示；未发部分在医生离职时能明确归属接手医生。

---

### 4. 把每个病例赚不赚钱算清楚<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:700;vertical-align:2px">以后做</span>

预收款全额计收入；没有未交付服务与产能的月度对照；算不出单例毛利与就诊次单价。

1. 定收入确认规则，报表单列预收款负债余额。
2. 每月对一次「未交付预收款余额 vs 在册病例交付能力」。
3. 做 5 例单例损益卡，算出单例就诊次单价。

做到这一步算完成。能回答「这一单赚不赚钱、和别的项目比怎么样」。

---

### 5. 每次复诊对着阶段目标看进度<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:700;vertical-align:2px">以后做</span>

阶段目标只在最近半年的新病例上写；复诊不固定对照；偏离没有触发条件。

1. 方案模板加入按时间分解的阶段目标表。
2. 每次复诊对照阶段目标，并与家长确认进度。
3. 定偏离的触发条件与记录要求。

做到这一步算完成。新病例方案都含阶段目标表；落后一个阶段以上的病例单独成清单。

---

### 6. 每次来都留下记录<span style="display:inline-block;padding:2px 10px;margin-left:10px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:700;vertical-align:2px">以后做</span>

简单处理常不挂号；计划外处理混在常规记录里；椅位时长未进系统；成本归不到病例。

1. 挂号台加「早矫复诊（含简单处理）」快捷号别，把挂号压到 10 秒内。
2. 复诊记录给计划外处理加单独标识。
3. 椅位占用时长进系统；耗材出入库从加工件抓起。

做到这一步算完成。报销表与病历记录能对上；每例计划外复诊次数可统计。


## 90 天怎么排 {span=2}

| 时间 | 要做什么 | 交付什么 | 怎样算做完 |
|---|---|---|---|
| 第 1–2 周 | 摸底数与终点定义 | 在册病例底数表 + 终点定义书面口径 + 容量线 | 在册数与超期数能随口报出且对得上系统 |
| 第 3–6 周 | 立标准与分级 | 分级表 + 审核表 + 阶段目标模板 | 至少 3 个新病例走完新流程并留下记录 |
| 第 7–10 周 | 建记录与复核 | 四张报表 + 结束复核表 | 报表数据与病历记录能对上 |
| 第 11–13 周 | 调钱和账 | 薪酬调整规则 + 三张财务表 + 5 张损益卡 | 能回答单例赚不赚钱 |

## 八个关键数字 {span=2}

| 指标 | 数值 | 从哪来 |
|---|---|---|
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标1</span> 在册病例数 | 243 | 前台导得出，和病历系统对得上。但只有这一个数，超期数还没有 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标2</span> 延期病例占比 | <span style="font-size:13px;color:#d97706">还不知道</span> | 需先在系统里给每例填「计划结束日期」，再按统计截止日比对 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标3</span> 计划疗程与实际疗程差多少 | 计划 18 个月，已结案的实际均值 20.1 个月 | 口径为拆托槽日期，与 K4 口径必须一致 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标4</span> 平均延期月数 | 在册未结案的 4.5 个月，已结案的 2.1 个月 | 两组数的统计口径不同，必须分别标注 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标5</span> 计划外复诊率 | <span style="font-size:13px;color:#d97706">还不知道</span> | 记录未单列计划外处理，需先加标识字段 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标6</span> 每次占椅位多久、每例来几次 | 每例平均来 20.8 次，椅位时长还不知道 | 椅位时长在挂号本有原始记录但未录入 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标7</span> 重启或二次治疗的比例 | <span style="font-size:13px;color:#d97706">还不知道</span> | 系统无重启标识；医疗主管口径为历史 8 例，不可用 |
| <span style="display:inline-block;padding:1px 8px;margin:0 2px;border-radius:6px;background:#f4f4f5;color:#71717a;font-size:12px;font-weight:600;white-space:nowrap">指标8</span> 单例就诊次单价 | 收入侧 1385 元一次，成本侧还不知道 | 成本侧缺椅位时长与病例级材料成本 |
````

---

## 6. STE 检查的处置

am 会自动做"简化技术中文"检查（STE）。默认 `--style 80`：**只警告、不拦，页面照常生成，退出码 0**。实测过三种模式的差别：

| 模式 | 行为 | 结论 |
|---|---|---|
| `--style 80`（默认） | 打印警告，页面照生成，退出码 0 | **本 skill 固定用这个** |
| `--style strict` | 有警告就不出页，退出码 1 | **禁止使用** |
| `--style off` | 打印 `STE check is off` | 只在排障时用 |

**为什么禁止 `strict`**：STE 词表把一批常见中文书面词判成套话（`闭环`、`抓手`、`赋能`、`至关重要` 等）。报告文案里只要出现一个，`strict` 就会让**整个报告不出 HTML**。实测：一份含 `闭环` 的 draft 用 `--style strict` 报 `✗ STE check failed (style: strict): 1 warning; no page was written:`，退出码 1。

另一种更彻底的做法是**把套话从源头上换掉**。本 skill 已经这么做过一次：维度 B 原本叫「方案审核与闭环」，改名「方案审核与结案」之后这条警告就不存在了（`结案` 是具体动作，读的人也懂）。剩下的词表命中来自受访者原话时，保留原话。

### 三条处置规则

1. **我们自己写的叙述里的词表命中 → 改掉。** 包括笼统数量词、轻动词、套话。能换成一个具体说法就换（`闭环` → `结案`），不要只是删掉。
2. **句子超长 → 必须拆句。** 上限见下表，超长在 1/3 栏宽里会变得难读。
3. **受访者原话里的词 → 保留。** 改写原话会让证据失真；这类警告接受，不追求 0 警告。

### 6.1 词表实测结果（自己写的都要改）

| 实测输出 | 处置 |
|---|---|
| `cliché "闭环"` | **从源头改掉**：维度 B 已从「方案审核与闭环」改名「方案审核与结案」 |
| `cliché "至关重要"` | 改写：说出具体事实 |
| `cliché "赋能"` / `"抓手"` / `"颗粒度"` | 改写：换成具体动作或数字 |
| `not recommended: "尽快"` | 改写：给确切期限（如"2 周内"） |
| `not recommended: "若干"` / `"多次"` | 改写：写出数字 |
| `not recommended: "大概"` | 自己写的改成"约"或确切值；**受访者原话里的保留** |
| `light verb "进行复核"` | 改写：`复核` |
| `light verb "加以说明"` | 改写：`说明` |
| `not recommended: "以上"`（数字后） | 改写：`大于` / `不小于` |
| `not recommended: "以下"`（数字后） | 改写：`小于` / `不大于` |
| `not recommended: "以内"` | 改写：`不超过` |

**实测不触发的词（可放心用）**：`底数不清`、`留痕`、`复核`、`复测`、`重启率`、`超期病例`、`结案`、`预收款`、`提成`、`椅位时长`、`下列`、`落地`。

`以上` / `以下` 的确切边界（实测）：`3 以上`、`5 以下`、`80% 以上` 触发；`18 个月以上`（数字与"以上"之间有单位）**不触发**；`以内` 在任何形式下都触发（`3 天以内` 触发）；`2 周内`、`不超过 3 例`、`大于 18 个月` 不触发。

### 6.2 句子长度上限（实测）

| 位置 | 上限 | 实测报告原文 |
|---|---|---|
| 段落行、表格单元格、`callout` 正文、无序列表项 | 45 字 | `sentence has 52 characters (max 45)` |
| 有序列表项（步骤） | 35 字 | `step has 54 characters (max 35)` |
| 面板标题、`title`、`subtitle`、frontmatter 值 | 不检查 | 长标题 0 警告 |

计数规则（实测）：**按行计数，不按逗号切分；中文标点不计入**。一段 58 字、含逗号的段落被报成 `sentence has 56 characters`，说明 `，。、；：！？` 都被排除在计数之外，而整行算作一句。所以**写长句用逗号连缀不能绕过长度检查**——要拆成多行。

### 6.3 唯一固定保留的一类警告：受访者原话

**受访者原话里的词一律保留。** 原话是证据，逐字保留，包括里面的词表命中词。改写原话等于改证据，这比一条 STE 警告严重得多。

术语不在此列。术语造成的警告要从源头解决：**换个说法，而不是删掉或保留。** 本 skill 已经把维度 B 从「方案审核与闭环」改成「方案审核与结案」，这就是标准做法。

本骨架文件实测产生 **1 条**警告，来自面板 H 的 D5 行（受访者原话"大概算过，收费减材料，人工和椅位没算进去"）：

```
L132 [word] not recommended: "大概" → use "约" in descriptions, a value in steps
```

**处置：接受，不改写。** 交付 HTML 时对这类警告的原则是"存在即接受，不追求 0 警告"；只要警告的落点能一一对上术语或原话，就算通过。

### 6.4 实测到的检查豁免（不要滥用）

| 豁免 | 实测 |
|---|---|
| 表格行里状态格写 `no` 的，**整行跳过**检查 | 同一句话放 `no` 行 0 警告、放 `warn` 行告警 |
| 反引号内联代码 | 跳过 |
| `~~删除线~~` | 跳过（am 文档说明的"反例写法"） |
| 面板标题（`## X 标题`） | 不检查 |

豁免的正当用途是**故意展示反例**。**不得**为了让警告消失而把行标成 `no`，那会把该行的真实问题一起遮掉。

---

## 7. 渲染与出图的命令

三个路径变量（本机实测值）：

```
node: C:\Program Files\nodejs\node.exe          （v24.19.0）
am:   %TEMP%\amwh\skills\answer-me-with-html\scripts\am.mjs
      本机 %TEMP% = C:\Users\admin\AppData\Local\Temp\1
图:   <skill 仓库>\tools\html_to_image.mjs
```

1. **出 HTML**（必用 `--no-open`，否则会弹出浏览器）：

```
node "%TEMP%\amwh\skills\answer-me-with-html\scripts\am.mjs" render "<draft.md>" -o "<out.html>" --theme shadcn --template sheet --style 80 --no-open
```

2. **出 PNG**（用仓库自带工具，不要自己调浏览器，理由见 §8 坑 4）：

```
node "<skill 仓库>\tools\html_to_image.mjs" "<out.html>" -o "<out.png>"
```

**不要传 `--width`。** 默认是 **990 CSS 视口宽 / 2 倍**，得到 2016 像素宽的图。
这个默认值是按"图缩到阅读宽度时字号 1:1"反推的，理由见下面两节。

3. **只检查不改页**（写 draft 时反复用，比渲染快）：

```
node "%TEMP%\amwh\skills\answer-me-with-html\scripts\am.mjs" lint "<draft.md>"
```

### 视口宽度：决定排版，也决定字清不清楚

am 的页面有两处响应式断点，**1100px 以下 grid 从 3 列塌成 2 列**，760px 以下塌成 1 列：

```css
.am-grid { grid-template-columns: repeat(var(--cols, 3), minmax(0, 1fr)); }
@media (max-width: 1100px) { .am-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px)  { .am-grid { grid-template-columns: minmax(0, 1fr); } }
```

断点只是第一层。真正决定成品能不能读的是**图片宽度与阅读宽度的比值**——图越宽，被缩放得越狠，字号越小：

| CSS 视口 | 2 倍图实际像素宽 | 缩到 990px 阅读时 | 13px 正文的等效高度 |
|---|---|---|---|
| 990 | 2016 | 49% | **13.0px**（原生） |
| 1422 | 2880 | 34% | 9.0px |
| 1710 | 3456 | 29% | **7.5px**（糊） |

所以默认取 **990**：1980～2016px 的图在常见阅读宽度下接近 1:1，13px 正文就是 13px。
把它加宽到 1710 会让排版从"侧栏 + 主栏"变成三栏，但图宽翻倍、缩下来字号只剩 58%，
**得不偿失**——这是实测踩过的坑。

990 下各面板的实际排布（实测，`--cols 3` + span 的结果）：

```
报告信息(1)  结论(2)          ← 侧栏 + 主栏
分数与等级(3)
四条红线 / 逐题明细 / 该做什么 / 90 天 / 八个关键数字   ← 各自占满
```

即高度是 4412px（比 1710 视口下的 2839px 高，但每一行都读得清）。

### `--window-size` 与 CSS 视口的 18px 差值

Chrome 的 `--window-size` 不是 CSS 视口宽：**CSS 视口 = 窗口宽 − 18px**（滚动条）。实测：

| `--window-size` | CSS 视口 |
|---|---|
| 990 | 972 |
| **1008** | **990** ← 脚本内部用这个 |
| 1018 | 1000 |

`html_to_image.mjs` 的 `--css-width` 帮你把这一步算好（内部传 `cssWidth + 18`）。
要直接用窗口宽就传 `--width`，它优先于 `--css-width`。

### HTML 的宽度约束：只锁窄窗，宽屏交给 am

目标是"打开、转发、导出成图三种场景看到同一个版式"。**这个目标只能部分达成**，
原因在 am 的运行时里，实测踩过三次坑：

1. **写死 `.am-sheet { width: 990px }`**：窗口 1920 时容器 990、窗口 1920，两者对不上，
   am 的列平衡脚本算错——报告信息被压成 1 列、结论被挤到它下面，版面散掉。
2. **只写 `max-width: 990px`**：容器仍是 990 而窗口 1920，同样散掉。
3. **用 JS 设 `zoom` 等比缩放**：am 用 `getBoundingClientRect()` 量宽度，
   zoom 下 rect 是缩放后的值、布局值没变，脚本量到 1902px 却按 990 布局，更乱。

问题不在 CSS，在于 **am 的运行时按容器实际宽度重排面板，而容器宽度与窗口宽度不一致时它会算错**。

所以现在的做法是**分区间**：

```css
@media (max-width: 1030px) {
  .am-sheet { width: 990px; max-width: 990px; margin: 0 auto; }
}
```

- **窗口 ≤1030px**（也就是出图与阅读的宽度）→ sheet 钉在 990px 居中。
  这是导出 PNG 用的区间，也是绝大多数阅读场景。
- **窗口更宽** → 不加约束，让 am 按它自己的算法正常排三栏。
  版式会变成另一种（报告信息在左、结论在它下面、分数与等级在右上），
  **但内容完整、阅读顺序不变、没有版面散掉**。

实测（同一份 HTML 在不同窗口下打开）：

| 窗口 → CSS 视口 | `.am-sheet` 宽 | 面板数 | 结论 |
|---|---|---|---|
| 900 → 882 | 882px | 8 | 窄于 990，按窗口宽排，不撑横向滚动条 |
| 1008 → 990 | **990px** | 8 | **出图与阅读的目标区间**，A+B 并排 |
| 1440 → 1422 | 1680px 上限 | 7 | am 三栏重排，内容完整 |
| 1920 → 1902 | 1680px 上限 | 7 | 同上 |

**要"完全一致"就发 PNG。** HTML 在宽屏下必然重排，这是 am 运行时的行为，
不是可以靠 CSS 修掉的。别为了追求一致性去跟它对抗——三次尝试的结论就是别试了。

**990 这个数字必须在两处一致**：

1. `tools/render_report.py` 的 `_LOCK_WIDTH`（窄窗锁定宽度）
2. `tools/html_to_image.mjs` 的 `--css-width` 默认值（出图视口）

### 报告信息面板不用 kv 组件

面板 A 曾经用 `kv cols=2`，排出来是"左侧等宽小标签 + 右侧值"的表格样子，
只有两三条信息时看着多余。现在直接写成三行文字（正文样式）：

```markdown
## 报告信息

机构：康桥口腔门诊<br>规模：3 名正畸医生 / 年新接约 180 例<br>访谈日期：2026-10-08
```

两个细节：

- **用 `<br>` 而不是 Markdown 的硬换行**（行尾两个空格）。硬换行会让每行成为独立段落，
  段间距看着像四条信息。
- **报告信息面板占 1 列（不写 `{span=2}`）**。990 视口下 1 列正好把结论面板放在右边，
  形成"侧栏 + 主栏"；占满整宽会把结论挤到下一行，那份报告的视觉重心就没了。
  "规模"那一行在窄栏里会折行，三行各自独立，折了也不串行。

```markdown
## 报告信息

机构：康桥口腔门诊<br>规模：3 名正畸医生 / 年新接约 180 例<br>访谈日期：2026-10-08
```

两个细节：

- **用 `<br>` 而不是 Markdown 的硬换行**（行尾两个空格）。硬换行会让每行成为独立段落，
  段间距看着像四条信息。
- **面板占 1 列（不写 `{span=2}`）**。990 视口下 1 列正好把结论放在右边，形成"侧栏 + 主栏"；
  占满整宽会把结论挤到下一行，那份报告的视觉重心就没了。"规模"那行在窄栏里会折行，
  三行各自独立，折了也不串行。

### HTML 与 PNG 的清理（两步，两边都要做）

`am` 产出的页面要过三道清理，**HTML 与 PNG 都基于清理后的版本**，否则"点开的"和"导出的"不一致：

1. **删页脚署名**。am 会在底部生成 `<footer class="am-colophon">Generated by Answer me with HTML 0.4.15 · <时间></footer>`。印在成品图上像水印，对读报告的人也没有信息量。am 是 MIT，允许修改；本仓库在 README 与文件头保留了完整署名。
2. **窄窗锁宽**（见上一节）。
3. **统一字体**。am 的 base CSS 把这几类元素设成等宽字体：

   ```css
   .am-md th          { font: 11px/1.3 var(--font-mono); }   /* 表头 */
   .am-kv dt          { font: 11px/1.4 var(--font-mono); }   /* 键值标签 */
   .am-panel-meta,
   .am-head-meta b    { font: var(--font-mono); }            /* 面板角标 */
   ```

   中文报告里这些中文标签会显示成外挂字形，整页看起来有两种字体。覆盖办法是注入一段样式（只改 `font-family`，字号/行高/颜色不动），**`code` / `pre` / `kbd` 继续用等宽**：

   ```html
   <style id="eoc-uniform-font">
   .am-md th, .am-kv dt, .am-panel-meta, .am-head-meta b
   { font-family: var(--font-sans) !important; }
   </style>
   ```

实测：`tools/render_report.py` 出页时自动做这两步（打印"已清理 2 处"），`tools/html_to_image.mjs` 出图时再做一遍兜底（对已经清理过的文件是幂等的）。

`am lint` 即使有警告也返回退出码 0，**判断要看输出文本**：本报告的预期输出是 1 条警告（D5 原话里的 `大概`，见 §6.3）。出现这 1 条以外的任何警告，按 §6 处置；出现 `STE ✓ 0 warnings` 也正常（例如 D5 原话被改写时——但那违反原话逐字保留的规则，不要为了让警告归零而改写原话）。

**产物路径**：HTML、PNG、draft 一律写临时目录（建议 `%TEMP%\eoc_reports\`），**不进仓库**。仓库 `.gitignore` 只忽略 csv/xlsx，html/png 不忽略——报告含机构名与经营数据，不要提交。

**输出怎么读**（`am render` 前后由 `render_report.py` 打印）：

```
$ "C:\Program Files\nodejs\node.EXE" ...\am.mjs render ...\report.draft.md -o ...\report.html --theme shadcn --template sheet --style 80 --no-open
✓ <out.html 绝对路径>
  sheet · shadcn · 9 panels · kv×1 callout×3 flow×1 timeline×1
  STE 1 warning (fix the draft and run again):
  L132 [word] not recommended: "大概" → use "约" in descriptions, a value in steps
html : <out.html>  (112752 B)
$ "C:\Program Files\nodejs\node.EXE" tools\html_to_image.mjs <out.html> -o <out.png> --css-width 990 --scale 2
<out.png>  2880x7560  2110075 B
  浏览器 C:/Program Files/Google/Chrome/Application/chrome.exe
  内容框 main: 3749px（top 0px）· 文档高 3789px · 窗口 1440x3789 · 倍率 2
png  : <out.png>  (2110075 B)
```

- 第一行 `✓` + 路径 = 成功，把 `file://` 加在路径前就是给受访者的可点链接（不要做百分号编码）。
- 第二行是模板 · 主题 · 面板数 · 组件统计。**面板数不是 9 或组件统计缺了 `flow`/`timeline`，说明 draft 结构写错了。**
- `✗ L<行号> [组件] …` + `Correct example:` = 该行语法错，按示例改后重渲染。**行号是 draft 文件的行号**（实测准确）。
- `STE n warnings` = 见 §6。

**PNG 命令输出**（三行）：

```
<out.png 绝对路径>  2880x4330  1302252 B
  浏览器 C:/Program Files/Google/Chrome/Application/chrome.exe
  内容框 main: 2125px（top 0px）· 文档高 2165px · 窗口 1440x2165 · 倍率 2
```

`--css-width 990 --scale 2` 得到 2016 像素宽的图；缩到 990px 阅读时字号是原生的，微信转发清楚。

---

## 8. 坑清单（全部实测）

1. **frontmatter 的自定义键必须是 ASCII。** 写 `机构: 康桥口腔门诊` 直接报错、不出页：
   `✗ L5 Cannot parse the draft: Cannot parse frontmatter line "机构: 康桥口腔门诊"; expected key: value`。
   键改成 `org:` 即可；**值可以是中文**（`title: 早矫管理体检报告` 正常）。
2. **`flow` 的方括号只有包住整个节点名时才是形状。** `A[ACT-2 P0]` 会原样显示成节点文字 `A[ACT-2 P0]`；`ACT2(ACT-2 P0)` 同理显示 `ACT2(ACT-2 P0)`。正确写法二选一：整段包住 → `(ACT-2 P0)`（圆角，显示 `ACT-2 P0`）；或直接用裸节点名 → `ACT-2`。方括号 `[文字]` 是矩形、`{文字}` 是菱形、`[(文字)]` 是柱体，都要求**整段**包住。
3. **`html_to_image.mjs` 没有 `--help`。** `--help` 会被当成输入文件：`✗ 找不到文件: D:\周五直播\--help`。用法看该文件头部注释。
4. **不要用固定窗口直接截图。** 页面按视口高度排版，直截会在底部留大片空白：1440×4000 窗口直截，内容止于第 2136 行，**底部空白 1863px**；用 `tools/html_to_image.mjs`（先测量再按实际高度截）**底部空白 54px**。
5. **不加 `--no-open` 会弹浏览器窗口。** 每次渲染都带 `--no-open`。
6. **省略 `-o` 会写到用户目录** `~/.answer-me-with-html/pages/`，不进你的临时目录，容易找不到。
7. **面板数与组件统计是自检信号。** 两种情况，都已实测：

   | 情形 | 统计行 |
   |---|---|
   | 四条红线全未命中 | `8 panels · kv×1 callout×2 flow×1` |
   | 有红线命中 | `8 panels · kv×1 callout×2 flow×1` |

   面板数恒为 8；`callout` 恒为 2（结论区一条 + 该做什么开头一条），有红线命中时只是第一条从 `info` 变成 `err`，条数不变。`kv`/`flow` 各 1，恒不变。对不上就是 draft 少写或多写了面板。
8. **不用 `timeline`**（§3 面板 G）：改成四列表格。timeline 的居中标题会让底下的灰字读不出属于哪一段。
9. **`--style strict` 会让整页不生成**（§6）。永远用 `--style 80`。
10. **8 个面板是上限。** 再加内容就**另开一页**，不要挤。
11. **`kv` 的分隔符支持半角 `:` 和全角 `：`**（实测两种都渲染成键值对）。但 `flow` 的边标签只用半角 `:`。
12. **行内 `<span>` 保留 `style` 属性**（实测）：大字号、颜色、tag 形状都靠它。不要用 `<div>`、`<style>`、`<script>`，那些会被当作文本显示或拦掉。
13. **带 BOM 的 draft 能渲染**（实测正常出页），但仍按 UTF-8 无 BOM 落盘，避免别的工具读串。
14. **写 draft 用 Node 或编辑工具，不要用 PowerShell 5.1 的 `Set-Content -Encoding utf8NoBOM`**：该枚举不存在（只有 `UTF8`，会写 BOM）。例如 `node -e "require('fs').writeFileSync(p, s, 'utf8')"`。
15. **用 PowerShell 读 draft/产物时加 `-Encoding UTF8`**，否则中文显示乱码（文件本身没问题）。
16. **不确定**：am 是否支持从 stdin 读 draft（`am render -`，`am help` 文本提到）**本规范未实测**，原因：Windows shell 的 heredoc 与引号转义不可控。**统一落盘成文件再渲染**，不要用 stdin。

---

## 9. 实测记录（命令与原始输出）

CLI：`answer-me-with-html 0.4.15`，Node v24.19.0，Windows。
所有 draft 与产物在 `%TEMP%\amwh_probe\` 下，**不在仓库内**。

> **这一节的用途**：证明本文件写的每一种组件语法都真的能渲染。它是**语法证据**，不是版式基准——生产路径是 `tools/render_report.py`，页面结构以它生成的结果为准（两份骨架的面板划分一致：kv → 结论 → 红线 → 四维 → 逐题 → 动作 → 路线图 → 指标 → 下一步）。
> 本节下面的记录（CMD1–CMD8）产生于本文件初稿版本，其 `callout` 计数（2 条）反映的是当时"红线不单独开 callout"的写法；后续已改为"红线命中加一个 B2 `callout err`"（见 §3 与 §5），因此**组件统计行以 §7 的 `callout×3` 为准**。组件语法本身的结论不受影响。

**CMD1 · 渲染骨架（sheet）** —— §5 那段骨架原文，结果：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\final\early-ortho-report.html
  sheet · shadcn · 9 panels · kv×1 callout×2 flow×1 timeline×1
  STE 1 warning (fix the draft and run again):
  L132 [word] not recommended: "大概" → use "约" in descriptions, a value in steps
```

**CMD2 · 同一份骨架换 `doc` 模板**（§2 备选方案）：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\final\early-ortho-report-doc.html
  doc · shadcn · 9 panels · kv×1 callout×2 flow×1 timeline×1
  STE 1 warning (fix the draft and run again):
  L132 [word] not recommended: "大概" → use "约" in descriptions, a value in steps
```

**CMD3 · 只检查**（`am lint`）：同上那 1 条警告，退出码 0。

**CMD4 · 出 PNG**：

```
C:\Users\admin\AppData\Local\Temp\1\amwh_probe\final\early-ortho-report.png  2880x4330  1302252 B
  浏览器 C:/Program Files/Google/Chrome/Application/chrome.exe
  内容框 main: 2125px（top 0px）· 文档高 2165px · 窗口 1440x2165 · 倍率 2
```

**CMD5 · `callout` 四型**（`info` / `ok` / `warn` / `err`）：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\v1_callouts.html
  sheet · shadcn · 4 panels · callout×4
  STE ✓ 0 warnings
```

**CMD6 · `kv` 全角冒号 + `mode: light`**：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\q1_kv_colon.html
  sheet · shadcn · 1 panel · kv×1
  STE ✓ 0 warnings
```

**CMD7 · `flow` 方向与形状**（默认 TB、`(圆角)`、`{菱形}`、`[(柱体)]`）：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\q2_flow_tb.html
  sheet · shadcn · 2 panels · flow×2
  STE ✓ 0 warnings
```

**CMD8 · `timeline` 7 项自动纵向**：

```
✓ C:\Users\admin\AppData\Local\Temp\1\amwh_probe\q3_timeline7.html
  sheet · shadcn · 1 panel · timeline×1
  STE ✓ 0 warnings
```

**CMD9 · frontmatter 中文键失败**（坑 1 原文）：

```
✗ L5 Cannot parse the draft: Cannot parse frontmatter line "机构: 康桥口腔门诊"; expected key: value
```

**CMD10 · `flow` 方括号原样显示**（坑 2）：`A[ACT-2 P0]` 的输出 SVG 节点文字实测为 `A[ACT-2 P0]`；`ACT2(ACT-2 P0)` 为 `ACT2(ACT-2 P0)`；整段包住的 `(ACT-2 P0)` 为 `ACT-2 P0`。

**CMD11 · `--style strict` 阻断出页**（§6 原文；另一份单行草稿实测报 `1 warning`，机制相同）：

```
✗ STE check failed (style: strict): 3 warnings; no page was written:
  L12 [cliche] cliché "闭环" → delete it or state a concrete fact
```

**CMD12 · 固定窗口直截 vs 自带出图工具**（坑 4）：`--window-size=1440,4000` 直截 → 1440×4000，内容止于第 2136 行，底部空白 1863px；自带工具（先测量再截）→ 底部空白 54px（用 Pillow 逐行扫描非背景像素测得）。当时用的宽度参数已过时，见 §7「视口宽度」。

**CMD13 · STE 词表与长度规则**（§6.1 / §6.2）：逐词单行草稿的 `am lint` 输出，共 12 条警告，覆盖 `闭环` ×2、`尽快`、`若干`、`大概`、`多次`、`进行复核`、`加以说明`、`至关重要`、`赋能`、`抓手`、`颗粒度`；长度规则用 58 字含逗号段落（报 `sentence has 56 characters (max 45)`）与 54 字有序列表项（报 `step has 54 characters (max 35)`）确认按行计数、标点不计入。

**CMD14 · STE 豁免**：同一句话在状态格 `no` 的行 0 警告、在 `warn`/`ok`/空格的行都告警；反引号内联代码与 `~~删除线~~` 均 0 警告；长 `title`/`subtitle` 0 警告。
