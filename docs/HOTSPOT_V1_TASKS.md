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
| 2 | 四平台数据接入 | 已完成（外部可用性受限） | 四平台真实契约测试与失败证据 |
| 3 | 30 分钟历史快照 | 已完成 | 迁移、幂等、窗口和恢复测试 |
| 4 | 热点标准化与基础去重 | 已完成 | 规则、Unicode、URL、回放测试 |
| 5 | 跨平台事件聚类 | 已完成 | 158 tests + 有界候选规模保护 |
| 6 | 趋势生命周期引擎 | 已完成 | 179 tests + freshness/失败水位保护 |
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

- [x] 接入 NewsNow Provider。
- [x] 接入 DailyHotApi Provider。
- [x] 接入 OpenCLI 进程隔离 Provider，仅用于需要登录态或特殊平台的备用链路。
- [x] 为 douyin/weibo/bilibili/xiaohongshu 配置可替换 Provider 链。
- [x] 保存每个平台真实响应和失败状态证据。
- [x] 验证空榜、限流、登录过期、响应变更和 fallback。
- [x] 完成契约/集成测试、任务文档更新和独立 commit。

### 完成项

- NewsNow 与 DailyHotApi 以原创 HTTP adapter 接入 douyin、weibo、bilibili；上游源码、selector 和 fixture 未复制进仓库。
- OpenCLI 以无 shell 的子进程参数向量接入 xiaohongshu feed；Collector 超时取消时会终止子进程，浏览器 cookie、token 和登录数据不写业务日志。
- 默认链为前三平台 `newsnow -> dailyhotapi`、小红书 `opencli`；现有后台 settings 可以替换 Provider 顺序、两个 HTTP 基地址、OpenCLI 路径和 limit。
- NewsNow 因 `status=success` 仍可能命中 interval cache，默认保守标记 `stale`；只有明确关闭缓存的自建实例才能通过配置声明 fresh。
- DailyHotApi `fromCache=true` 映射为 `stale`；合法空数组是实时空榜，缺少数组或 schema 漂移是失败。
- HTTP 401、403、429、5xx、网络失败、无效 JSON、部分非法条目、OpenCLI 登录失效和 Browser Bridge 不可用均有独立分类与测试。
- 成功、partial 和失败结果均保留可用的原始响应；真实验证工具仅输出长度、SHA-256 和状态，不输出热点标题或敏感载荷。

### 遗留问题

- 2026-08-14 真实探测中，NewsNow 公共实例对当前出口返回 Cloudflare HTTP 403；DailyHotApi 公共 hostname 无法解析。
- 未修改的 DailyHotApi 本机上游副本可启动，但 douyin、weibo、bilibili 路由访问各平台时均返回 HTTP 502。
- 当前 OpenCLI 1.8.6 可执行，但 Chrome Browser Bridge 扩展未连接；小红书返回明确配置失败，未采到 live item。
- 因四个平台本次都没有取得可证明的 live 数据，Phase 2 不提供演示榜单。生产部署前需要可用的自建 HTTP Provider 和已授权的 OpenCLI 浏览器会话。
- Phase 2 仍未接数据库、Scheduler 或 API；这是 Phase 3 持久化门禁，不应在此阶段绕过。

### 测试证据

- `pytest -W error::DeprecationWarning`：89 passed；Phase 2 新增 23 项 Provider/配置/fallback 测试。
- 覆盖 fresh/stale、真实空榜、partial、响应漂移、401/403/429/5xx、网络失败、fallback、登录失效、Bridge 失联和子进程取消清理。
- `ruff check` 与 `ruff format --check`：Phase 2 源码、工具和测试通过。
- `python -m compileall`、前端 Vite 8.2.1 生产构建通过；`npm audit` 为 0 vulnerabilities。
- 真实调用与 payload hash：`docs/evidence/PHASE_2_PROVIDER_VALIDATION_2026-08-14.md`。

