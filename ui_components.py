"""
风电塔灾损测算软件 — UI 组件与设计令牌模块

统一管理全局 CSS 令牌（颜色/字体/间距/圆角/阴影/动效）与
可复用 HTML 组件模板（风险徽章、摘要卡、折叠板块、空状态、状态条、统计卡、表格）。

设计规范详见 DEVELOPMENT_PLAN.md §5（设计系统 v2）。
所有颜色走 CSS 变量；风险语义色沿用 formatter.RISK_COLORS 原值，不改变数据含义。
"""

import html as _html

import i18n


# ══════════════════════════════════════════════════════════
#  设计令牌 + 全局样式
#  注入方式说明（重要）：主页面（Gradio）通过 server.py 的 head 参数
#  注入 <link rel="stylesheet" href="/wd-assets/base.css"> 加载本文件；
#  独立页（FastAPI 直渲染）由 page_shell 直接内嵌 BASE_CSS。
#  不能用 css= 参数：Gradio 会把 css= 里的每条规则都加
#  ".gradio-container... .contain" 前缀（用于组件级作用域），
#  html/body/:root 这类顶层规则被前缀化后在主页面上失效
#  ——这正是"主页面背景/字体全不生效"的根因。
# ══════════════════════════════════════════════════════════

BASE_CSS = """
:root {
  /* 品牌色 */
  --brand-900:#0D3A66; --brand-700:#125191; --brand-500:#1E6BB8; --brand-100:#E3EEF8;
  /* 语义色（= formatter.RISK_COLORS，仅表达业务风险） */
  --danger:#E74C3C; --danger-deep:#C0392B; --danger-bg:#FDEDEB;
  --warn:#F39C12;   --warn-deep:#B9770E;   --warn-bg:#FEF5E7;
  --success:#27AE60;--success-deep:#1E8449;--success-bg:#EAF7F0;
  --info:#3498DB;   --info-bg:#EBF5FB;
  /* 中性色 */
  --text-1:#1F2933; --text-2:#52606D; --text-3:#9AA5B1;
  --border:#E4E7EB; --bg-page:#F5F7FA; --bg-card:#FFFFFF;
  --table-head:#F0F3F7;
  /* 表面色（主题可覆盖） */
  --bg-card-tint:rgba(255,255,255,.94);
  --bg-field:#FFFFFF;
  --row-danger-hover:#FBDDD9;
  --veil-top:rgba(245,247,250,.88); --veil-mid:rgba(245,247,250,.70); --veil-bot:rgba(245,247,250,.50);
  --air-top:rgba(250,253,255,.50); --air-mid:rgba(248,253,251,.30); --air-bot:rgba(246,252,247,.22);
  --turbine-sky:#8ED0F2; --turbine-border:#8AB9CB;
  /* 阴影 / 焦点 / 遮罩 */
  --shadow-1:0 1px 3px rgba(31,41,51,.08);
  --shadow-2:0 4px 12px rgba(31,41,51,.12);
  --focus-ring:0 0 0 3px rgba(30,107,184,.22);
  --overlay:rgba(15,23,42,.45);
  /* 动效 */
  --duration-fast:120ms; --duration-normal:200ms;
  --ease-standard:cubic-bezier(.2,0,0,1);
}

/* ── 页面基调（动态风场背景 + 宋体/Times New Roman 字体）──
   主页面由固定 iframe 绘制蓝天、云层、摆动草地与旋转风机；独立认证页仍以
   bg_photo.jpg 作为无脚本兜底。顶层规则必须通过 head 内联样式注入。 */
:root {
  --bg-photo: url("/wd-assets/bg_photo.jpg");
  --font-stack: "Times New Roman", "SimSun", "宋体", "NSimSun", serif;
  --wd-fs: 1.15;
}
html { background:var(--bg-page) !important; }
html, body, gradio-app, .gradio-container { background:transparent !important; }
body { margin:0; }
body::before {
  content:""; position:fixed; inset:0; z-index:-3; pointer-events:none;
  background:
    linear-gradient(180deg,var(--veil-top) 0%,var(--veil-mid) 54%,var(--veil-bot) 100%),
    var(--bg-photo) center / cover no-repeat;
}
.wd-dynamic-bg-host {
  position:fixed !important; inset:0 !important; width:100vw !important; height:100vh !important;
  z-index:-2 !important; pointer-events:none !important; overflow:hidden !important;
  border:0 !important; padding:0 !important; margin:0 !important; background:transparent !important;
}
.wd-dynamic-bg-host iframe { width:100%; height:100%; border:0; display:block; }
/* 浅色空气蒙版保证任何时刻文字均清晰，同时保留草地与风机的运动感。 */
body::after {
  content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
  background:linear-gradient(180deg,var(--air-top),var(--air-mid) 58%,var(--air-bot));
}
.gradio-container, .gradio-container button, .gradio-container input,
.gradio-container textarea, .gradio-container select,
.gradio-container .prose, body, body button, body input, body select, body textarea {
  font-family: var(--font-stack) !important;
}
.gradio-container { font-variant-numeric: tabular-nums; }

/* ── 统一字号缩放：--wd-fs 只在 :root 定义，由显示设置脚本动态覆盖。
   所有主题字号和关键硬编码字号均引用同一变量，避免容器局部变量遮蔽设置。 ── */
.gradio-container {
  --text-xs: calc(13px * var(--wd-fs)) !important;
  --text-sm: calc(14px * var(--wd-fs)) !important; --block-info-text-size: calc(14px * var(--wd-fs)) !important;
  --block-label-text-size: calc(14px * var(--wd-fs)) !important; --block-title-text-size: calc(15px * var(--wd-fs)) !important;
  --body-text-size: calc(16px * var(--wd-fs)) !important; --text-md: calc(16px * var(--wd-fs)) !important;
  --text-lg: calc(18px * var(--wd-fs)) !important; --text-xl: calc(24px * var(--wd-fs)) !important;
  --text-xxl: calc(28px * var(--wd-fs)) !important;
}
.gradio-container.gradio-container-6-26-0 { font-size: var(--text-md) !important; }
.gradio-container .prose, .gradio-container label, .gradio-container input,
.gradio-container textarea, .gradio-container select { font-size:calc(16px * var(--wd-fs)) !important; }
.gradio-container button { min-height:44px; font-size:calc(16px * var(--wd-fs)) !important; padding:9px 16px !important; }
.gradio-container .tab-nav { min-height:48px; }
.gradio-container .tab-nav button {
  min-height:46px; padding:0 20px !important; font-size:calc(16px * var(--wd-fs)) !important; font-weight:600;
}

/* 注意：不隐藏 Gradio 自带页脚（Use via API / 设置等入口）。
   旧写法因 css= 前缀化而从未生效；样式注入修复后若加此规则会把
   页脚入口一起藏掉，故明确不加（2026-02 反馈）。 */

/* ── 下拉选择框：字号随框宽自适应 + 更顺滑的展开/悬停 ──
   注意：不加自定义展开动画/悬停过渡——与 Gradio 自带弹出动画叠加会导致卡顿，
   悬停高亮即时生效（无过渡）反而手感更跟手。 */
.gradio-container .dropdown input,
.gradio-container .dropdown button,
.gradio-container ul.options,
.gradio-container ul.options li {
  font-size: calc(15px * var(--wd-fs)) !important;
}
.gradio-container ul.options {
  max-height: 300px; overflow-y: auto;
}
.gradio-container ul.options li {
  padding: 8px 12px; cursor: pointer; user-select: none;
}
.gradio-container ul.options li:hover,
.gradio-container ul.options li.selected { background: var(--brand-100); }

.main-title { text-align:center; padding:14px 0 6px; }
.main-title h1 { font-size:32px; color:var(--brand-700); margin-bottom:4px; letter-spacing:.5px; }
.title-icon { display:inline-flex; vertical-align:-7px; margin-right:8px; }
.footer-note { text-align:center; color:var(--text-3); font-size:12px; padding:12px 0 4px; margin-top:10px; }

/* ── 卡片 ─────────────────────────────────────────── */
.wd-card {
  background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); padding:16px; margin-bottom:16px;
}

/* ── 结论摘要卡（结果页第一层） ────────────────────── */
.wd-summary {
  background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); padding:16px 18px; margin-bottom:16px;
  border-left:4px solid var(--success);
}
.wd-summary.wd-tone-danger  { border-left-color:var(--danger);  background:var(--danger-bg); }
.wd-summary.wd-tone-warn    { border-left-color:var(--warn);    background:var(--warn-bg); }
.wd-summary.wd-tone-success { border-left-color:var(--success); background:var(--success-bg); }
.wd-summary-grid { display:flex; flex-wrap:wrap; gap:8px 32px; align-items:center; }
.wd-summary-item { min-width:120px; }
.wd-summary-item .wd-label { font-size:calc(14px * var(--wd-fs)); color:var(--text-2); margin-bottom:2px; }
.wd-summary-item .wd-value { font-size:calc(18px * var(--wd-fs)); font-weight:600; color:var(--text-1); }
.wd-summary-title { font-size:calc(17px * var(--wd-fs)); font-weight:600; color:var(--text-1); margin-bottom:10px; }

/* ── 风险横幅（浅底 + 色条，不用高饱和红块） ───────── */
.wd-banner {
  display:flex; align-items:center; gap:10px;
  border-radius:8px; padding:12px 16px; margin-bottom:16px;
  background:var(--danger-bg); border-left:4px solid var(--danger);
}
.wd-banner .wd-banner-text { font-size:calc(16px * var(--wd-fs)); font-weight:600; color:var(--danger-deep); }

/* ── 风险徽章（胶囊，浅底深字，文字+颜色双通道） ───── */
.wd-badge {
  display:inline-block; padding:2px 12px; border-radius:999px;
  font-size:calc(14px * var(--wd-fs)); font-weight:600; line-height:22px; white-space:nowrap;
}
.wd-badge-danger  { background:var(--danger-bg);  color:var(--danger-deep); }
.wd-badge-warn    { background:var(--warn-bg);    color:var(--warn-deep); }
.wd-badge-success { background:var(--success-bg); color:var(--success-deep); }
.wd-badge-muted   { background:var(--table-head); color:var(--text-2); }
/* 表格单元格内：徽章与同行纯文字垂直居中对齐（胶囊略收窄，避免视觉下坠） */
table.wd-table td .wd-badge { vertical-align: middle; line-height: 18px; padding: 1px 10px; }

/* ── 折叠板块（详细报告分组） ──────────────────────── */
details.wd-sec {
  background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); margin-bottom:12px; overflow:hidden;
}
details.wd-sec > summary {
  cursor:pointer; list-style:none; display:flex; align-items:center; gap:8px;
  padding:12px 16px; font-size:calc(17px * var(--wd-fs)); font-weight:600; color:var(--brand-700);
  background:var(--table-head); border-bottom:1px solid transparent;
  transition:background var(--duration-fast) var(--ease-standard);
}
details.wd-sec > summary::-webkit-details-marker { display:none; }
details.wd-sec > summary::after {
  content:"▾"; margin-left:auto; color:var(--text-3); font-size:12px;
  transition:transform var(--duration-fast) var(--ease-standard);
}
details.wd-sec:not([open]) > summary:hover { background:var(--brand-100); }
details.wd-sec[open] > summary { border-bottom-color:var(--border); }
details.wd-sec[open] > summary::after { transform:rotate(180deg); }
details.wd-sec > .wd-sec-body { padding:12px 16px; }

/* ── 键值表格（报告字段） ──────────────────────────── */
table.wd-kv { width:100%; border-collapse:collapse; font-size:calc(16px * var(--wd-fs)); }
table.wd-kv td { padding:7px 8px; vertical-align:top; border-bottom:1px solid var(--border); }
table.wd-kv tr:last-child td { border-bottom:none; }
table.wd-kv td.wd-kv-label { width:150px; color:var(--text-2); white-space:nowrap; }
table.wd-kv td.wd-kv-value { color:var(--text-1); font-weight:500; word-break:break-word; }

/* ── 数据表格（历史/批量） ─────────────────────────── */
.table-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); background:var(--bg-card); }
table.wd-table { width:100%; border-collapse:collapse; font-size:calc(15px * var(--wd-fs)); }
table.wd-table th {
  background:var(--table-head); color:var(--text-2); font-weight:600;
  padding:9px 10px; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--border);
  position:sticky; top:0;
}
table.wd-table td { padding:7px 10px; border-bottom:1px solid var(--border); color:var(--text-1); }
table.wd-table tbody tr:nth-child(even) { background:var(--bg-page); }
table.wd-table tbody tr:hover { background:var(--brand-100); }
table.wd-table tr.wd-row-danger { background:var(--danger-bg); }
table.wd-table tr.wd-row-danger:hover { background:var(--row-danger-hover); }
table.wd-table td.wd-num { font-variant-numeric:tabular-nums; text-align:right; }

/* ── 统计卡 ────────────────────────────────────────── */
.wd-stats { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; }
.wd-stat {
  flex:1; min-width:140px; background:var(--bg-card); border:1px solid var(--border);
  border-radius:8px; box-shadow:var(--shadow-1); padding:14px; text-align:center;
  border-top:3px solid var(--brand-500);
}
.wd-stat .wd-stat-num { font-size:28px; font-weight:700; color:var(--brand-700);
  font-variant-numeric:tabular-nums; }
.wd-stat .wd-stat-label { font-size:13px; color:var(--text-2); margin-top:2px; }
.wd-stat.wd-tone-danger  { border-top-color:var(--danger); }
.wd-stat.wd-tone-danger  .wd-stat-num { color:var(--danger-deep); }
.wd-stat.wd-tone-warn    { border-top-color:var(--warn); }
.wd-stat.wd-tone-warn    .wd-stat-num { color:var(--warn-deep); }
.wd-stat.wd-tone-success { border-top-color:var(--success); }
.wd-stat.wd-tone-success .wd-stat-num { color:var(--success-deep); }

/* ── 空状态 ────────────────────────────────────────── */
.wd-empty {
  border:1.5px dashed var(--border); border-radius:8px;
  padding:44px 24px; text-align:center; background:var(--bg-card);
}
.wd-empty .wd-empty-title { font-size:17px; color:var(--text-1); font-weight:600; margin:10px 0 6px; }
.wd-empty .wd-empty-desc  { font-size:13px; color:var(--text-3); }

/* ── 状态条 ────────────────────────────────────────── */
.wd-status {
  border-radius:8px; padding:10px 14px; font-size:14px; margin-bottom:12px;
  border-left:4px solid var(--info); background:var(--info-bg); color:var(--text-1);
}
.wd-status.wd-status-success { border-left-color:var(--success); background:var(--success-bg); }
.wd-status.wd-status-error   { border-left-color:var(--danger);  background:var(--danger-bg);  color:var(--danger-deep); }
.wd-status.wd-status-warn    { border-left-color:var(--warn);    background:var(--warn-bg);    color:var(--warn-deep); }

/* ── 等待动效：分析进行中状态条的旋转 spinner ── */
.wd-working { display:flex; align-items:center; gap:10px; }
.wd-spinner { flex:0 0 auto; width:16px; height:16px; border-radius:50%;
  border:2.5px solid var(--brand-100); border-top-color:var(--brand-500);
  animation:wd-spin .8s linear infinite; }
@keyframes wd-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .wd-spinner { animation-duration:2.4s; }
}

/* ── 图表卡 ────────────────────────────────────────── */
.wd-chart-card { flex:1; min-width:240px; background:var(--bg-card);
  border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow-1); padding:10px; }
.wd-charts { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:16px; }
.wd-chart-card img { width:100%; border-radius:6px; display:block; }

/* ── 危险按钮（清空/删除类） ───────────────────────── */
button.wd-btn-danger {
  background:var(--bg-card) !important; color:var(--danger-deep) !important;
  border:1px solid var(--danger) !important;
}
button.wd-btn-danger:hover { background:var(--danger-bg) !important; }

/* ── 筛选工具栏 / 分页 ─────────────────────────────── */
.wd-filterbar { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:flex-end;
  background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); padding:12px 14px; margin-bottom:14px; }
.wd-filterbar .wd-fitem { display:flex; flex-direction:column; gap:4px; min-width:130px; }
.wd-filterbar .wd-flabel { font-size:12px; color:var(--text-2); }
.wd-filterbar .wd-finput { border:1px solid var(--border); border-radius:6px;
  padding:6px 10px; font-size:14px; background:var(--bg-card); color:var(--text-1); }
.wd-filterbar .wd-finput:focus { outline:none; box-shadow:var(--focus-ring); border-color:var(--brand-500); }
.wd-total-count { font-size:13px; color:var(--text-2); margin-left:auto; align-self:center; }
.wd-pager { display:flex; align-items:center; gap:12px; justify-content:center;
  padding:12px 0 4px; }
.wd-pager .wd-page-btn { border:1px solid var(--border); background:var(--bg-card);
  color:var(--text-1); border-radius:6px; padding:6px 16px; font-size:13px; cursor:pointer; }
.wd-pager .wd-page-btn:disabled { color:var(--text-3); cursor:not-allowed; }
.wd-pager .wd-page-info { font-size:13px; color:var(--text-2); font-variant-numeric:tabular-nums; }

/* ── 详情页头部 / 返回链接 ─────────────────────────── */
.wd-page-head { max-width:var(--reading-max, 880px); margin:0 auto; padding:20px 16px 0; }
.wd-backlink { font-size:14px; color:var(--brand-500); text-decoration:none; }
.wd-backlink:hover { text-decoration:underline; }

/* ── 桌面 / 移动双渲染切换（服务端渲染两套，CSS 切换显示） ── */
.wd-mobile-only { display:none; }
@media (max-width: 767px) {
  .wd-desktop-only { display:none; }
  .wd-mobile-only { display:block; }
}

/* ── 移动端历史卡片 ────────────────────────────────── */
.wd-mcard { background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
  box-shadow:var(--shadow-1); padding:12px 14px; margin-bottom:10px; }
.wd-mcard.wd-row-danger { background:var(--danger-bg); }
.wd-mcard .wd-mcard-head { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
.wd-mcard .wd-mcard-name { font-size:14px; color:var(--text-2); word-break:break-all; }
.wd-mcard .wd-mcard-meta { font-size:12px; color:var(--text-3); margin:6px 0 10px;
  font-variant-numeric:tabular-nums; }
.wd-mcard .wd-mcard-actions { display:flex; gap:8px; }
.wd-mcard .wd-mcard-actions a { flex:1; text-align:center; border:1px solid var(--border);
  border-radius:6px; padding:8px 0; font-size:13px; color:var(--brand-700);
  text-decoration:none; background:var(--bg-card); }
.wd-mcard .wd-mcard-actions a.wd-mcard-primary { background:var(--brand-700);
  color:#fff; border-color:var(--brand-700); }

/* ── 单图检测工作台：保留顶栏，余下视口由左输入 / 中三维 / 右报告铺满 ─ */
.gradio-container { width:100% !important; max-width:none !important; }
.app.fillable:not(.fill_width) { max-width:none !important; width:100% !important; }
.wd-workbench-grid {
  align-items:stretch !important; gap:12px !important; flex-wrap:nowrap !important;
  width:100%; min-width:0; height:calc(100vh - 158px); height:calc(100dvh - 158px);
  min-height:610px; overflow:hidden;
}
.wd-workbench-col {
  min-width:0 !important; min-height:0 !important; height:100%; overflow:hidden;
  background:var(--bg-card-tint); border:1px solid rgba(190,210,220,.9);
  border-radius:10px; box-shadow:var(--shadow-1); padding:12px !important;
}
.wd-workbench-col > .prose:first-child h3 { margin:0 0 8px; color:var(--brand-700); }
.wd-input-col { flex:0 1 20% !important; overflow-y:auto; overflow-x:hidden; scrollbar-gutter:stable; }
.wd-input-col .image-container { min-height:230px; }
.wd-input-col .gallery {
  display:grid !important; grid-template-columns:repeat(auto-fill, 80px) !important;
  gap:8px !important; justify-content:start; padding:2px 0;
}
.wd-input-col .gallery .gallery-item,
.wd-input-col .gallery-item,
.wd-input-col .gallery .container {
  width:80px !important; height:80px !important; max-width:80px !important;
  min-width:80px !important; overflow:hidden !important; padding:0 !important;
  margin:0 !important;
}
.wd-input-col .gallery-item img,
.wd-input-col .gallery .container img {
  width:80px !important; height:80px !important; object-fit:cover !important;
}
.wd-export-row {
  flex-direction:column !important; flex-wrap:nowrap !important;
  align-items:stretch !important; gap:8px !important; margin:0 !important;
}
.wd-export-btn {
  width:100% !important; min-width:0 !important;
  white-space:nowrap !important; justify-content:center;
}
/* 三列容器一律禁止横向换列：flex-column + wrap 在列高不足时会把
   viewer 等子块“换列”推到列右侧（视口较矮时触发，页面横向错位）。
   改为 nowrap 后子块纵向堆叠；同时禁止 flex 按比例压扁超高子块
   （否则标题块会被压成十几像素、文字被裁掉半截），超出部分交给
   列内部滚动兜底；常规视口无影响。 */
.wd-workbench-col { flex-wrap:nowrap !important; justify-content:flex-start !important; }
.wd-workbench-col > * { flex-shrink:0 !important; }
.wd-model-col { flex:1 1 58% !important; display:flex !important; flex-direction:column !important; }
.wd-turbine-viewer {
  position:relative !important; flex:1 1 auto !important; min-height:620px !important; height:calc(100dvh - 230px) !important;
  padding:0 !important; overflow:hidden !important;
}
.wd-turbine-viewer > div { height:100% !important; min-height:620px !important; }
.wd-turbine-frame {
  position:absolute; inset:0; width:100%; height:100%; min-height:620px; overflow:hidden; border:1px solid var(--turbine-border);
  border-radius:9px; background:var(--turbine-sky); box-shadow:inset 0 0 24px rgba(31,89,112,.13);
}
.wd-turbine-frame iframe { width:100%; height:100%; display:block; border:0; background:var(--turbine-sky); }
.wd-report-col { flex:0 1 22% !important; flex-direction:column !important; flex-wrap:nowrap !important; overflow-y:auto !important; overflow-x:hidden !important; scrollbar-gutter:stable; }
.wd-report-col > * { flex:0 0 auto !important; min-height:min-content !important; }
.wd-report-output { flex:0 0 auto !important; height:auto !important; overflow:visible !important; }
.wd-report-col > *, .wd-report-col .html-container,
.wd-report-col .html-container > div { min-width:0 !important; max-width:100% !important; width:100%; height:auto !important; }
.wd-report-col details.wd-sec { width:100%; }
.wd-report-col table.wd-kv { table-layout:fixed; }
.wd-report-col table.wd-kv td.wd-kv-label {
  width:36%; min-width:0; white-space:normal; overflow-wrap:anywhere; word-break:break-word;
}
.wd-report-col table.wd-kv td.wd-kv-value { overflow-wrap:anywhere; word-break:break-word; }
.wd-report-col .wd-summary { padding:12px 13px; margin-bottom:10px; }
.wd-report-col .wd-summary-grid { gap:7px 14px; }
.wd-report-col .wd-summary-item { min-width:calc(50% - 8px); }
.wd-report-col .wd-banner { margin-bottom:10px; }
.wd-report-col details.wd-sec { margin-bottom:9px; }
.wd-report-col details.wd-sec > summary { padding:10px 12px; }
.wd-report-col details.wd-sec > .wd-sec-body { padding:8px 10px; }

/* ── 响应式：1280px 起保持三栏，窄屏回落为两栏 + 报告 ───── */
@media (max-width: 1279px) {
  .wd-workbench-grid { flex-wrap:wrap !important; height:auto; min-height:0; overflow:visible; }
  .wd-input-col { flex:1 1 34% !important; height:650px; }
  .wd-model-col { flex:1 1 58% !important; height:650px; }
  .wd-report-col { flex:1 1 100% !important; height:auto; max-height:760px; }
}
@media (max-width: 767px) {
  .main-title h1 { font-size:24px; }
  .wd-summary-grid { flex-direction:column; align-items:flex-start; }
  .wd-stat { min-width:calc(50% - 8px); }
  .wd-workbench-col { height:auto; min-height:auto !important; flex:1 1 100% !important; overflow:visible !important; }
  .wd-model-col { height:500px; }
  .wd-turbine-frame { height:440px; min-height:420px; }
  .wd-report-col { max-height:none; }
}

/* ── 动效降级 ──────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  * { transition:none !important; animation:none !important; }
}

/* ── 可访问性（§6.4 子集）：键盘焦点可见，鼠标点击不高亮 ── */
:focus { outline:none; }
:focus-visible { outline:2px solid var(--brand-500); outline-offset:2px;
  border-radius:4px; }
.wd-btn:focus-visible, button:focus-visible, a:focus-visible {
  outline:2px solid var(--brand-500); outline-offset:2px; }

/* ── 历史记录抽屉快捷预览（右侧滑出，iframe 加载独立详情页）── */
.wd-drawer-mask { position:fixed; inset:0; background:var(--overlay); z-index:9998;
  opacity:0; pointer-events:none;
  transition:opacity var(--duration-normal) var(--ease-standard); }
.wd-drawer-mask.wd-open { opacity:1; pointer-events:auto; }
.wd-drawer { position:fixed; top:0; right:0; height:100vh; width:min(600px,94vw);
  background:var(--bg-card); box-shadow:var(--shadow-2); z-index:9999;
  display:flex; flex-direction:column;
  transform:translateX(102%);
  transition:transform var(--duration-normal) var(--ease-standard); }
.wd-drawer.wd-open { transform:none; }
.wd-drawer-head { display:flex; align-items:center; gap:12px; padding:12px 16px;
  border-bottom:1px solid var(--border); background:var(--table-head); }
.wd-drawer-head .wd-drawer-title { flex:1; font-size:15px; font-weight:600;
  color:var(--brand-700); }
.wd-drawer-head a { font-size:13px; color:var(--brand-500); font-weight:600;
  text-decoration:none; white-space:nowrap; }
.wd-drawer-head a:hover { text-decoration:underline; }
.wd-drawer-head button { font-size:13px; padding:5px 14px; cursor:pointer;
  border:1px solid var(--border); border-radius:6px; background:var(--bg-card);
  color:var(--text-1); }
.wd-drawer-head button:hover { background:var(--brand-100); }
.wd-drawer-body { flex:1; overflow-y:auto; padding:14px 16px; }
.wd-drawer-body iframe { width:100%; height:100%; min-height:calc(100vh - 70px);
  border:none; display:block; }
.wd-preview-link { color:var(--brand-500); cursor:pointer; user-select:none;
  font-size:12px; margin-left:8px; text-decoration:underline; white-space:nowrap; }
.wd-preview-link:hover { color:var(--brand-700); }
.wd-mcard-actions .wd-preview-link { flex:0 0 auto; margin-left:0; margin-right:8px;
  text-align:center; border:1px solid var(--border); border-radius:6px;
  padding:8px 12px; color:var(--brand-700); text-decoration:none;
  background:var(--bg-card); display:inline-block; }

/* ── 显示设置弹层（右上角"设置"打开；深浅模式 + 字号缩放）── */
.wd-settings-mask { position:fixed; inset:0; background:var(--overlay); z-index:9990;
  opacity:0; pointer-events:none;
  transition:opacity var(--duration-normal) var(--ease-standard); }
.wd-settings-mask.wd-open { opacity:1; pointer-events:auto; }
.wd-settings-popover { position:fixed; top:56px; right:16px; z-index:9991;
  width:min(320px,92vw); background:var(--bg-card); border:1px solid var(--border);
  border-radius:10px; box-shadow:var(--shadow-2); padding:14px 16px;
  opacity:0; transform:translateY(-6px); pointer-events:none;
  transition:opacity var(--duration-normal) var(--ease-standard),
             transform var(--duration-normal) var(--ease-standard); }
.wd-settings-popover.wd-open { opacity:1; transform:none; pointer-events:auto; }
.wd-sp-head { display:flex; align-items:center; justify-content:space-between;
  margin-bottom:10px; }
.wd-sp-title { font-size:15px; font-weight:600; color:var(--text-1); }
.wd-sp-head button { font-size:12px; padding:4px 10px; cursor:pointer;
  border:1px solid var(--border); border-radius:6px; background:var(--bg-page);
  color:var(--text-2); }
.wd-sp-head button:hover { background:var(--brand-100); color:var(--brand-700); }
.wd-sp-row { margin-bottom:12px; }
.wd-sp-row:last-child { margin-bottom:0; }
.wd-sp-label { display:block; font-size:13px; color:var(--text-2); margin-bottom:6px; }
.wd-sp-seg { display:flex; gap:8px; }
.wd-sp-seg.wd-sp-skin { flex-wrap:wrap; }
.wd-sp-seg.wd-sp-skin button { flex:1 0 28%; }
.wd-sp-seg button { flex:1; font-size:13px; padding:7px 0; cursor:pointer;
  border:1px solid var(--border); border-radius:6px; background:var(--bg-page);
  color:var(--text-2); }
.wd-sp-seg button.wd-active { background:var(--brand-500); border-color:var(--brand-500);
  color:#fff; font-weight:600; }
.wd-sp-font { display:flex; align-items:center; gap:10px; }
.wd-sp-font input[type="range"] { flex:1; accent-color:var(--brand-500); }
.wd-sp-font span { font-size:13px; color:var(--text-1); min-width:42px; text-align:right; }
.wd-sp-font button { font-size:12px; padding:4px 10px; cursor:pointer;
  border:1px solid var(--border); border-radius:6px; background:var(--bg-page);
  color:var(--text-2); }
.wd-sp-font button:hover { background:var(--brand-100); }

/* ── 批量进度日志（可滚动，column-reverse 使新内容保持在视野底部）── */
.wd-progress-box { max-height:230px; overflow-y:auto; display:flex;
  flex-direction:column-reverse; border:1px solid var(--border); border-radius:8px;
  background:var(--table-head); }
.wd-progress-box pre.wd-progress-log { margin:0; padding:10px 12px;
  font-size:13px; line-height:1.7; white-space:pre-wrap; word-break:break-all;
  font-family:var(--font-stack) !important; color:var(--text-1); }

/* ── 记录巡检图像卡（历史详情 / 独立页 / 抽屉预览共用）────── */
.wd-img-card { background:var(--bg-card); border:1px solid var(--border);
  border-radius:8px; box-shadow:var(--shadow-1); padding:10px 12px; margin-bottom:16px; }
.wd-img-card .wd-img-title { font-size:13px; color:var(--text-2); margin-bottom:8px; }
.wd-img-card img { width:100%; height:auto; display:block; border-radius:6px; }

/* ── 认证页（登录/注册/初始化，§10）── 卡片加宽加大，输入区更舒展 */
.wd-auth-wrap { min-height:calc(100vh - 40px); display:flex; align-items:center;
  justify-content:center; padding:24px 16px; }
.wd-auth-card { width:100%; max-width:480px; background:var(--bg-card);
  border:1px solid var(--border); border-radius:14px; box-shadow:var(--shadow-2);
  padding:36px 40px 32px; }
.wd-auth-card h1 { font-size:24px; margin:0 0 6px; color:var(--text-1);
  display:flex; align-items:center; gap:10px; }
.wd-auth-card h1 svg { width:30px; height:30px; }
.wd-auth-sub { font-size:14px; color:var(--text-3); margin:0 0 22px; line-height:1.55; }
.wd-field { margin-bottom:16px; }
.wd-field label { display:block; font-size:14px; color:var(--text-2);
  font-weight:600; margin-bottom:6px; }
.wd-field input[type="text"], .wd-field input[type="password"] {
  width:100%; box-sizing:border-box; padding:12px 14px; font-size:15px;
  border:1px solid var(--border); border-radius:8px; background:var(--bg-field);
  color:var(--text-1); }
.wd-field input:focus { outline:2px solid var(--brand-500); outline-offset:1px;
  border-color:var(--brand-500); }
.wd-field-row { display:flex; align-items:center; justify-content:space-between;
  margin-top:6px; font-size:12px; color:var(--text-3); }
.wd-field-row label { font-weight:400; display:flex; align-items:center; gap:5px;
  margin:0; cursor:pointer; }
.wd-form-error { color:#C0392B; font-size:13px; margin:2px 0 10px; line-height:1.45; }
.wd-pw-rules { list-style:none; margin:8px 0 0; padding:0; font-size:12px; }
.wd-pw-rules li { color:var(--text-3); margin-bottom:3px; }
.wd-pw-rules li::before { content:"○ "; }
.wd-pw-rules li.wd-rule-ok { color:#1E8449; }
.wd-pw-rules li.wd-rule-ok::before { content:"● "; }

/* ── 密码强度实时提示条（F5）：宽度=得分比例，颜色随 弱/中/强 变化 ── */
.wd-pw-meter { display:flex; align-items:center; gap:8px; margin-top:8px; }
.wd-pw-meter-bar { flex:1; height:6px; border-radius:3px;
  background:var(--table-head); overflow:hidden; }
.wd-pw-meter-bar span { display:block; height:100%; width:0; border-radius:3px;
  background:var(--danger);
  transition:width var(--duration-normal) var(--ease-standard),
             background var(--duration-normal) var(--ease-standard); }
.wd-pw-meter.wd-pw-medium .wd-pw-meter-bar span { background:var(--warn); }
.wd-pw-meter.wd-pw-strong .wd-pw-meter-bar span { background:var(--success); }
.wd-pw-meter-label { font-size:12px; color:var(--text-2); min-width:2em; text-align:right; }
.wd-auth-alt { margin-top:16px; padding-top:14px; border-top:1px solid var(--border);
  font-size:13px; color:var(--text-3); }
.wd-auth-alt a { color:var(--brand-500); font-weight:600; text-decoration:none; }
.wd-auth-alt a:hover { text-decoration:underline; }
.wd-btn-primary-block { width:100%; padding:13px 0; font-size:16px; font-weight:600;
  background:var(--brand-700); color:#fff; border:none; border-radius:8px;
  cursor:pointer; margin-top:8px; }
.wd-btn-primary-block:hover { background:var(--brand-500); }
.wd-auth-banner { max-width:480px; margin:0 auto 12px; border-radius:8px;
  padding:11px 14px; font-size:13px; line-height:1.5; }
.wd-auth-banner.wd-banner-warn { background:#FEF5E7; border:1px solid #F5B041; color:#7E5109; }
.wd-auth-banner.wd-banner-error { background:var(--danger-bg, #FDEDEC); border:1px solid #EC7063; color:#943126; }

/* ── 用户管理表 ────────────────────────────────────── */
.wd-users-wrap { max-width:var(--reading-max, 880px); margin:0 auto; padding:24px 16px; }
.wd-users-actions { display:flex; gap:6px; flex-wrap:wrap; }
.wd-users-actions form { display:inline-flex; gap:6px; align-items:center; }
.wd-users-actions button, .wd-users-actions input[type="submit"] {
  font-size:12px; padding:5px 10px; border:1px solid var(--border); border-radius:6px;
  background:var(--bg-card); color:var(--brand-700); cursor:pointer; }
.wd-users-actions .wd-u-danger { color:#C0392B; border-color:#EC7063; }
.wd-users-actions input[type="password"] { padding:4px 8px; font-size:12px;
  border:1px solid var(--border); border-radius:6px; width:170px; }

/* ── 顶栏用户徽章 ──────────────────────────────────── */
.wd-user-badge { display:flex; gap:12px; align-items:center; justify-content:flex-end;
  max-width:1280px; margin:0 auto; padding:8px 16px 0; font-size:15px; min-height:24px; }
.wd-user-badge:empty { display:none; }
.wd-user-badge a { color:var(--brand-500); font-weight:600; text-decoration:none; }
.wd-user-badge a:hover { text-decoration:underline; }
.wd-user-badge .wd-ub-name { font-weight:600; color:var(--text-2);
  max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
/* 徽章行内的角色胶囊（管理员/普通用户）跟随放大，但仍比链接略小一档 */
.wd-user-badge .wd-badge { font-size:14px; line-height:22px; }
/* 账号胶囊容器：仅承载布局（图标在非 HUD 皮肤下隐藏，视觉与原版一致） */
.wd-user-badge .wd-ub-chip { display:inline-flex; align-items:center; gap:6px; }
/* 小图标默认隐藏——只有 HUD 皮肤启用，其余五皮肤顶栏保持原样 */
.wd-user-badge .wd-ub-ic { display:none; }

/* ── Gradio 页脚：设置按钮的宿主，视觉上隐藏但保留在 DOM ──
   右上角"设置"链接靠程序化点击页脚按钮打开设置面板（组件私有状态，
   无公开路由），故 footer_links 须含 "settings"，此处只做视觉隐藏。 */
.gradio-container footer[aria-label] {
  position: absolute !important; width: 1px !important; height: 1px !important;
  overflow: hidden !important; clip-path: inset(50%) !important;
  pointer-events: none !important;
}

/* ══════════════════════════════════════════════════════════
   五主题皮肤系统（设置弹层"界面风格"切换，localStorage 持久化）
   默认 = A 晴空浅色（:root 原值）；以下为 token 覆盖块。
   JS 在 <html> 上设 data-wd-theme 属性即时切换，无需刷新。
   ══════════════════════════════════════════════════════════ */

/* ── B 夜航 · 深色监控中枢 ── */
[data-wd-theme="night"] {
  --brand-900:#67E8F9; --brand-700:#22D3EE; --brand-500:#38BDF8; --brand-100:rgba(34,211,238,.14);
  --danger:#F87171; --danger-deep:#FCA5A5; --danger-bg:rgba(248,113,113,.13);
  --warn:#FBBF24;   --warn-deep:#FCD34D;   --warn-bg:rgba(251,191,36,.13);
  --success:#34D399;--success-deep:#6EE7B7;--success-bg:rgba(52,211,153,.13);
  --info:#38BDF8;   --info-bg:rgba(56,189,248,.13);
  --text-1:#E5EDF7; --text-2:#A9BBD4; --text-3:#7C8DB0;
  --border:#243049; --bg-page:#0B1220; --bg-card:#131C2E;
  --table-head:#18233A;
  --bg-card-tint:rgba(19,28,46,.94);
  --bg-field:#0F1930;
  --row-danger-hover:rgba(248,113,113,.22);
  --veil-top:rgba(11,18,32,.94); --veil-mid:rgba(11,18,32,.90); --veil-bot:rgba(11,18,32,.84);
  --air-top:rgba(11,18,32,.80); --air-mid:rgba(11,18,32,.72); --air-bot:rgba(11,18,32,.62);
  --turbine-sky:#0E1B33; --turbine-border:#24365C;
  --shadow-1:0 1px 3px rgba(0,0,0,.45);
  --shadow-2:0 4px 12px rgba(0,0,0,.55);
  --focus-ring:0 0 0 3px rgba(56,189,248,.30);
  --overlay:rgba(0,0,0,.62);
}
/* 夜航：重映射 Gradio 组件变量，使控件随主题变深（不改 ?__theme） */
[data-wd-theme="night"] .gradio-container {
  --background-fill-primary:#0B1220; --background-fill-secondary:#131C2E;
  --block-background-fill:#131C2E; --panel-background-fill:#131C2E;
  --border-color-primary:#243049; --border-color-accent:#243049;
  --block-border-color:#243049; --input-border-color:#243049;
  --body-text-color:#E5EDF7; --block-text-color: #E5EDF7; --block-info-text-color:#A9BBD4;
  --block-label-text-color:#A9BBD4; --block-title-text-color:#E5EDF7;
  --block-label-background-fill:#18233A; --block-label-border-color:#243049;
  --block-title-background-fill:#18233A;
  --border-color-accent:#243049; --background-fill-secondary:#131C2E;
  --input-background-fill:#0F1930; --input-background-fill-focus:#0F1930;
  --input-text-color:#E5EDF7; --placeholder-text-color:#7C8DB0;
  --checkbox-background-color:#0F1930; --table-border-color: #243049;
  --button-secondary-background-fill:#18233A; --button-secondary-background-fill-hover:#1E2B45;
  --button-secondary-text-color:#E5EDF7; --button-primary-background-fill:#0E7490;
  --button-primary-background-fill-hover:#22D3EE; --color-accent:#22D3EE;
  --link-text-color:#38BDF8; --body-background-fill:#0B1220;
  --stat-background-fill:#131C2E; --code-background-fill:#0F1930;
  --prose-text-color:#E5EDF7; --shadow-drop:rgba(0,0,0,.45); --shadow-drop-lg:rgba(0,0,0,.55);
}
[data-wd-theme="night"] .gradio-container .prose,
[data-wd-theme="night"] .gradio-container .prose h1,
[data-wd-theme="night"] .gradio-container .prose h2,
[data-wd-theme="night"] .gradio-container .prose h3 { color:var(--text-1); }
/* 对比度加固：无论 Gradio 深浅模式（.dark）如何叠加，夜航下所有正文面必须浅字深底。
   这些选择器带 !important，防止组件级样式或 Gradio 主题变量把文字打回深色。 */
[data-wd-theme="night"] .gradio-container .prose,
[data-wd-theme="night"] .gradio-container .prose h1,
[data-wd-theme="night"] .gradio-container .prose h2,
[data-wd-theme="night"] .gradio-container .prose h3,
[data-wd-theme="night"] .gradio-container .prose h4,
[data-wd-theme="night"] .gradio-container .prose p,
[data-wd-theme="night"] .gradio-container .prose span,
[data-wd-theme="night"] .gradio-container .html-container,
[data-wd-theme="night"] .gradio-container .html-container div,
[data-wd-theme="night"] .gradio-container .html-container span,
[data-wd-theme="night"] .gradio-container .html-container td,
[data-wd-theme="night"] .gradio-container .html-container th,
[data-wd-theme="night"] .gradio-container .prose li { color:var(--text-1) !important; }
[data-wd-theme="night"] .gradio-container label,
[data-wd-theme="night"] .gradio-container [data-testid="block-label"],
[data-wd-theme="night"] .gradio-container .block-info,
[data-wd-theme="night"] .gradio-container .prose { color:var(--text-1) !important; }
[data-wd-theme="night"] .gradio-container details.wd-sec > summary {
  color:var(--brand-700) !important;
  background:var(--table-head);
}
[data-wd-theme="night"] .gradio-container .wd-empty .wd-empty-title { color:var(--text-1) !important; }
[data-wd-theme="night"] .gradio-container .wd-empty .wd-empty-desc { color:var(--text-3) !important; }
/* 按钮对比度加固：Gradio 按钮文字色有自己的变量链（.dark 类下取深色值），
   仅重映射 --button-secondary-text-color 不够 —— 必须按变体强制。 */
[data-wd-theme="night"] .gradio-container button,
[data-wd-theme="night"] .gradio-container button span { color:var(--text-1) !important; }
[data-wd-theme="night"] .gradio-container button.lg { border:1px solid var(--border) !important; }
[data-wd-theme="night"] .gradio-container button.primary,
[data-wd-theme="night"] .gradio-container button.primary span { color:#FFFFFF !important; }
[data-wd-theme="night"] .gradio-container a { color:var(--brand-500) !important; }
[data-wd-theme="night"] .gradio-container .pagination { color:var(--text-2) !important; }
/* 弹层激活按钮：夜航的 --brand-500 是亮青，必须配深字（白字只有 1.8:1） */
[data-wd-theme="night"] .wd-sp-seg button.wd-active { color:#0B1220 !important; }
/* 标签片兜底：block-label/block-info chip（"图片信息"等）背景必须随主题压深，
   否则与强制浅色的文字冲突（浅蓝底×浅字 ≈ 1:1） */
[data-wd-theme="night"] .gradio-container [data-testid="block-label"],
[data-wd-theme="night"] .gradio-container [data-testid="block-info"],
[data-wd-theme="night"] .gradio-container [class*="block-label"] {
  background:var(--table-head) !important;
  border-color:var(--border) !important;
  color:var(--text-2) !important;
}
[data-wd-theme="night"] .gradio-container [data-testid="block-label"] span,
[data-wd-theme="night"] .gradio-container [data-testid="block-info"] span { color:var(--text-2) !important; }
[data-wd-theme="night"] .wd-workbench-col { border-color:var(--border); }
[data-wd-theme="night"] .wd-turbine-frame { box-shadow:inset 0 0 24px rgba(0,0,0,.5); }
[data-wd-theme="night"] button.wd-btn-danger {
  background:var(--bg-card) !important; color:var(--danger-deep) !important;
  border:1px solid var(--danger) !important;
}
[data-wd-theme="night"] button.wd-btn-danger:hover { background:var(--danger-bg) !important; }

/* ── C 流光 · 玻璃拟态新能源（浅色基底 + 半透明卡片） ── */
[data-wd-theme="glass"] {
  --brand-900:#155E75; --brand-700:#0E7490; --brand-500:#0891B2; --brand-100:rgba(8,145,178,.12);
  --text-1:#0F172A; --text-2:#334155; --text-3:#64748B;
  --border:rgba(15,23,42,.14); --bg-page:#F0FAFC; --bg-card:rgba(255,255,255,.72);
  --table-head:rgba(255,255,255,.6);
  --bg-card-tint:rgba(255,255,255,.66);
  --bg-field:rgba(255,255,255,.85);
  --veil-top:rgba(240,250,252,.55); --veil-mid:rgba(235,248,250,.45); --veil-bot:rgba(235,248,250,.38);
  --turbine-sky:#A5DDF3; --turbine-border:#7FC5E0;
  --shadow-1:0 1px 3px rgba(15,23,42,.08);
  --shadow-2:0 8px 24px rgba(15,23,42,.14);
  --focus-ring:0 0 0 3px rgba(8,145,178,.25);
  --overlay:rgba(15,23,42,.40);
}
/* 极光画在 ::after（z-index -1，位于天空 iframe 之上），否则被背景挡住 */
[data-wd-theme="glass"] body::after {
  background:
    radial-gradient(60% 55% at 12% 8%, rgba(103,232,249,.30), transparent 62%),
    radial-gradient(55% 50% at 88% 14%, rgba(59,130,246,.22), transparent 60%),
    radial-gradient(70% 60% at 50% 96%, rgba(52,211,153,.26), transparent 65%),
    linear-gradient(180deg,var(--air-top),var(--air-mid) 58%,var(--air-bot));
  animation:wd-aurora 26s ease-in-out infinite alternate;
}
@keyframes wd-aurora {
  from { background-position:0% 0%, 100% 0%, 50% 100%, 0 0; }
  to   { background-position:36% 18%, 62% 30%, 38% 66%, 0 0; }
}
[data-wd-theme="glass"] .wd-card,
[data-wd-theme="glass"] .wd-workbench-col,
[data-wd-theme="glass"] .wd-summary,
[data-wd-theme="glass"] details.wd-sec,
[data-wd-theme="glass"] .table-wrap {
  backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
}
/* 弹层/抽屉浮在内容之上，必须近乎不透明，避免背后文字透出串行 */
[data-wd-theme="glass"] .wd-settings-popover,
[data-wd-theme="glass"] .wd-drawer { background:rgba(255,255,255,.96); }
@media (prefers-reduced-motion: reduce) {
  [data-wd-theme="glass"] .wd-card,
  [data-wd-theme="glass"] .wd-workbench-col { backdrop-filter:none; -webkit-backdrop-filter:none; }
}

/* ── D 棱格 · Bento 极简数据风（近白底 + 细边框 + 去阴影） ── */
[data-wd-theme="bento"] {
  --brand-900:#1E3A8A; --brand-700:#1D4ED8; --brand-500:#2563EB; --brand-100:rgba(37,99,235,.08);
  --text-1:#1C1917; --text-2:#57534E; --text-3:#A8A29E;
  --border:#E7E5E4; --bg-page:#FAFAF9; --bg-card:#FFFFFF;
  --table-head:#F5F5F4;
  --bg-card-tint:rgba(255,255,255,.97);
  --bg-field:#FFFFFF;
  --veil-top:rgba(250,250,249,.92); --veil-mid:rgba(250,250,249,.85); --veil-bot:rgba(250,250,249,.78);
  --turbine-sky:#CBE7F5; --turbine-border:#B5D9EC;
  --shadow-1:none; --shadow-2:none;
  --focus-ring:0 0 0 3px rgba(37,99,235,.22);
}
[data-wd-theme="bento"] .wd-card,
[data-wd-theme="bento"] .wd-workbench-col,
[data-wd-theme="bento"] .wd-stat { border-radius:12px; box-shadow:none; }
[data-wd-theme="bento"] .wd-workbench-col { border:1px solid var(--border); }
/* Bento：标题层级加大加粗，数据数字特大号（信息层级优先） */
[data-wd-theme="bento"] .wd-workbench-col > .prose:first-child h3 {
  font-size:calc(20px * var(--wd-fs)); font-weight:800; letter-spacing:-.01em;
}
[data-wd-theme="bento"] .wd-stat .wd-stat-num { font-size:32px; font-weight:800; }
[data-wd-theme="bento"] .wd-summary-title { font-size:calc(18px * var(--wd-fs)); font-weight:700; }

/* ── E 电网 · 工业 HMI（灰蓝面板 + 电力黄主色） ── */
[data-wd-theme="hmi"] {
  --brand-900:#8A6100; --brand-700:#B8860B; --brand-500:#F5A700; --brand-100:rgba(245,167,0,.14);
  --text-1:#1F2A38; --text-2:#3E4C5E; --text-3:#7B8794;
  --border:#C3CFDB; --bg-page:#E8EDF2; --bg-card:#F2F6F9;
  --table-head:#DDE5EC;
  --bg-card-tint:rgba(242,246,249,.96);
  --bg-field:#FFFFFF;
  --veil-top:rgba(232,237,242,.92); --veil-mid:rgba(232,237,242,.86); --veil-bot:rgba(232,237,242,.78);
  --turbine-sky:#9CC8E4; --turbine-border:#7FAECB;
  --focus-ring:0 0 0 3px rgba(245,167,0,.30);
  --overlay:rgba(31,42,56,.45);
}
[data-wd-theme="hmi"] .wd-stat { border-top-color:var(--brand-500); }
[data-wd-theme="hmi"] .wd-stat .wd-stat-num { color:var(--brand-900); }
[data-wd-theme="hmi"] .wd-workbench-col { border:1px solid var(--border); border-radius:6px; }
[data-wd-theme="hmi"] details.wd-sec > summary {
  font-weight:700; letter-spacing:.5px; text-transform:none;
}
/* HMI：状态色与形状双通道（色弱可辨）——高▲ / 中■ / 低● */
[data-wd-theme="hmi"] .wd-badge-danger::before { content:"▲ "; font-size:.82em; }
[data-wd-theme="hmi"] .wd-badge-warn::before   { content:"■ "; font-size:.82em; }
[data-wd-theme="hmi"] .wd-badge-success::before{ content:"● "; font-size:.82em; }
[data-wd-theme="hmi"] .gradio-container button { border-radius:6px; }

/* ── F 深空 HUD · 融合参考1（智慧风电监管平台）+ 参考2（光储能源平台） ──
   参考1：深空海军蓝、面板 L 形角标、青色发光描边、科技感标签；
   参考2：半透明蓝面板、左侧竖条标题、网格底纹、胶囊描边按钮。 */
[data-wd-theme="hud"] {
  --brand-900:#67E8F9; --brand-700:#22D3EE; --brand-500:#06B6D4; --brand-100:rgba(34,211,238,.12);
  --danger:#F87171; --danger-deep:#FCA5A5; --danger-bg:rgba(248,113,113,.12);
  --warn:#FBBF24;   --warn-deep:#FCD34D;   --warn-bg:rgba(251,191,36,.12);
  --success:#34D399;--success-deep:#6EE7B7;--success-bg:rgba(52,211,153,.12);
  --info:#38BDF8;   --info-bg:rgba(56,189,248,.12);
  --text-1:#DCEBFA; --text-2:#9FBEDA; --text-3:#6684A3;
  --border:rgba(103,232,249,.26); --bg-page:#071426; --bg-card:#0C2138;
  --table-head:rgba(18,42,68,.85);
  --bg-card-tint:rgba(12,33,56,.82);
  --bg-field:rgba(7,20,38,.85);
  --row-danger-hover:rgba(248,113,113,.20);
  --veil-top:rgba(7,20,38,.96); --veil-mid:rgba(7,20,38,.93); --veil-bot:rgba(7,20,38,.88);
  --air-top:rgba(7,20,38,.82); --air-mid:rgba(7,20,38,.74); --air-bot:rgba(7,20,38,.64);
  --turbine-sky:#0B1D33; --turbine-border:rgba(103,232,249,.35);
  --shadow-1:0 0 0 1px rgba(103,232,249,.06);
  --shadow-2:0 8px 28px rgba(2,10,22,.6);
  --focus-ring:0 0 0 3px rgba(34,211,238,.28);
  --overlay:rgba(2,10,22,.66);
}
/* 参考2：科技网格底纹（细网格 + 青色光晕），画在天空 iframe 之上 */
[data-wd-theme="hud"] body::after {
  background:
    repeating-linear-gradient(0deg, rgba(103,232,249,.08) 0 1px, transparent 1px 44px),
    repeating-linear-gradient(90deg, rgba(103,232,249,.08) 0 1px, transparent 1px 44px),
    radial-gradient(58% 46% at 14% 6%, rgba(34,211,238,.14), transparent 62%),
    radial-gradient(52% 44% at 88% 92%, rgba(14,116,144,.18), transparent 64%),
    linear-gradient(180deg,var(--air-top),var(--air-mid) 58%,var(--air-bot));
}
/* 参考1：面板 L 形角标（::before 左上 + ::after 右下）与青边半透明面板 */
[data-wd-theme="hud"] .wd-workbench-col {
  position:relative; border:1px solid var(--border);
  background:linear-gradient(158deg, rgba(14,38,64,.88) 0%, rgba(9,25,45,.84) 100%);
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
}
[data-wd-theme="hud"] .wd-workbench-col::before,
[data-wd-theme="hud"] .wd-workbench-col::after {
  content:""; position:absolute; width:16px; height:16px; pointer-events:none;
}
[data-wd-theme="hud"] .wd-workbench-col::before {
  top:0; left:0; border-top:2px solid var(--brand-500); border-left:2px solid var(--brand-500);
}
[data-wd-theme="hud"] .wd-workbench-col::after {
  bottom:0; right:0; border-bottom:2px solid var(--brand-500); border-right:2px solid var(--brand-500);
}
/* 参考2：面板标题左竖条 + 科技字距 + 渐变下划线
   （Gradio 的 h3 在 div.block > … > .prose 深处，故直接命中 h3。
    注意：不可给 h3 加 padding-bottom/margin 等垂直尺寸——中栏标题变高
    会改变 3D iframe 的屏幕几何，触发 Chromium 合成器丢弃 WebGL 层，
    画布内容正确但屏上全黑；竖条与下划线均不占垂直空间。） */
[data-wd-theme="hud"] .wd-workbench-col h3 {
  border-left:3px solid var(--brand-500); padding-left:10px;
  letter-spacing:2px; color:var(--brand-700);
  background:linear-gradient(90deg, rgba(34,211,238,.16), transparent 72%) left bottom / 100% 2px no-repeat;
}
[data-wd-theme="hud"] details.wd-sec > summary {
  letter-spacing:1.5px; border-left:3px solid var(--brand-500); padding-left:10px;
  background:linear-gradient(90deg, rgba(34,211,238,.10), transparent 80%);
}
[data-wd-theme="hud"] .wd-stat { border-top-color:var(--brand-500); }
[data-wd-theme="hud"] .wd-turbine-frame { box-shadow:inset 0 0 30px rgba(2,10,22,.55), 0 0 0 1px rgba(103,232,249,.18); }
[data-wd-theme="hud"] table.wd-table tr:nth-child(even) { background:rgba(18,42,68,.45); }
/* 高风险整行：底色盖过斑马纹（同等特异性靠后者胜）+ 左侧红色警示条 */
[data-wd-theme="hud"] table.wd-table tr.wd-row-danger,
[data-wd-theme="hud"] table.wd-table tr.wd-row-danger:nth-child(even) { background:rgba(248,113,113,.13); }
[data-wd-theme="hud"] table.wd-table tr.wd-row-danger td:first-child { box-shadow:inset 3px 0 0 var(--danger); }
[data-wd-theme="hud"] .gradio-container button.primary {
  background:linear-gradient(135deg, #0E7490, #22D3EE) !important;
  border:1px solid rgba(103,232,249,.6) !important;
  box-shadow:0 0 14px rgba(34,211,238,.40);
}
[data-wd-theme="hud"] .gradio-container button.primary:hover { box-shadow:0 0 20px rgba(34,211,238,.62); }
/* 深色皮肤的对比度加固与夜航同规格 */
[data-wd-theme="hud"] .gradio-container .prose,
[data-wd-theme="hud"] .gradio-container .prose h1,
[data-wd-theme="hud"] .gradio-container .prose h2,
[data-wd-theme="hud"] .gradio-container .prose h3,
[data-wd-theme="hud"] .gradio-container .prose h4,
[data-wd-theme="hud"] .gradio-container .prose p,
[data-wd-theme="hud"] .gradio-container .prose span,
[data-wd-theme="hud"] .gradio-container .html-container,
[data-wd-theme="hud"] .gradio-container .html-container div,
[data-wd-theme="hud"] .gradio-container .html-container span,
[data-wd-theme="hud"] .gradio-container .html-container td,
[data-wd-theme="hud"] .gradio-container .html-container th,
[data-wd-theme="hud"] .gradio-container .prose li { color:var(--text-1) !important; }
[data-wd-theme="hud"] .gradio-container button,
[data-wd-theme="hud"] .gradio-container button span { color:var(--text-1) !important; }
[data-wd-theme="hud"] .gradio-container button.primary,
[data-wd-theme="hud"] .gradio-container button.primary span { color:#FFFFFF !important; }
[data-wd-theme="hud"] .gradio-container button.lg { border:1px solid var(--border) !important; }
[data-wd-theme="hud"] .gradio-container a { color:var(--brand-500) !important; }
[data-wd-theme="hud"] .gradio-container [data-testid="block-label"],
[data-wd-theme="hud"] .gradio-container [data-testid="block-info"],
[data-wd-theme="hud"] .gradio-container [class*="block-label"] {
  background:var(--table-head) !important;
  border-color:var(--border) !important;
  color:var(--text-2) !important;
}
[data-wd-theme="hud"] .gradio-container [data-testid="block-label"] span,
[data-wd-theme="hud"] .gradio-container [data-testid="block-info"] span { color:var(--text-2) !important; }
/* ── 状态强调强化：深底下徽章胶囊更醒目（放在上方 span 强制色规则之后，
      特异性相同时靠后者胜；描边用 inset box-shadow，不增加几何尺寸） ── */
[data-wd-theme="hud"] .gradio-container span.wd-badge-danger,
[data-wd-theme="hud"] span.wd-badge-danger {
  background:rgba(248,113,113,.22) !important;
  color:#FECACA !important;
  box-shadow:inset 0 0 0 1px rgba(248,113,113,.62), 0 0 12px rgba(248,113,113,.16);
}
[data-wd-theme="hud"] .gradio-container span.wd-badge-warn,
[data-wd-theme="hud"] span.wd-badge-warn {
  background:rgba(251,191,36,.18) !important;
  color:#FDE68A !important;
  box-shadow:inset 0 0 0 1px rgba(251,191,36,.52), 0 0 12px rgba(251,191,36,.12);
}
[data-wd-theme="hud"] .gradio-container span.wd-badge-success,
[data-wd-theme="hud"] span.wd-badge-success {
  background:rgba(52,211,153,.18) !important;
  color:#A7F3D0 !important;
  box-shadow:inset 0 0 0 1px rgba(52,211,153,.52), 0 0 12px rgba(52,211,153,.12);
}
[data-wd-theme="hud"] .gradio-container {
  --background-fill-primary:#071426; --background-fill-secondary:#0C2138;
  --block-background-fill:#0C2138; --panel-background-fill:#0C2138;
  --border-color-primary:rgba(103,232,249,.26); --border-color-accent:rgba(103,232,249,.26);
  --block-border-color:rgba(103,232,249,.26); --input-border-color:rgba(103,232,249,.26);
  --body-text-color:#DCEBFA; --block-text-color:#DCEBFA; --block-info-text-color:#9FBEDA;
  --block-label-text-color:#9FBEDA; --block-title-text-color:#DCEBFA;
  --block-label-background-fill:#122A44; --block-label-border-color:rgba(103,232,249,.26);
  --block-title-background-fill:#122A44;
  --input-background-fill:rgba(7,20,38,.85); --input-background-fill-focus:rgba(7,20,38,.85);
  --input-text-color:#DCEBFA; --placeholder-text-color:#6684A3;
  --button-secondary-background-fill:#122A44; --button-secondary-background-fill-hover:#173356;
  --button-secondary-text-color:#DCEBFA;
  --link-text-color:#22D3EE; --body-background-fill:#071426;
  --prose-text-color:#DCEBFA; --shadow-drop:rgba(2,10,22,.5); --shadow-drop-lg:rgba(2,10,22,.6);
}
[data-wd-theme="hud"] .wd-sp-seg button.wd-active { color:#04121F !important; }

/* ── 顶栏用户徽章美化：账号胶囊 + 圆角图标链接（仅 HUD 皮肤；
      padding-top 8→5 抵消胶囊增高，顶栏总高不变，下方布局零位移） ── */
[data-wd-theme="hud"] .wd-user-badge { gap:8px; padding-top:3px; font-size:16px; }
[data-wd-theme="hud"] .wd-user-badge .wd-ub-ic {
  display:inline-block; width:15px; height:15px; flex:none;
}
[data-wd-theme="hud"] .wd-user-badge .wd-ub-chip {
  padding:2px 13px; border-radius:999px;
  background:rgba(14,38,64,.62); border:1px solid rgba(103,232,249,.32);
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  box-shadow:0 0 10px rgba(34,211,238,.12);
}
[data-wd-theme="hud"] .wd-user-badge .wd-ub-chip .wd-ub-ic { color:var(--brand-700); }
[data-wd-theme="hud"] .wd-user-badge .wd-badge {
  display:inline-flex; align-items:center; gap:5px;
  padding:1px 12px; border-radius:999px;
  background:rgba(34,211,238,.12); border:1px solid rgba(103,232,249,.38);
  color:#8DEFFF !important;
}
[data-wd-theme="hud"] .wd-user-badge .wd-badge .wd-ub-ic { width:13px; height:13px; color:#8DEFFF; }
[data-wd-theme="hud"] .wd-user-badge a.wd-ub-link {
  display:inline-flex; align-items:center; gap:6px;
  padding:2px 13px; border-radius:999px;
  background:rgba(14,38,64,.45); border:1px solid rgba(103,232,249,.22);
  text-decoration:none;
  transition:background .18s, border-color .18s, box-shadow .18s;
}
[data-wd-theme="hud"] .wd-user-badge a.wd-ub-link:hover {
  background:rgba(34,211,238,.14); border-color:rgba(103,232,249,.55);
  box-shadow:0 0 12px rgba(34,211,238,.22); text-decoration:none;
}
[data-wd-theme="hud"] .wd-user-badge a.wd-ub-link .wd-ub-ic { color:var(--brand-700); }

/* ── HUD 大屏化：viewer（风机+按钮）留在中栏槽位 = 最初的左中右三栏；
    另有一个纯风景 iframe（脚本创建，body 层 id=wd-bg-viewer，z-index:-2）
    固定铺满全屏当最底层背景，三栏玻璃面板悬浮其上。 */
[data-wd-theme="hud"] body > iframe#wd-bg-viewer {
  position:fixed; inset:0; width:100vw; height:100vh; z-index:-2;
  border:0; display:block; background:var(--turbine-sky); pointer-events:none;
}
/* 中栏槽位：原样承装 viewer iframe（可交互——风机拖拽/滚轮缩放），
   仅加可见描边与内阴影突出轮廓 */
[data-wd-theme="hud"] .wd-turbine-frame {
  border:1px solid rgba(103,232,249,.32);
  box-shadow:inset 0 0 36px rgba(2,10,22,.38);
}
/* 三列统一玻璃面板：对齐新大屏 .sc-panel 质感（仅调透明度与模糊，几何不动）；
   透明度调高，让底层风景背景透出来 */
[data-wd-theme="hud"] .wd-workbench-col {
  background:linear-gradient(158deg, rgba(14,38,64,.34) 0%, rgba(9,25,45,.24) 100%);
  backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
}
/* 空气蒙版减淡：让背景风景透出来（文字对比度由玻璃面板保证） */
[data-wd-theme="hud"] body::after {
  background:
    repeating-linear-gradient(0deg, rgba(103,232,249,.04) 0 1px, transparent 1px 44px),
    repeating-linear-gradient(90deg, rgba(103,232,249,.04) 0 1px, transparent 1px 44px),
    radial-gradient(58% 46% at 14% 6%, rgba(34,211,238,.08), transparent 62%),
    radial-gradient(52% 44% at 88% 92%, rgba(14,116,144,.10), transparent 64%),
    linear-gradient(180deg, rgba(7,20,38,.42), rgba(7,20,38,.32) 58%, rgba(7,20,38,.26));
}
"""


