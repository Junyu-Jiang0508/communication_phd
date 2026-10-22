# Communication PhD Program Explorer — 详细计划

> 参考对象：<https://political-science-program-explorer.vw9pwn.chatgpt.site/>（Political Science Program Explorer）。
> 本文档记录对原站底层逻辑的拆解、新站（Communication 版）的改进设计、数据管线、技术架构与部署方案。

## 0. 一句话目标

给准备申请美国 Communication / Media PhD 的人一个"先写研究兴趣、再找导师与项目"的工具：
浏览器本地语义匹配 + 可解释的多维标签 + 项目层面的汇总，比原站更准、更可解释、更适合做申请清单。

目标用户：Communication 方向的博士申请者（含中文母语申请者），在笔记本上、写 SoP 的同时使用。

## 1. 原站底层逻辑拆解（爬取 + 反编译 bundle 的结果）

### 1.1 技术栈
- React 19 + 自研 RSC 式框架（`vinext`，ChatGPT 站点生成器），Vite/Rolldown 打包，Tailwind v4 基础层 + 手写 CSS。
- 字体：预载 Geist/Geist Mono，但正文实际用 Arial，标题 Georgia（字体资源浪费）。
- 托管在 Cloudflare 后面，所有数据以 JS bundle / 静态 JSON / 二进制形式随页面下发，没有后端 API。

### 1.2 页面与信息架构（3 个路由）
| 路由 | 内容 | 关键交互 |
|---|---|---|
| `/` Matching | 文本框输入研究描述 → "Find semantic matches" | 浏览器本地跑 embedding；结果卡片（分数 + 姓名 + 学校）→ 弹窗看 profile |
| `/departments` | 左侧 Leaflet 地图（OSM 瓦片）或列表；右侧选中学校的 faculty 名册 | 学校卡片带 U.S. News 排名（National 2027 / Political Science 2025）、院系目录外链 |
| `/faculty` | 5 个"lens"标签页（Research Topics / Units of Analysis / Methods / Data Source / Regional Focus）+ 搜索 + 标签下拉 + 学校下拉 + "Primary labels only" | 每次显示 60 条，Load more；卡片显示该 lens 下的标签，★ 为 primary |

### 1.3 数据模型
- 50 所大学（`universities[]`：name, rank, usNewsProgramRank(+tied, year), usNewsNationalRank(+tied, year), city, state, latitude, longitude, accent 色），学校 favicon 存 `/schools/*.ico|png`。
- 1609 条 faculty（`faculty[]`：university, name, title, academicRank ∈ {Professor 931, Associate 370, Assistant 308}, researchDivisions[]（系网站的 subfield）, departmentProfileUrl, personalUrl, directoryUrl），头像本地化到 `/faculty/profiles/<school>--<name>.jpg`（43 校有图）。
- LLM 生成标签（`generated-faculty-labels`，1 MB）：每人 `summary`（一句话研究概述）、`confidence`、`labels{substantive, setting, method, data, geographic_scope}`，每个标签 `{code, primary, sources[department_profile|personal_site|publications]}`。5 维共 10+8+10+4+9 = 41 个标签码。

### 1.4 语义匹配算法（核心逻辑）
1. 页面按需 `import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.0')`。
2. 加载 `/search/search_manifest.json`：model = `Xenova/bge-small-en-v1.5`，dimensions = 384，vectorCount = 1609，quantizationScale = 127，queryPrefix = "Represent this sentence for searching relevant passages: "。
3. `pipeline('feature-extraction', model, {dtype:'q8'})`（约 34 MB，一次性下载，浏览器 Cache API 缓存），`pooling:'cls', normalize:true`。
4. faculty 向量离线算好、量化为 int8 存 `/search/faculty_vectors.i8.bin`（1609×384 字节 = 617,856 B），`faculty_index.json` 记录行与人名对应（1555 人有向量）。
5. 匹配 = 查询向量 · int8 向量 / 127 → 余弦相似度 → ×100 取整为 "strength"；阈值 35/100；按分数排序；每次显示 50。
6. "严格标签过滤"：用正则在查询文本里探测地区/方法关键词（China、quantitative、NLP、LLM、experiments、survey、formal theory、networks、qualitative…），命中则要求候选人在对应维度拥有相应标签码，否则直接剔除。
7. 隐私：查询不上传；全部在浏览器完成。