### 下一 Phase 计划

Phase 3 只实现 30 分钟历史快照和原始数据持久化：

- 引入版本化数据库迁移和 append-only 原始载荷/原始热点表。
- 增加采集运行、Provider 尝试、快照和快照成员表，原始与聚合数据继续分离。
- 实现 30 分钟后台配置、窗口幂等键、多实例锁及 misfire/coalesce。
- 将 Phase 2 Provider/Collector 接入持久化端口和 Scheduler，但不提前做标准化或聚类。
- 完成迁移、幂等、窗口、并发和恢复测试后再提交。

### Commit

本节随 `feat(phase-2): integrate replaceable live hotspot providers` 独立提交。

## Phase 3：30 分钟历史快照

- [x] 引入版本化数据库迁移。
- [x] 新增采集运行、Provider 尝试、原始载荷、原始热点、快照及成员表。
- [x] 默认采集间隔设为 30 分钟并允许后台配置。
- [x] 实现窗口幂等、多实例锁、misfire/coalesce。
- [x] 保证所有原始数据 append-only 保存。
- [x] 实现 stale 快照读取语义。
- [x] 完成迁移/幂等/恢复测试、任务文档更新和独立 commit。

### 完成项

- 新增 SQLite/MySQL 双方言、带 SHA-256 漂移检测的 `hotspot_schema_migrations` 迁移体系；V1 新表使用 `hotspot_*` 前缀，与 HotPush 旧表隔离。
- 新增采集运行、Provider 尝试、原始 payload、原始热点、历史快照、快照成员和窗口锁表；运行、尝试和原始证据只追加，不受旧快照 7 天清理任务影响。
- 原始响应按字节保存并记录 SHA-256；未获选 Provider 的尝试、错误和可用条目同样保存，便于回放与审计。
- 30 分钟窗口按 UTC 半开区间确定；`platform + window_start` 唯一约束、数据库锁和写入时二次检查共同保证多实例幂等。
- Collector V2 已接入独立 `hotspot_collect_v2` APScheduler 任务，默认 30 分钟，设置键为 `hotspot_collection_interval_minutes`，后台配置合法范围为 1–1440 分钟。
- 定时与手动触发共用 `HotspotCollectionService.collect_all`；任务启用 `max_instances=1`、`coalesce=True` 和有限 misfire grace time。
- 实时失败会保存运行/尝试/原始错误，不生成快照；stale Provider 或历史快照回退会明确标记 `stale`，且不会制造新的实时窗口观测。
- 最新历史快照实现 `StaleResultReader`，只有含真实成员的既有快照可作为回退数据。
- 修补 Phase 0 升级 Vite 8 后遗漏的 CI 运行时：GitHub Actions 前端门禁由不兼容的 Node 18 升级到 Node 22。

### 遗留问题

- MySQL 迁移 SQL 已实现并通过静态/编译检查，但当前开发环境没有独立 MySQL 测试实例；部署前仍需在与生产一致的 MySQL 版本执行迁移演练和备份恢复验证。
- 四平台公网 Provider 仍受 Phase 2 记录的外部 403、DNS、502 和 Browser Bridge 状态限制；Scheduler 会记录真实失败，不会补入演示数据。
- 本阶段只保存 Raw 与 Snapshot；尚未生成规范化条目、单平台去重或跨平台事件。
- 原始层按产品原则永久保留；压缩、对象存储归档与容量告警留到 Phase 11，但不得静默删除原始证据。

### 测试证据

- `pytest -W error::DeprecationWarning`：105 passed；Phase 3 新增 16 项窗口、迁移、仓储、锁、恢复、服务和 Scheduler 测试。
- 覆盖迁移幂等与失败恢复、同 run/同窗口幂等、原始字节与哈希、失败无快照、stale 不造新快照、历史 stale 读取、锁所有权/过期恢复、已有窗口跳过、30 分钟单实例任务和手动同入口。
- `ruff check` 与 `ruff format --check`：Collector V2、Provider、Phase 3 仓储/服务及全部热点测试通过。
- `python -m compileall`：后端应用通过；前端生产构建和依赖审计通过。
- GitHub Actions：后端测试与 Node 22 前端构建门禁通过。

