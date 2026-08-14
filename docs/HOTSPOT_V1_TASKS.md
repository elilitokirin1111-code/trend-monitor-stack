# 多平台热点情报中心 V1 任务清单

## 执行规则

- Phase 必须按 0 到 11 顺序执行。
- 每个 Phase 必须先通过测试，再标记完成并提交独立 commit。
- 单元测试可以使用 fixture/fake 隔离外部服务，但演示、验收、报表和生产读取不得把它们冒充实时平台数据。
- 外部平台无法访问时，记录真实失败；缓存结果必须标记 `stale`。
- 每个 Phase 完成时补充“完成项、遗留问题、下一 Phase 计划、测试证据、commit”。

## 总体状态

| Phase | 名称 | 状态 | 完成门禁 |
| --- | --- | --- | --- |
| 0 | 项目审计与架构整理 | 已完成 | 文档校验、基线测试、独立 commit |
| 1 | Collector V2 | 已完成 | 合同/编排/fallback 单元与集成测试 |
| 2 | 四平台数据接入 | 未开始 | 四平台真实契约测试与失败证据 |
| 3 | 30 分钟历史快照 | 未开始 | 迁移、幂等、窗口和恢复测试 |
| 4 | 热点标准化与基础去重 | 未开始 | 规则、Unicode、URL、回放测试 |
| 5 | 跨平台事件聚类 | 未开始 | 候选召回、边界、规模测试 |
| 6 | 趋势生命周期引擎 | 未开始 | 状态机、配置、时间序列测试 |
| 7 | AI 分类与酒旅相关性 | 未开始 | 结构化输出、降级、评测集测试 |
| 8 | 热点 Dashboard | 未开始 | API、组件、构建、端到端测试 |
| 9 | 日报/周报系统 | 未开始 | 窗口、模板、幂等、快照测试 |
| 10 | 飞书报告推送 | 未开始 | 签名、分片、重试、幂等测试 |
| 11 | 运行稳定性和监控 | 未开始 | 故障注入、告警、恢复、负载测试 |

## Phase 0：项目审计与架构整理

### 工作项

- [x] 确认目标目录原始状态：仅 `bin/autocli.exe`，无业务源码和 Git 仓库。
- [x] 获取并固定 HotPush 上游基线及 commit。
- [x] 使用代码知识图谱审计 HotPush 的结构、入口、依赖、路由和调用热点。
- [x] 审计数据库表和快照实现。
- [x] 审计现有 API。
- [x] 审计 APScheduler 任务和默认抓取频率。
- [x] 审计飞书 Webhook 推送实现。
- [x] 审计 HotPush、NewsNow、DailyHotApi、OpenCLI、TrendRadar、MediaCrawler 许可证边界。
- [x] 形成保留、重构、新增模块清单。
- [x] 创建 `docs/HOTSPOT_V1_ARCHITECTURE.md`。
- [x] 创建 `THIRD_PARTY.md`。
- [x] 运行后端基线测试。
- [x] 运行前端依赖安装与生产构建。
- [x] 检查文档链接、许可证声明和 Git diff。
- [x] 填写测试证据、遗留问题和 commit。

### 完成项

- HotPush 已作为 `hotspot-v1` 分支的上游历史基线，而不是无来源复制。
- Collector/Provider/Raw/派生层边界和 stale/fallback 规则已确定。
- 目标数据模型、API 命名空间、Scheduler 拆分、AI 边界和飞书演进方案已确定。
- GPL 与非商业许可证代码被明确排除在商业仓库之外。
- Phase 0 后续修补已清除前端 6 个依赖漏洞和后端 6 条弃用警告，并将未核验工具二进制排除出 Git。

### 遗留问题

- `bin/autocli.exe` 仍为未跟踪文件；已确认它与 `nashsu/AutoCLI` v0.3.8 Windows 官方发布包内文件一致，SHA-256 为 `F1BF52BD7AEA43FBC984F6CAEEDA3496B3CC2E518510E7F3F668BFE477F89758`。它不是当前 OpenCLI 版本；Apache LICENSE/NOTICE 和升级/替换方案落实前不得纳入发行包。
- NewsNow/DailyHotApi 的线上服务稳定性、限流和响应合同需在 Phase 2 以真实调用验证。
- 小红书公开热榜 Provider 尚未确认，不能承诺实时可用。
- 平台条款、账号授权、个人信息和商业采集边界需要上线前的合规复核。

### 测试证据

