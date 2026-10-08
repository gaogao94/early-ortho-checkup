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
 *   node html_to_image.mjs <page.html> [-o out.png] [--width 1440] [--scale 2]
 *                           [--browser <path>] [--pad 0]
 *
 * Prints one line: "<out.png>  <w>x<h>  <bytes> B"
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

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
  const a = { out: null, width: 1440, scale: 2, browser: null, pad: 0, min: 900, max: 20000 };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === "-o" || t === "--out") a.out = argv[++i];
    else if (t === "--width") a.width = Number(argv[++i]);
    else if (t === "--scale") a.scale = Number(argv[++i]);
    else if (t === "--browser") a.browser = argv[++i];
    else if (t === "--pad") a.pad = Number(argv[++i]);
    else if (t === "--min") a.min = Number(argv[++i]);
    else if (t === "--max") a.max = Number(argv[++i]);
    else rest.push(t);
  }
  a.input = rest[0];
  return a;
}

const args = parseArgs(process.argv.slice(2));

if (process.argv.includes("-h") || process.argv.includes("--help")) {
  console.log(`html_to_image.mjs — 把一个 HTML 页面导出成 PNG（用于分享）

为什么需要它：am 生成的页面按视口高度排版，直接用固定窗口截图会在底部留一大片空白。
本工具先用 --dump-dom 量出真实内容高度，再按这个高度截图。

用法：
  node html_to_image.mjs <page.html> [-o out.png] [--width 1440] [--scale 2] [--pad 0]
                                     [--browser <chrome|edge 路径>] [--min 900] [--max 20000]

参数：
  <page.html>     输入页面（必填）
  -o, --out       输出 PNG；默认与输入同名 .png
  --width         视口宽度（CSS px），默认 1440
  --scale         设备像素倍率，默认 2（即 1440 → 2880px 宽）
  --pad           内容高度额外补白（px），默认 0
  --min / --max   高度上下限，默认 900 / 20000
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

// ---- 1) measure -----------------------------------------------------------
const tmp = mkdtempSync(join(tmpdir(), "am2img-"));
const probe = join(tmp, "probe.html");
const html = readFileSync(input, "utf8");
const script = `<script>
setTimeout(function () {
  var de = document.documentElement, b = document.body;
  var main = document.querySelector('main') || b;
  var r = main.getBoundingClientRect();
  var h = Math.ceil(r.height + r.top + (de.scrollHeight - de.clientHeight > 0 ? 0 : 0));
  var pre = document.createElement('pre'); pre.id = 'MEASURE';
  pre.textContent = JSON.stringify({ mainH: Math.ceil(r.height), mainTop: Math.ceil(r.top), docH: de.scrollHeight, clientH: de.clientHeight, w: de.clientWidth });
  document.body.appendChild(pre);
}, 2200);
</script>`;
writeFileSync(probe, html + script, "utf8");

let measure;
try {
  const dom = execFileSync(
    browser,
    ["--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
     `--window-size=${args.width},1200`, "--virtual-time-budget=9000", "--dump-dom",
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
     `--force-device-scale-factor=${args.scale}`, `--window-size=${args.width},${height}`,
     "--virtual-time-budget=9000", `--screenshot=${out}`, fileUrl],
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
console.log(`${out}  ${args.width * args.scale}x${height * args.scale}  ${bytes} B`);
console.log(`  浏览器 ${browser}`);
console.log(`  内容框 main: ${measure.mainH}px（top ${measure.mainTop}px）· 文档高 ${measure.docH}px · 窗口 ${args.width}x${height} · 倍率 ${args.scale}`);