### 下一 Phase 计划

Phase 4 只实现热点标准化与基础去重：

- 新增版本化派生表，保存规范化规则版本、输入 raw ID 和失败原因。
- 实现 Unicode、空白、标点、标题和 URL 的确定性规范化。
- 实现平台热度单位与时间字段解析，解析失败不删除原始记录。
- 按外部 ID、canonical URL 和严格标题指纹做基础去重并保存匹配证据。
- 使用 Phase 3 原始记录回放测试；不提前实现跨平台事件聚类、LLM 比较或 Dashboard。

### Commit

本节随 `feat(phase-3): persist idempotent hotspot snapshots` 独立提交。

## Phase 4：热点标准化与基础去重

- [x] 实现 Unicode、空白、标点和标题规范化。
- [x] 实现 canonical URL。
- [x] 实现热度单位和平台时间解析。
- [x] 实现外部 ID、URL、严格标题指纹去重。
- [x] 保存规则版本与匹配证据。
- [x] 完成边界/回放测试、任务文档更新和独立 commit。

### 完成项

- 新增不可变的 `SnapshotRawItem`、`NormalizedHotItem`、`NormalizationBatch`、`DedupGroup` 和匹配证据领域合同。
- 标题规范化使用 Unicode NFKC、格式控制字符清理、空白折叠和明确标点映射；严格标题指纹额外移除空白/标点并 casefold，不修改 raw 标题。
- canonical URL 仅接受 HTTP(S)，统一 scheme/IDNA host/默认端口/路径编码，排序 query，移除 fragment 与配置化 tracking 参数；带凭据或非法端口的 URL 明确失败。
- 热度以 `Decimal` 规则解析整数、小数、千/万/亿、K/M/W 等配置化单位，不可识别单位不猜测数值。
- 平台时间支持带时区 ISO、Unix 秒/毫秒、刚刚、分钟/小时/天前、昨天、月日等保守格式；相对时间以原始 `observed_at` 为锚，无法解析时保存 warning，不伪造时间。
- 基础去重在单个快照内按“平台 + Provider 外部 ID”“平台 + canonical URL”“平台 + 严格标题指纹”建立哈希索引，并以并查集做线性候选合并；未使用 LLM，也没有全量两两比较。
- 每个去重组选择最低有效 rank、再按原始位置排序的代表项；成员保存匹配类型、匹配对象和匹配值 SHA-256，可审计传递合并。
- 新增 `hotspot_normalization_runs`、`hotspot_normalized_items`、`hotspot_dedup_groups`、`hotspot_dedup_members` SQLite/MySQL 迁移；以 `snapshot + rule_version + config_hash` 幂等。
- 同一配置重跑会跳过，规则或配置变化会追加新批次；失败派生记录保留 error，原始数据和旧派生版本均不覆盖。
- Collector V2 Scheduler 在采集后通过独立 `HotspotNormalizationService` 回放待处理 fresh 快照；单个快照失败被隔离并保留为可重试状态。

### 遗留问题

- 本阶段只做快照内、低误判的确定性去重；相似标题、跨平台内容和跨时间事件合并必须等 Phase 5 的候选召回与事件聚类。
- 未识别的热度或时间格式只产生 `partial`/warning；新增格式必须提升规则版本并通过历史回放测试，不能原地改写旧结果。
- tracking 参数默认列表可能不适合所有自建 Provider，管理员可配置；配置变化会安全生成新的 append-only 标准化批次。
- MySQL 002 迁移尚未在生产同版本实例演练，仍需在部署前执行迁移、回滚和备份恢复验证。