### 1.5 原站的问题（我们要改的地方）
- **只有 faculty 排名，没有项目层面的判断**：申请者选的是项目，需要"一个系里有 ≥2–3 位潜在导师"。
- **硬过滤太脆**：提到 "China" 就把没有 R_CHINA 标签的人全删掉；标签是 LLM 生成的，漏标就被误杀。
- **不可解释**："Semantic match across public research material" 一句话，不说为什么匹配。
- **纯余弦分数**：对长文本 SoP 与一句话 summary 的分布不一致；没有关键词/标签层面的信号补充。
- **没有收藏/导出**，无法做申请清单。
- **无深链 / 无静态 profile 页**：faculty 只在弹窗里，不能分享。
- **UI 是"奶油底 + 衬线标题 + 森林绿"的生成式默认风格**，lens 用下拉框而非 facet，移动端把 field tags 直接隐藏。
- 字体预载但未使用；首屏 2 MB 数据 bundle 同步加载（labels 1 MB + photos map 1 MB）。
- 没有深色模式；没有中文。

## 2. 新站：逻辑层面的改进

1. **混合排序（Hybrid ranking）**：`score = 0.75·cosine + 0.25·lexical`，lexical 为查询词与"summary + 标签文本 + 研究领域"的 BM25 风格重合度；两者都归一到 0–1。阈值可调（默认 0.35 余弦）。
2. **可解释匹配**：每张结果卡显示"为什么匹配"：重合的标签（按维度着色）、summary、命中的关键词高亮。
3. **项目层面汇总（Program fit）**：按学校聚合，`fit = mean(top-3 faculty score)`，并显示 ≥ 阈值的匹配人数；视图可在 "Faculty" / "Programs" 间切换。
4. **软过滤 + 可编辑 chips**：从文本里自动探测地区/方法/主题，作为"建议过滤"展示，默认只做加权（+0.05），用户点一下才变成硬过滤；另有 rank / university / lens 过滤。
5. **收藏清单（Shortlist）**：localStorage；可导出 CSV / Markdown（姓名、学校、系、职称、profile 链接、备注列），作为申请追踪表。
6. **静态可分享页面**：`/programs/<slug>/`、`/faculty/<slug>/`（Astro 预渲染），弹窗改为侧边抽屉 + 深链。
7. **数据来源与时效**：每条记录标注来源 URL、抓取日期；About 页说明标签方法与局限；提供"报告错误"入口（GitHub issue）。
8. **模型加载体验**：显示下载进度（signal-bars 动画）；HF 主站失败自动切换 `hf-mirror.com`（国内可用）；模型文件由浏览器 Cache API 缓存。
9. **双语 UI**：EN / 中文切换（界面文案、标签名、维度说明），默认英文。
10. **性能**：faculty 数据按页面需要拆分加载（index 列表 / 标签 / 向量分离）；头像统一为 96px WebP 缩略图并 lazy-load。

## 3. 数据管线（pipeline/）

```
ShanghaiRanking 2025 GRAS Communication (US, 79 校)  ┐
NCA Doctoral Program Guide (88 条博士项目)            ┼→ data/programs_seed.json (73 候选校)
人工筛选（排除无 PhD / 分校）                          ┘
        │  Workflow 1: discover（每校一个 agent：核实 PhD 项目、在册系所、faculty 目录 URL、坐标、域名）
        ▼
data/programs_discovered.json → data/programs.json（最终 ≈50 校）
        │  Workflow 2: scrape（每校一个 agent：抓目录 + 每位 faculty 的 profile 文本，输出 data/raw/<slug>.json，schema 校验）
        ▼
data/raw/*.json  （name, title, rank, department, profile_url, personal_url, photo_url, research_areas[], bio）
        │  Workflow 3: label（每校一个 agent：按 pipeline/taxonomy.json 打 5 维标签 + primary + summary + confidence）
        ▼
data/labels/*.json
        │  pipeline/build.py：合并、去重、职称归一、头像下载缩略图、favicon、
        │  sentence-transformers(BAAI/bge-small-en-v1.5, CLS, normalize) → int8 → public/search/*
        ▼
src/data/*.json + public/search/{manifest.json, index.json, vectors.i8.bin} + public/faculty/*.webp
```

质量闸门：
- raw：`pipeline/validate_raw.py`（必填字段、rank 枚举、URL 绝对路径、去重、非 tenure-line 职称警告）。
- labels：每个标签码必须在 taxonomy 中；每人每维 ≤ 4 个标签、≥ 1 个 primary（topic 维）；summary ≤ 200 字符。
- 抽样复核：Workflow 3 之后随机抽 5% 由独立 agent 对照 profile 页复核标签。

标签体系（`pipeline/taxonomy.json`）：topic 19 / approach 12 / data 7 / setting 10 / region 9，共 57 个码，Communication 领域专用（political comm、journalism、misinfo、platforms & AI、media effects、health、science/environment、interpersonal、organizational、strategic/PR/ad、critical-cultural、rhetoric、industries/policy、global/intercultural、entertainment/games、history/theory、HCI/CMC、language & interaction、children/family media）。