- `uv run --with-requirements requirements.txt pytest -q`：44 passed，6 warnings。
- `npm ci`：依赖安装成功；审计发现 6 个漏洞，已列为遗留问题。
- `npm run build`：Vite 生产构建成功，58 modules transformed。
- `git diff --check`：通过。
- OpenCLI/AutoCLI 工件核验：本地 `autocli 0.3.8` 与 `nashsu/AutoCLI` v0.3.8 Windows 官方发布包内 SHA-256 一致。
- Phase 0 修补复测：`pytest -W error::DeprecationWarning` 为 44 passed；`npm audit` 为 0 vulnerabilities；Vite 8.2.1 生产构建通过。

### 下一 Phase 计划

Phase 1 只实现 Collector V2，不接四平台生产 Provider：

- 新增领域枚举和 Collector/Provider 合同。
- 新增 Provider registry、fallback policy、超时和错误分类。
- 新增 freshness/stale 结果语义和运行记录接口。
- 为 success/partial/failure/fallback/stale/真实空榜编写测试。
- 不修改 Dashboard、报告或飞书模板。

### Commit

本文件所在的 `docs(phase-0): audit HotPush baseline and define hotspot V1 architecture` 独立提交。

## Phase 1：Collector V2

- [x] 定义 `Platform`、`CollectRequest`、`ProviderResult`、`CollectorResult`。
- [x] 定义 `HotspotProvider` 协议和 health contract。
- [x] 实现 Provider registry 与按平台配置的优先级。
- [x] 实现超时、错误分类、有限重试和 fallback。
- [x] 实现 fresh/stale 读取规则，禁止伪造实时数据。
- [x] 定义原始数据写入端口，不在 Collector 内实现业务聚类。
- [x] 添加配置模型和后台配置兼容入口。
- [x] 完成单元/集成测试、任务文档更新和独立 commit。

### 完成项

- 四个平台已成为独立业务枚举，Provider ID 不再冒充平台。
- Provider 注册表按配置顺序解析并验证平台能力，重复、缺失或不支持的 Provider 会形成明确配置失败。
- Collector 实现逐 Provider 有界重试、超时隔离、错误分类和顺序 fallback。
- fresh success 立即结束；fresh partial 仅在没有完整成功时使用；真实空榜 success 不触发 fallback。
- 实时 Provider 全部失败后，只有显式允许且读取端口返回 `stale` 时才提供旧数据，并写入 `all_providers_failed` 原因。
- 每次 Provider 尝试保留完整 `ProviderResult`、原始响应和错误；成功写入失败会向调用者传播，不会虚报采集成功。
- Collector 只依赖 `RawCollectionWriter` 和 `StaleResultReader` 端口，未耦合数据库、标准化、聚类、报告或推送。
- 后台通用 settings API 可承载 Provider 顺序、超时、0–3 次重试和 stale 策略；默认 Provider 列表保持为空。

### 遗留问题

- Phase 1 只定义写入/读取端口，数据库实现和 30 分钟快照留在 Phase 3。
- 没有生产 Provider 被注册；四平台真实可用性必须在 Phase 2 验证后才能配置。
- Provider 速率限制和认证错误的具体映射由各 Phase 2 adapter 负责。
- Collector 尚未接入 Scheduler 或公开 API，避免在真实 Provider 和持久化实现完成前暴露半成品生产链路。

### 测试证据

- `pytest -W error::DeprecationWarning`：66 passed，其中 Collector V2 新增 22 项领域、配置、registry 和编排测试。
- 覆盖 success、partial、failed、timeout、retry、fallback、stale、禁用 stale、真实空榜、Provider 身份错误、无配置及持久化失败。
- `ruff check`：新增 Collector V2 源码和测试全部通过。
- `ruff format --check`：13 个新增/相关文件均已格式化。
- `python -m compileall`：新增模块全部通过。

### 下一 Phase 计划

Phase 2 仅做四平台 Provider 接入和真实合同验证：

- 分别实现 NewsNow、DailyHotApi 和隔离的 OpenCLI adapter。
- 为每个 Provider 保存真实响应契约、时间、状态、原始载荷和失败证据。
- 基于真实结果确定 douyin/weibo/bilibili/xiaohongshu 的 Provider 顺序；不可用平台保持明确失败。
- 增加 HTTP 超时、限流、认证失效、响应漂移、真实空榜和 fallback 契约测试。
- 不提前创建快照表、聚类、Dashboard 或报告系统。

### Commit

本文件所在的 `feat(phase-1): add collector v2 provider contracts and fallback` 独立提交。

## Phase 2：四平台数据接入