### 测试证据

- `pytest -W error::DeprecationWarning`：141 passed；Phase 4 新增 36 项规则、Unicode、URL、热度、时间、去重、规模、迁移和回放测试。
- 2000 条唯一热点的规模保护测试确认去重键只提取 2000 次，不执行 O(n²) 比较或任何 LLM 调用。
- 覆盖配置哈希、非法后台配置、IDNA/追踪参数/危险 URL、小数单位、相对时间、跨年月日、partial/failed、传递去重证据、Provider/平台作用域、空快照、幂等与规则升级追加。
- `ruff check`、`ruff format --check`、`python -m compileall` 通过；前端 Vite 生产构建通过；`npm audit` 为 0 vulnerabilities。

### 下一 Phase 计划

Phase 5 只实现跨平台事件聚类：

- 新增事件、事件成员、聚类运行和候选匹配证据表，记录算法/配置版本。
- 使用时间窗、实体/关键词、n-gram/MinHash 或 ANN 建立有上限的候选召回，不做全量两两比较。
- 先执行确定性相似度与配置化阈值；仅把灰区候选交给可选 AI 语义边界判断。
- AI 不可用、超时或输出非法时保持确定性结果并记录降级，不阻断事件回放。
- 建立跨平台正负例、边界例、规模保护和历史重放测试；不提前实现趋势生命周期或 Dashboard。

### Commit

本节随 `feat(phase-4): normalize and deduplicate snapshot items` 独立提交。

## Phase 5：跨平台事件聚类

- [x] 实现时间窗、关键词和字符 n-gram 候选召回。
- [x] 禁止全量 LLM 两两比较并加入规模保护测试。
- [x] 实现确定性相似度与配置化阈值。
- [x] 仅对边界候选调用 AI 语义判断。
- [x] 保存事件成员、匹配证据和算法版本。
- [x] 完成质量/规模/回放测试、任务文档更新和独立 commit。

### 完成项

- 新增不可变 `ClusterInputItem`、候选决策、事件成员、事件和聚类批次领域合同；每个 Phase 4 去重组恰好进入一个事件，单例不会丢失。
- `ClusteringRepository` 只读取与当前标准化规则版本和配置哈希一致的去重组代表项，不重新消费 raw item，也不混用不同 Phase 4 版本。
- 默认以最新真实观测为锚回看 48 小时，候选时间窗 36 小时；历史数据可以离线重放，不因执行当天时间而被错误排除。
- 候选召回使用严格标题、canonical URL、字符 n-gram 倒排和关键词特征；倒排 posting 与每条候选数均有上限，候选对上界为 `N × max_candidates_per_item`。
- 确定性相似度由标题序列、n-gram、关键词和时间特征加权；版本、窗口、阈值、权重、倒排上限、候选上限和语义预算均通过 settings 配置并写入稳定配置哈希。
- 只有确定性分数位于灰区且显式开启语义判断时才调用 `SemanticBoundaryJudge` 端口；默认没有生产模型耦合，不会把分类或摘要提前带入 Phase 5。
- 语义端口缺失、超时、非法结果或调用预算耗尽时保守拒绝，分别记录 unavailable/error/invalid/budget_exhausted，聚类运行标记 degraded，不虚构合并结果。
- 新增 SQLite/MySQL 003 迁移：`hotspot_clustering_runs`、`hotspot_cluster_candidates`、`hotspot_events`、`hotspot_event_members`；候选原因、分数组件、最终决策和模型边界证据全部追加保存。
- 聚类运行按算法版本、聚类配置、上游标准化配置和输入哈希幂等；相同输入重跑跳过，配置或输入变化追加新版本。
- Collector V2 Scheduler 在标准化之后调用独立 `HotspotClusteringService`，并在状态接口暴露最新聚类计数与失败信息。

### 遗留问题