## 4. 信息架构（新站路由）

| 路由 | 作用 |
|---|---|
| `/` | Match：输入研究描述 → faculty / programs 两种结果视图；建议过滤 chips；解释卡 |
| `/programs/` | 地图 + 列表；选中学校 → 项目信息（PhD 页面、ShanghaiRanking、NCA 领域、在册系所）+ 名册 |
| `/programs/<slug>/` | 静态项目页（可分享） |
| `/faculty/` | 目录：左侧 facet（5 维 + rank + 学校，带计数），搜索，排序；卡片 + 侧边抽屉 |
| `/faculty/<slug>/` | 静态 faculty 页 |
| `/shortlist/` | 收藏清单 + 导出 |
| `/about/` | 方法、数据来源、隐私、局限、更新日期、报告错误 |

## 5. 设计方向（视觉世界）

- 模式：Operate 为主（搜索、筛选、比较），首页带一个 Persuade 式入口（匹配器本身就是产品）。
- 世界：**广播/信号的图形传统**——SMPTE 彩条（test card）作为唯一的"高声量"签名：站标是 6 色彩条，5 个标签维度各占一色（topic 黄、approach 青、data 绿、setting 品红、region 蓝），匹配分数以"信号强度"条呈现；模型下载进度条就是彩条逐格点亮。其余界面克制：浅色为灰白纸面 + 石墨墨色，深色为深石板；一个动作色（信号蓝）。
- 字体：Bricolage Grotesque（标题，自带宽度轴，有表情）+ Schibsted Grotesk（正文/界面，报业出身的 grotesk），自托管 woff2（避免 Google Fonts 在国内不可达）。数字用 tabular-nums。
- 布局：首页左右两栏，左栏输入与控制粘性固定，右栏结果流；目录页 facet 侧栏；项目页地图/名册并列。移动端单栏，facet 折叠成底部抽屉。
- 拒绝：eyebrow 小标签、奶油底 + 衬线、卡片堆砌、emoji 图标、箭头后缀。

## 6. 技术架构

- Astro 5（静态输出，`base:/communication_phd`），无 React：交互用原生 TS 模块（islands 通过 `<script>`）。
- 语义匹配：`@huggingface/transformers@4.x`（jsDelivr CDN，动态 import），`Xenova/bge-small-en-v1.5` q8，CLS pooling + normalize，与离线向量同模型同 pooling。
- 地图：Leaflet 1.9 + CARTO light/dark 瓦片（随主题切换）。
- 数据：`src/data/*.json` 编译期注入（Astro `import`），大数据（labels/vectors）放 `public/` 运行时 fetch。
- 主题：CSS 自定义属性，`prefers-color-scheme` + 手动切换（localStorage）。
- 无依赖的 BM25-lite 与过滤逻辑放 `src/lib/`。

## 7. 部署（沿用 junyuj.com 的推送逻辑）

- GitHub 仓库 `Junyu-Jiang0508/communication_phd`（public），`main` 分支。
- `.github/workflows/deploy.yml`：push → `npm ci` → `npm run build` → `actions/upload-pages-artifact` → `actions/deploy-pages`（与 My-Web-V2 相同）。
- 站点地址：`https://junyu-jiang0508.github.io/communication_phd/`；如需挂到自定义域（如 `comm.junyuj.com`），在 Cloudflare/DNS 加 CNAME 并在 `public/CNAME` 写域名、`astro.config.mjs` 去掉 `base`。
- 数据更新：重跑 pipeline → commit `data/` 与 `public/search/` → push 即发布。

## 8. 里程碑

1. 拆解原站 + 计划（本文档）✅
2. 候选校名单（73）→ Workflow 1 discover → 最终名单
3. Workflow 2 scrape → raw 校验
4. Workflow 3 label → 抽样复核
5. build.py：头像、favicon、向量
6. 站点：设计系统 → 四个主页面 → 静态详情页 → 收藏/导出 → 双语
7. 本地构建 + 截图自检（桌面/移动、浅色/深色）
8. 推送到 GitHub → Actions 部署 → 线上验证

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 系网站反爬 / JS 渲染 / 分页 | fetch helper 自动回退 headless Chromium；agent 逐校适配；失败校记录在 notes 中人工补 |
| 头像版权 | 只存 96px 缩略图并标明来源；提供 `--no-photos` 构建选项 |
| 标签准确率 | 来源标注 + primary 仅在证据明确时 + 抽样复核 + 前端标注"解释性标签，非完整画像" |
| 模型在国内下载失败 | hf-mirror 自动回退；提示仅需一次 34 MB |
| 名单争议 | About 页说明入选规则（ShanghaiRanking 2025 Communication 美国前 200 + NCA 指南），欢迎 issue 补充 |
