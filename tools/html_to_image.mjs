#!/usr/bin/env node
/**
 * html_to_image.mjs — export an .html page to a PNG for sharing.
 *
 * Why this exists: the pages produced by answer-me-with-html size themselves to
 * the viewport (a 1440x2400 window leaves ~1500px of blank paper at the bottom).
 * So we measure the real content box first with --dump-dom, then screenshot at
 * exactly that height.
 *
 * Usage:
 *   node html_to_image.mjs <page.html> [-o out.png] [--css-width 990] [--scale 2]
 *                           [--browser <path>] [--pad 0] [--min 900] [--max 40000]
 *
 * --css-width is the CSS viewport width and it is the knob that matters: it decides
 * both the layout (am collapses the 3-column grid below 1100px) and how legible the
 * text ends up. Default 990 comes from working backwards from the reading width: a
 * 1980px image (990 x 2) shown at about 990px is 1:1, so 13px body text stays 13px.
 * Widening the viewport widens the image, which then gets scaled down harder:
 * a 1710px viewport yields 3420px, shown at 990px that is 58%, i.e. 7.5px text.
 *
 * Prints one line: "<out.png>  <w>x<h>  <bytes> B"
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

//: Chrome 在非 hide-scrollbars 模式下给滚动条留的宽度（实测 18px）。
//: 要让 CSS 视口正好是 N，窗口宽得传 N + 18。
const SCROLLBAR_PX = 18;

const BROWSERS = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
];

function parseArgs(argv) {
  // 默认 CSS 视口 990px、2 倍图（1980px 宽）。
  //
  // 为什么是 990 而不是更宽：这个宽度下 am 的 grid 是 3 列，各面板按 span 排成
  // "侧栏 + 主栏"的版式（报告信息在左、结论在右）。更关键的是字号——1980px 的图
  // 在常见阅读宽度（约 990px）下是 1:1 显示，13px 正文就是 13px，清晰。
  // 视口越宽，导出的图越宽，被压得越狠：1710px 视口出 3420px 的图，缩到 990
  // 只有 58%，13px 正文变成 7.5px，糊得看不清。
  //
  // --width 是 Chrome 的窗口宽；--css-width 是想要的 CSS 视口宽（Chrome 有
  // 18px 滚动条宽度差，所以窗口宽 = CSS 视口宽 + 18）。
  const a = { out: null, width: null, cssWidth: 990, scale: 2, browser: null, pad: 0, min: 900, max: 40000 };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === "-o" || t === "--out") a.out = argv[++i];
    else if (t === "--width") a.width = Number(argv[++i]);
    else if (t === "--css-width") a.cssWidth = Number(argv[++i]);
    else if (t === "--scale") a.scale = Number(argv[++i]);
    else if (t === "--browser") a.browser = argv[++i];
    else if (t === "--pad") a.pad = Number(argv[++i]);
    else if (t === "--min") a.min = Number(argv[++i]);
    else if (t === "--max") a.max = Number(argv[++i]);
    else rest.push(t);
  }
  // --width 优先级更高，直接把窗口宽当结果；否则用 CSS 视口宽换算
  a.windowWidth = a.width != null ? a.width : a.cssWidth + SCROLLBAR_PX;
  a.input = rest[0];
  return a;
}

const args = parseArgs(process.argv.slice(2));

if (process.argv.includes("-h") || process.argv.includes("--help")) {
  console.log(`html_to_image.mjs — 把一个 HTML 页面导出成 PNG（用于分享）

为什么需要它：am 生成的页面按视口高度排版，直接用固定窗口截图会在底部留一大片空白。
本工具先用 --dump-dom 量出真实内容高度，再按这个高度截图。

用法：
  node html_to_image.mjs <page.html> [-o out.png] [--css-width 990] [--scale 2] [--pad 0]
                                     [--browser <chrome|edge 路径>] [--min 900] [--max 40000]

参数：
  <page.html>     输入页面（必填）
  -o, --out       输出 PNG；默认与输入同名 .png
  --css-width     CSS 视口宽度，默认 990。**这个值同时决定排版和字清不清楚**
                  990 是按"图缩到常见阅读宽度时字号 1:1"反推的：1980px 的图
                  （990 × 2）在约 990px 宽阅读时是原生大小，13px 正文就是 13px。
                  不要随便调大：视口越宽，导出的图越宽、被压得越狠。
                  1710px 视口出 3420px 的图，缩到 990 只剩 58%，13px 正文变 7.5px。
                  也不要低于 1100 太多：am 在 1100px 以下把 grid 从 3 列塌成 2 列。
  --width         Chrome 窗口宽度；给了它就忽略 --css-width（两者差 18px 滚动条）
  --scale         设备像素倍率，默认 2
  --pad           内容高度额外补白（px），默认 0
  --min / --max   高度上下限，默认 900 / 40000
  --browser       显式指定 Chrome 或 Edge；默认自动探测
  -h, --help      显示本帮助

输出：
  <out.png>  <宽>x<高>  <字节数 B>
  浏览器 <路径>
  内容框 main: ...px · 文档高 ...px · 窗口 ... · 倍率 ...
`);
  process.exit(0);
}

if (!args.input) {
  console.error("usage: node html_to_image.mjs <page.html> [-o out.png] [--width 1440] [--scale 2] [--pad 0]");
  console.error("       node html_to_image.mjs --help");
  process.exit(2);
}
const input = resolve(args.input);
if (!existsSync(input)) {
  console.error(`✗ 找不到文件: ${input}`);
  process.exit(2);
}
const out = resolve(args.out || input.replace(/\.html?$/i, "") + ".png");

const browser = args.browser || BROWSERS.find((p) => existsSync(p));
if (!browser) {
  console.error("✗ 找不到 Chrome 或 Edge。用 --browser <path> 指定。");
  process.exit(2);
}

const fileUrl = "file:///" + input.replace(/\\/g, "/").replace(/^\//, "");

// ---- 0) 摘掉页脚的 colophon ------------------------------------------------
// am 会在页面底部生成 "Generated by Answer me with HTML 0.4.15 · <时间>"。
// 它是工具署名，对读报告的人没有信息量，印在成品图上更像水印。
// 本仓库在 README 与文件头保留了完整署名与许可证说明（MIT，允许修改），
// 产品文档里也写明了报告由 am 渲染，署名没有丢。
function stripColophon(html) {
  return html.replace(/<footer class="am-colophon">[\s\S]*?<\/footer>/g, "");
}

// ---- 0b) 统一字体 ----------------------------------------------------------
// am 的 base CSS 把表头 (.am-md th)、键值标签 (.am-kv dt)、面板角标 (.am-panel-meta)
// 都设成等宽字体 `font: 11px/1.3 var(--font-mono)`。中文报告里这会让"等级""这一档的样子"
// 这些中文标签显示成外挂字形，整页看起来有两种字体。
// 这里只覆盖 font-family，字号/行高/颜色不动；code/pre/kbd 继续用等宽。
const SANS_OVERRIDE = `<style id="eoc-uniform-font">
.am-md th, .am-kv dt, .am-panel-meta, .am-head-meta b { font-family: var(--font-sans) !important; }
</style>`;

function unifyFont(html) {
  if (html.includes('id="eoc-uniform-font"')) return html;
  return html.includes("</head>")
    ? html.replace("</head>", SANS_OVERRIDE + "</head>")
    : SANS_OVERRIDE + html;
}

// ---- 1) measure -----------------------------------------------------------
const tmp = mkdtempSync(join(tmpdir(), "am2img-"));
const probe = join(tmp, "probe.html");
// 测量与截图都用同一个整理过的副本，保证两次的 DOM 一致
const clean = unifyFont(stripColophon(readFileSync(input, "utf8")));
//: 整理后的副本，截图也用它（删页脚、统一字体都不改布局的列数）
const shotSrc = join(tmp, "page.html");
writeFileSync(shotSrc, clean, "utf8");
const script = `<script>
setTimeout(function () {
  var de = document.documentElement, b = document.body;
  var main = document.querySelector('main') || b;
  var r = main.getBoundingClientRect();
  var pre = document.createElement('pre'); pre.id = 'MEASURE';
  pre.textContent = JSON.stringify({ mainH: Math.ceil(r.height), mainTop: Math.ceil(r.top), docH: de.scrollHeight, clientH: de.clientHeight, w: de.clientWidth });
  document.body.appendChild(pre);
}, 2200);
</script>`;
writeFileSync(probe, clean + script, "utf8");

let measure;
try {
  const dom = execFileSync(
    browser,
    ["--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
     `--window-size=${args.windowWidth},1200`, "--virtual-time-budget=9000", "--dump-dom",
     "file:///" + probe.replace(/\\/g, "/").replace(/^\//, "")],
    { encoding: "utf8", maxBuffer: 1 << 28, stdio: ["ignore", "pipe", "ignore"] },
  );
  const m = dom.match(/<pre id="MEASURE">(.*?)<\/pre>/s);
  if (!m) throw new Error("测量脚本未返回结果");
  measure = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&"));
} catch (e) {
  console.error("✗ 测量页面高度失败: " + e.message);
  process.exit(1);
}

// page content = main box (sheets are viewport-sized, so we take the real box)
let height = Math.ceil(measure.mainTop + measure.mainH) + args.pad;
height = Math.max(args.min, Math.min(args.max, height));
if (measure.docH > measure.clientH) {
  // a genuinely scrolling page: use the document height
  height = Math.min(args.max, measure.docH + args.pad);
}

// ---- 2) screenshot --------------------------------------------------------
try {
  execFileSync(
    browser,
    ["--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
     `--force-device-scale-factor=${args.scale}`, `--window-size=${args.windowWidth},${Math.ceil(height)}`,
     "--virtual-time-budget=9000", `--screenshot=${out}`,
     "file:///" + shotSrc.replace(/\\/g, "/").replace(/^\//, "")],
    { stdio: ["ignore", "ignore", "ignore"], maxBuffer: 1 << 28 },
  );
} catch (e) {
  console.error("✗ 截图失败: " + e.message);
  process.exit(1);
}
if (!existsSync(out)) {
  console.error("✗ 截图未生成: " + out);
  process.exit(1);
}
const bytes = statSync(out).size;
console.log(`${out}  ${args.windowWidth * args.scale}x${Math.ceil(height * args.scale)}  ${bytes} B`);
console.log(`  浏览器 ${browser}`);
console.log(`  内容框 main: ${measure.mainH}px（top ${measure.mainTop}px）· 文档高 ${measure.docH}px · CSS 视口 ${args.cssWidth}px · 窗口 ${args.windowWidth}x${height} · 倍率 ${args.scale}`);