- [ ] 接入 NewsNow Provider。
- [ ] 接入 DailyHotApi Provider。
- [ ] 接入 OpenCLI 进程隔离 Provider，仅用于需要登录态或特殊平台的备用链路。
- [ ] 为 douyin/weibo/bilibili/xiaohongshu 配置可替换 Provider 链。
- [ ] 保存每个平台真实响应和失败状态证据。
- [ ] 验证空榜、限流、登录过期、响应变更和 fallback。
- [ ] 完成契约/集成测试、任务文档更新和独立 commit。

## Phase 3：30 分钟历史快照

- [ ] 引入版本化数据库迁移。
- [ ] 新增采集运行、Provider 尝试、原始载荷、原始热点、快照及成员表。
- [ ] 默认采集间隔设为 30 分钟并允许后台配置。
- [ ] 实现窗口幂等、多实例锁、misfire/coalesce。
- [ ] 保证所有原始数据 append-only 保存。
- [ ] 实现 stale 快照读取语义。
- [ ] 完成迁移/幂等/恢复测试、任务文档更新和独立 commit。

## Phase 4：热点标准化与基础去重

- [ ] 实现 Unicode、空白、标点和标题规范化。
- [ ] 实现 canonical URL。
- [ ] 实现热度单位和平台时间解析。
- [ ] 实现外部 ID、URL、严格标题指纹去重。
- [ ] 保存规则版本与匹配证据。
- [ ] 完成边界/回放测试、任务文档更新和独立 commit。

## Phase 5：跨平台事件聚类

- [ ] 实现时间窗、实体/关键词、n-gram/MinHash 或 ANN 候选召回。
- [ ] 禁止全量 LLM 两两比较并加入规模保护测试。
- [ ] 实现确定性相似度与配置化阈值。
- [ ] 仅对边界候选调用 AI 语义判断。
- [ ] 保存事件成员、匹配证据和算法版本。
- [ ] 完成质量/规模/回放测试、任务文档更新和独立 commit。

## Phase 6：趋势生命周期引擎

- [ ] 实现 `emerging/rising/peaking/declining/dormant/recurrent` 状态机。
- [ ] 实现速度、加速度、持续度和跨平台覆盖特征。
- [ ] 实现配置化窗口、阈值、权重和衰减。
- [ ] stale 数据不得制造实时上升信号。
- [ ] 完成状态机/配置/时间序列测试、任务文档更新和独立 commit。

## Phase 7：AI 分类与酒旅相关性

- [ ] 定义结构化分类输出 schema。
- [ ] 实现主题分类、酒旅相关性、理由与摘要。
- [ ] 记录模型、提示词版本、输入证据、成本和耗时。
- [ ] 实现超时、无 Key、非法输出和模型失败降级。
- [ ] 建立人工标注评测集，不用 AI 自评代替验收。
- [ ] 完成 schema/降级/评测测试、任务文档更新和独立 commit。

## Phase 8：热点 Dashboard

- [ ] 新增 V1 事件、趋势、平台、freshness API。
- [ ] 展示实时/陈旧/失败状态和数据年龄。
- [ ] 展示事件成员与原始证据链接。
- [ ] 展示趋势生命周期、酒旅相关性和筛选。
- [ ] 增加采集健康和 Provider fallback 可见性。
- [ ] 完成 API/组件/构建/E2E 测试、任务文档更新和独立 commit。

## Phase 9：日报/周报系统

- [ ] 定义日报/周报时间窗和版本。
- [ ] 基于事件与趋势生成报告，不直接读取 Provider 响应。
- [ ] 实现幂等生成、重跑和审计来源。
- [ ] 明确标记 stale、缺失平台和数据不完整。
- [ ] 完成窗口/模板/快照测试、任务文档更新和独立 commit。

## Phase 10：飞书报告推送

- [ ] 将 `FeishuPusher` 升级为报告投递适配器。
- [ ] 支持签名、凭据脱敏、超时、重试和指数退避。
- [ ] 支持长度分片和飞书业务码校验。
- [ ] 实现投递幂等、历史、重放和失败告警。
- [ ] 完成签名/分片/重试/幂等测试、任务文档更新和独立 commit。

## Phase 11：运行稳定性和监控

- [ ] 建立结构化日志、指标、trace/correlation ID。
- [ ] 监控 Provider 成功率、延迟、空榜、stale 年龄和 fallback 比率。
- [ ] 监控队列积压、聚类耗时、AI 失败、报告和投递状态。
- [ ] 实现健康检查、就绪检查和告警规则。
- [ ] 执行故障注入、恢复、迁移回滚、备份恢复和负载测试。
- [ ] 完成运行手册、最终任务文档更新和独立 commit。