- 当前事件 ID 属于单次聚类运行；跨运行的事件连续性、速度、加速度、复发识别和生命周期状态属于 Phase 6，不能在 Phase 5 通过回写历史事件实现。
- 语义边界只有端口、结构化结果校验和降级策略，默认关闭；生产模型选择、提示词版本、成本与延迟记录将在 Phase 7 落地，启用前仍需人工标注边界集评估。
- 中文候选召回当前使用无外部词典的字符 n-gram 与单字关键词特征；若未来引入分词、MinHash 或向量索引，必须提升算法版本并用历史回放比较误合并/漏合并率。
- MySQL 003 已按既有 191 字符外键列对齐并通过静态检查，但当前环境没有生产同版本 MySQL，部署前仍需迁移、回滚和备份恢复演练。
- 四平台实时数据可用性仍受 Phase 2 外部状态限制；聚类只处理真实持久化快照，测试 fixture 不会进入生产库或对外冒充实时事件。

### 测试证据

- `pytest -W error::DeprecationWarning`：158 passed；Phase 5 新增 17 项规则、候选、语义边界、规模、迁移、持久化、幂等、Scheduler 和历史回放测试。
- 1000 条高重叠标题的规模保护测试确认候选对不超过 `N × 5`，且小于全量两两组合的 1%，语义调用为 0；未执行热点全量两两比较。
- 覆盖精确跨平台合并、时间窗隔离、负例单例、灰区语义调用、模型超时降级、配置非法、代表项读取、候选证据落库、原始记录保留、同配置幂等与阈值升级追加。
- 新增/修改聚类模块通过 `ruff check`、`ruff format --check`、`python -m compileall`；前端 Vite 生产构建与 `npm audit` 通过。

### 下一 Phase 计划

Phase 6 只实现趋势生命周期引擎：

- 新增版本化趋势运行、事件窗口特征和生命周期状态表，消费 Phase 5 事件成员与真实快照，不读取 Provider 临时响应。
- 计算配置化的平台覆盖、排名/热度、速度、加速度、持续度和复发间隔；明确区分缺失、失败与 stale 数据。
- 实现 `emerging/rising/peaking/declining/dormant/recurrent` 状态机、允许的状态迁移和回放幂等。
- stale 或缺失平台不得制造实时上升信号；为边界阈值、时间序列、复发、回退和规模编写测试。
- 不提前实现 AI 酒旅分类、Dashboard、日报或飞书推送。

### Commit

本节随 `feat(phase-5): cluster bounded cross-platform hotspot events` 独立提交。

## Phase 6：趋势生命周期引擎

- [x] 实现 `emerging/rising/peaking/declining/dormant/recurrent` 状态机。
- [x] 实现速度、加速度、持续度和跨平台覆盖特征。
- [x] 实现配置化窗口、阈值、权重和衰减。
- [x] stale 数据不得制造实时上升信号。
- [x] 完成状态机/配置/时间序列测试、任务文档更新和独立 commit。

### 完成项