# ══════════════════════════════════════════════════════════
#  HTML 组件模板
# ══════════════════════════════════════════════════════════

def esc(text) -> str:
    """HTML 转义（所有用户/模型可控内容必须经过此函数再入模板）。"""
    return _html.escape(str(text), quote=True)


def esc_js(text) -> str:
    """JS 字符串字面量转义：内容已 HTML 转义后再包一层单引号安全。
    用于 onsubmit="return confirm('...')" 这类内联属性——属性本身由
    esc() 级别的引号包裹，内部只需保证不提前闭合 JS 引号。"""
    s = str(text).replace("\\", "\\\\").replace("'", "\\'")
    s = s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\r", "").replace("\n", " ")
    return f"'{s}'"


def risk_badge(value: str, tone: str = "") -> str:
    """风险徽章：胶囊形，浅色语义底 + 深色文字（文字+颜色双通道）。

    tone: "danger" / "warn" / "success" / "muted"；空串时按 value 自动判断。
    """
    if not value:
        return ""
    if not tone:
        tone = tone_for_value(value)
    return f'<span class="wd-badge wd-badge-{tone}">{esc(value)}</span>'


# 与 formatter.RISK_COLORS 一致的语义映射（展示值，zh/en 都覆盖）
_TONE_BY_VALUE = {
    # 高风险类
    "高": "danger", "High": "danger", "是": "danger", "Yes": "danger",
    "严重": "danger", "Severe": "danger", "紧急": "danger", "Urgent": "danger",
    # 中等
    "中": "warn", "Medium": "warn", "一般": "warn", "Moderate": "warn",
    # 安全类
    "低": "success", "Low": "success", "否": "success", "No": "success",
    "无": "success", "None": "success", "正常": "success", "Normal": "success",
}