- 新增不可变趋势观测、事件输入、评估上下文、上一状态、特征、状态记录和批次领域合同；状态机完整覆盖 emerging、rising、peaking、declining、dormant、recurrent，并限制非法跃迁。
- `TrendRepository` 只读取当前 Phase 5 聚类运行、事件成员、Phase 4 代表项及其真实快照观测；不读取 Provider 临时响应，不修改 Phase 5 事件，也不复用旧 `/api/trends` 的兼容快照评分。
- 趋势计算按 30 分钟桶提取当前/上一/更早强度，计算速度、加速度、平台覆盖、持续度、观测数、freshness 年龄和复发间隔；每条观测每次运行只计算一次基础信号，没有事件两两比较或 LLM 调用。
- 排名与对数热度信号、回看窗口、休眠/复发间隔、速度/平台/持续度权重、平台总数和各状态阈值全部来自 `hotspot_trend_*` settings，并进入稳定配置哈希和算法版本。
- 只有 `fresh` 观测进入强度、速度和加速度；stale 仅保留计数与数据质量证据，即使携带极高热度也不能触发 rising。
- 最新采集运行作为趋势评估水位。采集失败不会制造快照或上升信号，但会推进事件年龄，使状态可以确定性转为 declining/dormant；同窗口的失败、stale、缺失平台数和完整度进入数据质量。
- 通过共享 Phase 4 去重组优先、代表标题指纹兜底的确定性 lineage 将不同 Phase 5 运行关联到稳定 `trend_series_id`；匹配类型、重叠数和上一事件 ID 都持久化，复发判断不依赖可变 event ID。
- 新增 SQLite/MySQL 004 迁移：`hotspot_trend_runs` 和 `hotspot_trend_states`。运行保存 source/evaluation/config/input 哈希和状态计数；状态同时保存可查询特征列、完整 JSON、上一状态和 lineage 证据。
- 运行按聚类运行、评估水位、算法版本、配置哈希和输入哈希幂等；同水位重跑跳过，配置或采集水位变化追加新运行，旧趋势状态不回写。
- Collector V2 Scheduler 在聚类之后调用独立 `HotspotTrendService`，状态接口暴露最新趋势运行、生命周期计数及失败信息；趋势失败被隔离并允许后续窗口重试。

### 遗留问题

- Phase 6 只生成确定性趋势状态，没有 AI 主题分类、酒旅相关性或摘要；这些字段必须等 Phase 7 的结构化模型输出和人工标注评测门禁。
- 当前 lineage 是确定性的去重组重叠/代表指纹关联。若未来增加向量或 AI 跨运行关联，必须提升算法版本、保留旧结果，并用人工事件连续性集合评估误关联。
- 默认趋势参数是工程初始值，尚未用生产真实流量校准；上线前应基于长期真实快照回放调整阈值，不能用测试 fixture 作为业务效果证明。
- MySQL 004 已与现有外键类型对齐并通过静态检查，但当前环境没有生产同版本 MySQL；部署前仍需迁移、回滚、索引和备份恢复演练。
- 四平台实时数据可用性仍受 Phase 2 外部状态限制。无 fresh 数据时会保存真实失败或数据质量状态，不会生成演示趋势。

### 测试证据

- `pytest -W error::DeprecationWarning`：179 passed；Phase 6 新增 21 项规则、六状态、时间序列、freshness、采集失败水位、规模、迁移、持久化、lineage、幂等和 Scheduler 测试。
- 六种生命周期均有确定性时间序列用例；stale 高热度不能触发 rising，失败采集推进 8 小时后事件进入 dormant 且快照数不增加。
- 10,000 条观测规模测试确认每条观测每次运行只计算一次基础信号，不执行事件两两比较或任何 LLM 调用；同输入重放得到相同 run/state ID 和 input hash。
- 新增/修改趋势模块通过 `ruff check`、`ruff format --check`；完整 `compileall`、前端 Vite 生产构建和 `npm audit` 在提交门禁中复核。

### 下一 Phase 计划

Phase 7 只实现 AI 分类与酒旅相关性：

- 定义严格结构化的分类、酒旅相关性、理由与摘要 schema，并保存输入事件/趋势证据引用。
- 建立独立 AI adapter 和版本化 prompt/model 配置；记录耗时、token/成本（Provider 可提供时）、失败原因和原始结构化响应哈希。
- 只对事件分类与摘要，不用 LLM 重新计算趋势、伪造实时事实或执行热点全量两两比较。
- 对无 Key、超时、限流、非法 JSON、schema 漂移和模型失败做明确降级，核心采集/趋势链继续运行。
- 建立人工标注的主题与酒旅相关性评测集和阈值门禁；不提前实现 Dashboard、报告或飞书推送。

### Commit

本节随 `feat(phase-6): add hotspot trend lifecycle engine` 独立提交。

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