def tone_for_value(value: str) -> str:
    return _TONE_BY_VALUE.get(str(value).strip(), "muted")


def status_banner(text: str, kind: str = "info") -> str:
    """状态条。kind: info / success / error / warn"""
    return f'<div class="wd-status wd-status-{esc(kind)}">{text}</div>'


def working_banner(text: str) -> str:
    """等待动效状态条：旋转 spinner + 文案 + 实时已用时计时。

    .wd-elapsed 的秒数由前端每秒心跳脚本刷新（见 app._BADGE_JS 组合脚本），
    首次心跳时写入 data-start 起点。"""
    unit = i18n.t("elapsed_sec_unit")
    return ('<div class="wd-status wd-status-info wd-working">'
            '<span class="wd-spinner" aria-hidden="true"></span>'
            f'{text}<span class="wd-elapsed-wrap">&nbsp;（{i18n.t("elapsed_prefix")} '
            f'<span class="wd-elapsed">0</span> {unit}）</span></div>')


def empty_state(title: str, desc: str = "", icon_svg: str = "") -> str:
    """空状态：图标 + 标题 + 一句说明。"""
    icon = f"<div>{icon_svg}</div>" if icon_svg else ""
    desc_html = f'<div class="wd-empty-desc">{desc}</div>' if desc else ""
    return (
        f'<div class="wd-empty">{icon}'
        f'<div class="wd-empty-title">{title}</div>{desc_html}</div>'
    )


def stat_card(num, label: str, tone: str = "") -> str:
    """统计卡。tone: ""(品牌蓝) / danger / warn / success"""
    tone_cls = f" wd-tone-{tone}" if tone else ""
    return (
        f'<div class="wd-stat{tone_cls}">'
        f'<div class="wd-stat-num">{esc(num)}</div>'
        f'<div class="wd-stat-label">{esc(label)}</div></div>'
    )


def summary_card(items, tone: str = "success", title: str = "") -> str:
    """结论摘要卡（结果页第一层）。

    items: [(label, value_html), ...]；tone: danger / warn / success
    """
    tone_cls = f" wd-tone-{tone}" if tone != "muted" else ""
    title_html = f'<div class="wd-summary-title">{title}</div>' if title else ""
    cells = "".join(
        f'<div class="wd-summary-item"><div class="wd-label">{esc(label)}</div>'
        f'<div class="wd-value">{value}</div></div>'
        for label, value in items
    )
    return (
        f'<div class="wd-summary{tone_cls}">{title_html}'
        f'<div class="wd-summary-grid">{cells}</div></div>'
    )


def risk_banner(text: str) -> str:
    """高风险横幅：浅底 + 左侧色条 + 图标 + 明确文字（不用高饱和红块）。"""
    return (
        '<div class="wd-banner" role="alert">'
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C0392B" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86'
        'a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
        f'<span class="wd-banner-text">{esc(text)}</span></div>'
    )


def sec_details(icon: str, title: str, body: str, open_: bool = False) -> str:
    """折叠报告板块（原生 <details>，无需 JS）。"""
    open_attr = " open" if open_ else ""
    return (
        f'<details class="wd-sec"{open_attr}>'
        f"<summary><span>{icon}</span><span>{esc(title)}</span></summary>"
        f'<div class="wd-sec-body">{body}</div></details>'
    )


def kv_rows(fields) -> str:
    """键值行表格。fields: [(label, value_html, is_risk), ...]"""
    rows = []
    for label, value, is_risk in fields:
        weight = "" if is_risk else "font-weight:500;"
        rows.append(
            "<tr>"
            f'<td class="wd-kv-label">{esc(label)}</td>'
            f'<td class="wd-kv-value" style="{weight}">{value}</td>'
            "</tr>"
        )
    return f'<table class="wd-kv">{"".join(rows)}</table>'


def data_table(headers, rows_html: str) -> str:
    """标准数据表格（浅色 sticky 表头）。rows_html 为已构建的 <tr>... 串。"""
    ths = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return (
        f'<div class="table-wrap"><table class="wd-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{rows_html}</tbody></table></div>"
    )


def mobile_history_card(badge_html: str, image_name: str, meta_html: str,
                        detail_url: str, detail_label: str,
                        danger: bool = False,
                        preview_html: str = "") -> str:
    """移动端历史记录卡片（§7：<768px 替代表格）。preview_html 为抽屉预览触发器。"""
    cls = " wd-row-danger" if danger else ""
    return (
        f'<div class="wd-mcard{cls}">'
        f'<div class="wd-mcard-head">{badge_html}</div>'
        f'<div class="wd-mcard-name">{esc(image_name)}</div>'
        f'<div class="wd-mcard-meta">{meta_html}</div>'
        f'<div class="wd-mcard-actions">'
        f'{preview_html}'
        f'<a class="wd-mcard-primary" href="{esc(detail_url)}">{esc(detail_label)}</a>'
        f"</div></div>"
    )


def page_shell(title: str, body_html: str, lang: str = None) -> str:
    """独立页（FastAPI 渲染）的完整 HTML 外壳：内嵌设计令牌，viewport 齐全。"""
    lang_attr = esc(lang or i18n.LANG)
    return f"""<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
{BASE_CSS}
body {{ margin:0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
