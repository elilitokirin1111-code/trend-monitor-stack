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
| 7 | AI 分类与酒旅相关性 | 已完成（生产模型评测待配置） | 204 tests + 严格 schema/证据/降级门禁 |
| 8 | 热点 Dashboard | 已完成 | API、组件、构建、端到端测试 |
| 9 | 日报/周报系统 | 已完成 | 窗口、模板、幂等、快照测试 |
| 10 | 飞书报告推送 | 已完成 | 签名、分片、重试、幂等测试 |
| 11 | 运行稳定性和监控 | 已完成 | 故障注入、告警、恢复、负载测试 |

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

- [x] 定义结构化分类输出 schema。
- [x] 实现主题分类、酒旅相关性、理由与摘要。
- [x] 记录模型、提示词版本、输入证据、成本和耗时。
- [x] 实现超时、无 Key、非法输出和模型失败降级。
- [x] 建立固定、可人工审阅的标注评测集，不用 AI 自评代替验收。
- [x] 完成 schema/降级/评测测试、任务文档更新和独立 commit。

### 完成项

- 新增不可变分类证据、趋势输入、结构化决策、逐事件记录和批次领域合同。输出严格限制为主题分类、1–5 个标签、酒旅相关性与分数、置信度、理由、摘要和证据 ID。
- `ClassificationRepository` 只消费最新版本化 `hotspot_trend_states` 及对应 Phase 5 事件成员；模型看到的标题、平台、观测时间、排名和热度都可回溯到不可变派生/快照记录，不读取 Provider 临时响应。
- 分类响应必须是无 Markdown 包裹的单个 JSON 对象，字段集合和类型必须完全匹配 schema；`evidence_ids` 必须属于当前事件成员，引用不存在的证据会整条失败，不保存伪造决定。
- 新增独立 `ClassificationProvider` 端口与 `LiteLLMClassificationProvider` 适配器，复用已有 LiteLLM 依赖而未增加第三方包；请求使用确定性温度和 JSON response format，并记录实际模型、耗时、prompt/completion token 及 Provider 可提供的成本。
- 分类默认独立关闭；旧摘要 `ai_config.enabled` 不会自动启用 Phase 7。只有显式设置 `hotspot_ai_classification_enabled=true` 才调用模型，禁用或缺 Key 时分别保存 skipped/failed 审计状态。
- classifier/prompt 版本、模型、base URL、超时、最大并发和文本上限通过 `hotspot_ai_*` settings 配置并进入稳定配置哈希；API Key 不进入配置 JSON、哈希、日志或错误正文。
- 超时、限流、Provider 异常、非法 JSON、schema 漂移、证据越界和无 Key 均有独立错误码；单事件失败不阻断其他事件，也不影响采集、聚类或趋势链。
- 同一趋势运行、输入、classifier/prompt/model/config 在模型调用前计算确定性 run ID 并查询幂等记录；重复调度不会再次调用模型，配置或提示词版本变化才追加新批次。
- 新增 SQLite/MySQL 005 迁移：`hotspot_classification_runs` 和 `hotspot_ai_classifications`。运行与逐事件结果保存 input/request/response hash、完整响应正文、结构化决定、证据引用、token/成本、耗时和失败原因，旧趋势结果不回写。
- Scheduler 已在 TrendEngine 后调用独立 `HotspotClassificationService` 并暴露最新成功/失败/跳过计数；默认关闭时仍形成真实、可审计的 skipped 记录。
- 修补旧 AI 配置泄密路径：专用 `/api/scheduler/ai-config` 和通用 `/api/config/settings` 均对 legacy `ai_config.api_key` 与 `hotspot_ai_api_key` 做掩码，更新响应也不再返回完整 Key。
- 新增 12 条固定、可人工审阅的主题/酒旅相关性验收标签，标签与模型预测分离；离线 evaluator 只计算 category/relevance accuracy，缺失预测按错误计，不允许模型给自己打分。

### 遗留问题

- 当前环境没有用户授权的生产模型 Key，因此没有把 fixture 或虚构结果冒充真实模型评测。12 条固定标签只验证 schema、执行器和指标合同；上线前需由酒旅业务负责人复核并扩充真实事件标注集，再对选定模型设定准确率门槛。
- LiteLLM 适配器已通过隔离契约测试，但不同模型对 JSON response format、token/cost 字段和限流错误的支持仍需用目标 Provider 做真实合同验证。
- 当前运行前检查可避免顺序重复调用，数据库唯一键可避免重复落库；极端多实例同时首次处理同一趋势运行时仍可能产生重复外部调用，分布式调用租约留到 Phase 11。
- 模型输出是派生判断而非事实来源；Dashboard 和报告必须同时展示 evidence、data quality 和失败状态，不得只展示摘要文本。
- MySQL 005 已按现有外键类型设计并通过迁移测试/静态检查，但当前环境没有生产同版本 MySQL，部署前仍需迁移、回滚、索引和备份恢复演练。

### 测试证据

- `pytest -W error::DeprecationWarning`：204 passed；Phase 7 新增 25 项规则、schema、证据约束、超时、限流、并发上限、错误脱敏、Provider 适配、持久化、幂等、评测、安全掩码和 Scheduler 测试。
- 覆盖严格 JSON 成功、未知 evidence ID、Markdown/非法 JSON、Provider 异常、限流、超时、禁用、缺 Key、API Key 错误脱敏、实际模型/token/成本记录、配置非法和提示词升级追加。
- 12 条固定标注集验证类别/相关性指标，缺失预测明确计错；测试没有调用外部模型，也没有把固定样例写入生产数据库或对外接口。
- 新增分类模块通过 `ruff check`、`ruff format --check`；完整 `compileall`、前端 Vite 生产构建和 `npm audit` 在提交门禁中复核。

### 下一 Phase 计划

Phase 8 只实现热点 Dashboard 与 V1 读取 API：

- 新增 `/api/v1/hotspots` 只读接口，联合展示事件、趋势、分类、平台 freshness、失败/缺失和原始证据引用。
- 为列表、详情、筛选、分页和采集健康定义稳定 response schema；旧 HotPush API 保持兼容。
- Dashboard 明确区分 fresh/stale/failed、AI success/failed/skipped 和数据年龄，不隐藏 Provider/模型不可用状态。
- 展示事件成员、趋势生命周期、酒旅相关性与理由；摘要不得脱离证据单独呈现。
- 完成 API、组件、生产构建和端到端测试；不提前生成日报/周报或发送飞书。

### Commit

本节随 `feat(phase-7): add evidence-grounded AI classification` 独立提交。

## Phase 8：热点 Dashboard

- [x] 新增 V1 事件、趋势、平台、freshness API。
- [x] 展示实时/陈旧/失败状态和数据年龄。
- [x] 展示事件成员与原始证据链接。
- [x] 展示趋势生命周期、酒旅相关性和筛选。
- [x] 增加采集健康和 Provider fallback 可见性。
- [x] 完成 API/组件/构建/E2E 测试、任务文档更新和独立 commit。

### 完成项

- 新增 `/api/v1/hotspots` 只读 API：`GET /overview`（平台健康卡片）、`GET /events`（关键词/平台/生命周期/酒旅相关性/数据质量筛选 + 分页）、`GET /events/{event_id}`（事件成员与原始证据）、`GET /raw-items/{raw_item_id}`（原始热点证据）。
- 平台健康卡片展示 `fresh/stale/failed/unavailable` 状态、数据年龄（`formatAgeMinutes`）、胜出 Provider、fallback 是否触发、stale 原因和最近错误，且永不把 unavailable/失败数据描述为实时。
- 事件列表展示趋势生命周期状态、酒旅相关性、数据质量和证据链；事件详情链接全部原始证据记录，未知证据返回 404。
- 前端新增 `/intelligence` 热点情报页（`HotspotDashboardView.vue`）、Pinia store 与查询构建工具；侧边栏新增"热点情报"入口。
- Dashboard 仓储坚持 freshness 硬边界：最新失败保留旧快照但标记 `failed` 且 `stale`，空数据库返回显式空状态，stale 阈值可运行时配置。

### 遗留问题

- 前端 E2E（Playwright 等）未引入；目前以 Node 内置 test runner 单元测试 + Vite 生产构建 + 后端 API 契约测试覆盖。
- 生产部署仍缺真实四平台 live 数据（见 Phase 2 遗留），Dashboard 会如实显示采集失败/不可用状态。

### 测试证据

- `pytest tests/hotspot/test_dashboard_api.py tests/hotspot/test_dashboard_repository.py -v`：9 passed（鉴权保护、契约、404、overview 不隐藏 unavailable、stale 阈值配置、失败保留旧快照、事件筛选、证据链接、空库显式空状态）。
- 后端全量回归：`pytest -q`：214 passed。
- 前端：`npm test`：3 passed（查询构建省略空筛选、freshness 标签/色调、数据年龄格式化）。
- 前端生产构建：`npm run build`：Vite 构建成功。

### 下一 Phase 计划

Phase 9 实现日报/周报系统：新增 `reports` 迁移；`ReportEngine` 只消费已版本化的事件与趋势状态（不直接读取 Provider 响应）；`ReportService` 按 `period + report_type + version + input_hash` 幂等生成、支持重跑与审计；明确标记 stale、缺失平台和数据不完整；补窗口/模板/快照测试并独立 commit。

### Commit

本节随 `feat(phase-8): add hotspot intelligence dashboard` 独立提交。

## Phase 9：日报/周报系统

- [x] 定义日报/周报时间窗和版本。
- [x] 基于事件与趋势生成报告，不直接读取 Provider 响应。
- [x] 实现幂等生成、重跑和审计来源。
- [x] 明确标记 stale、缺失平台和数据不完整。
- [x] 完成窗口/模板/快照测试、任务文档更新和独立 commit。

### 完成项

- 新增 `ReportType`（daily/weekly）、`ReportStatus`、`ReportDataQuality` 领域合同和 `ReportRules` 配置（`hotspot_report_version`、`hotspot_report_template`、`hotspot_report_max_items`、`hotspot_report_include_irrelevant`、`hotspot_report_timezone`），配置进入稳定 `config_hash`。
- 时间窗按 `Asia/Shanghai` 自然日：日报为最近 1 个自然日、周报为最近 7 个自然日；支持显式 `period_start` 和 31 天上限校验。
- `ReportEngine` 只消费版本化趋势状态、事件成员和 AI 分类（含已有摘要），确定性渲染 Markdown 报告，不读取 Provider 响应；事件按趋势分排序、可过滤不相关事件、`max_items` 截断。
- `ReportRepository` 按 `report_type + period_start + report_version + config_hash + input_hash + attempt` 幂等落库；`report_run_id_base` 确定性生成，`force` 重跑追加 `attempt` 新记录，旧记录保留可审计。
- 报告明确标记 `stale_platforms`、`missing_platforms` 和数据质量（complete/partial/stale_only/no_fresh_data），正文包含审计来源（源趋势运行、源分类运行、输入/配置哈希）。
- 新增 `hotspot_report_runs` 迁移（sqlite/mysql 双份）；调度器注册 `hotspot_report_daily`（每天 01:00）和 `hotspot_report_weekly`（每周一 01:00）独立任务并记录最近结果；`POST /api/v1/hotspots/reports/{daily|weekly}/regenerate` 提供管理员手动重跑入口。
- 新增 V1 报告 API：`GET /reports`（类型/分页筛选）、`GET /reports/{report_run_id}`（详情含正文）、`POST /reports/{report_type}/regenerate`（管理员）。

### 遗留问题

- 报告正文为确定性 Markdown 模板；AI 生成摘要未启用（仅复用 Phase 7 分类摘要）。后续可接入报告级 AI 摘要端口（架构文档 §9 允许），默认关闭不产生费用。
- 周报时间窗固定为最近 7 个自然日，暂不支持自定义结束日。
- 前端暂无报告浏览页，可通过 API/Swagger 查看。

### 测试证据

- `pytest tests/hotspot/test_report_rules.py tests/hotspot/test_report_engine.py tests/hotspot/test_report_repository.py tests/hotspot/test_reports_api.py`：23 passed（窗口/版本/配置哈希、模板渲染与排序、stale/缺失标记、数据质量判定、幂等生成、force 重跑 attempt 追加、列表分页、API 鉴权与管理员门禁、404）。
- 后端全量回归：`pytest -q`：237 passed。
- 迁移幂等：`HotspotMigrationRunner.apply() == (1,2,3,4,5,6)`，重复 apply 返回空。

### 下一 Phase 计划

Phase 10 将 `FeishuPusher` 升级为报告投递适配器：webhook 签名/密钥与凭据脱敏、超时/有限重试/指数退避、长度分片与飞书业务码校验、`report_run_id + channel + content_version` 幂等投递、`report_deliveries` 表与重放/失败告警，完成签名/分片/重试/幂等测试后独立 commit。

### Commit

本节随 `feat(phase-9): add versioned daily and weekly hotspot reports` 独立提交。

## Phase 10：飞书报告推送

- [x] 将 `FeishuPusher` 升级为报告投递适配器。
- [x] 支持签名、凭据脱敏、超时、重试和指数退避。
- [x] 支持长度分片和飞书业务码校验。
- [x] 实现投递幂等、历史、重放和失败告警。
- [x] 完成签名/分片/重试/幂等测试、任务文档更新和独立 commit。

### 完成项

- 新增 `app/delivery/` 投递模块：`FeishuDeliveryAdapter`（报告投递适配器）、`FeishuDeliveryRules`、签名/脱敏/分片工具。
- 签名：按飞书官方算法 `HMAC-SHA256(timestamp + "\n" + secret)`，请求携带 `timestamp` 和 `sign`；凭据脱敏：webhook query 与 secret 永不进日志/配置哈希。
- 超时（可配置）、有限重试（0–5）与指数退避（base 0.01–60s、max 30s）；错误分类：not_configured/timeout/network/http_error/business_error/invalid_response/unknown，仅可重试类触发重试。
- 长度分片：报告正文按 `hotspot_delivery_max_chunk_chars`（默认 20000）切块，尽量在换行边界切割；每片独立投递并记录 `chunk_index/total_chunks`。
- 飞书返回业务码校验：HTTP 2xx 且 `code == 0` 才视为成功，`code != 0` 记录业务码与 msg 为失败。
- 幂等投递：`report_run_id + channel + content_version + chunk_index` 唯一键（`hotspot_report_deliveries` 表，迁移 007），重复投递跳过、`force` 覆盖重投。
- 投递历史与重放：`GET /deliveries`、`GET /deliveries/{id}`、`POST /reports/{id}/deliver`、`POST /deliveries/{id}/replay`（后两者管理员）。
- 失败告警：投递失败时通过可选 `hotspot_delivery_alert_webhook` 发送告警（best-effort 不重试），失败详情与告警状态均落库。
- 旧 `FeishuPusher` 升级：复用签名、超时、业务码校验与脱敏日志，PushService 接口保持不变。
- 新增 `feishu_webhook_secret` 应用配置项。

### 遗留问题

- 告警只支持飞书 webhook 单通道；多通道告警（Telegram/邮件）留待 Phase 11 监控接入。
- 未做真实飞书端到端验证（需真实 webhook 与签名密钥）；签名算法按官方文档实现并有固定向量测试。
- 报告投递未加入自动调度（报告生成后需手动或后续 Phase 11 定时触发投递）。

### 测试证据

- `pytest tests/hotspot/test_feishu_adapter.py tests/hotspot/test_delivery_repository.py tests/hotspot/test_delivery_service.py tests/hotspot/test_deliveries_api.py`：28 passed（签名向量、URL 脱敏、分片边界、业务码不重试、HTTP 错误重试+退避、瞬时网络故障恢复、超时分类、幂等键、force 覆盖、失败告警、重放恢复、API 鉴权/404/契约）。
- 后端全量回归：`pytest -q`：265 passed。
- 迁移幂等：`HotspotMigrationRunner.apply() == (1,2,3,4,5,6,7)`。

### 下一 Phase 计划

Phase 11 完成运行稳定性与监控：结构化日志/指标/trace（correlation ID）、Provider 成功率/延迟/空榜/stale 年龄/fallback 比率监控、队列积压/聚类耗时/AI 失败/报告与投递状态监控、健康/就绪检查与告警规则、故障注入/恢复/迁移回滚/备份恢复/负载测试、运行手册，最终任务文档更新与独立 commit。

### Commit

本节随 `feat(phase-10): add feishu report delivery with signing and idempotency` 独立提交。

## Phase 11：运行稳定性和监控

- [x] 建立结构化日志、指标、trace/correlation ID。
- [x] 监控 Provider 成功率、延迟、空榜、stale 年龄和 fallback 比率。
- [x] 监控队列积压、聚类耗时、AI 失败、报告和投递状态。
- [x] 实现健康检查、就绪检查和告警规则。
- [x] 执行故障注入、恢复、迁移回滚、备份恢复和负载测试。
- [x] 完成运行手册、最终任务文档更新和独立 commit。

### 完成项

- 结构化日志：`logger.py` 支持 JSON 行输出（`HOTSPOT_STRUCTURED_LOGS=1`）与 `CorrelationFilter`；新增 `CorrelationMiddleware`（`X-Correlation-ID` 透传/生成，响应回写），日志行携带 correlation ID 前缀。
- 运行时指标：`app/observability/metrics.py` 进程内注册表（计数器/仪表/延迟摘要），Prometheus 文本渲染，`GET /api/v1/hotspots/monitoring/metrics` 公开抓取；采集/标准化/聚类/趋势/分类阶段用 `timed` 打点。
- DB 聚合监控：`PipelineMonitor` 从 append-only 表聚合 Provider 成功率、平均延迟、空榜数、fallback 尝试与比率、平台失败数、最新 stale 年龄（分钟）、标准化积压快照数、最近聚类/趋势/分类/报告运行状态、失败投递总数。
- 告警规则：`AlertEvaluator` 支持 stale 平台（超阈值 3 倍升 critical）、Provider 成功率（样本 ≥3）、失败运行数、积压快照数、失败投递（critical）五类规则；配置键 `hotspot_alerts_enabled` 等；指纹去重（`hotspot_alert_last_fingerprint`），变化时经可选 `hotspot_alert_webhook` 推送；调度器每次采集后自动评估并暴露 `last_alert_result`。
- 健康/就绪：`/health`（liveness）保留，新增 `/health/ready`（数据库连通性）与 `/api/v1/hotspots/monitoring/health`（V1 管线视图）。
- 监控 API：`GET /monitoring/summary`、`GET /monitoring/alerts`（登录）；metrics 端点公开且仅含运行时指标。
- 故障注入与恢复测试：Provider 全失败→Dashboard 如实标记 failed/stale 且不伪造实时；下一窗口 fresh 采集恢复；SQLite 文件级备份/恢复后数据与迁移完整；迁移漂移（篡改已应用迁移）触发 `MigrationDriftError`；全新库完整重建全部 7 个迁移并幂等。
- 负载测试：批量写入 1000 raw items 后 overview/events 查询在 5 秒门禁内且结果如实（未聚类不编造事件）；10 个批量 run 保持 append-only。
- 运行手册：`docs/RUNBOOK.md`（架构、启动配置、任务清单、监控端点与告警规则、故障排查、备份恢复、回滚、质量门禁、上线前复核清单）。

### 遗留问题

- 生产告警通道目前仅飞书 webhook；多通道（Telegram/邮件）与 Prometheus 抓取接入（如 Grafana 面板）未部署验证。
- 负载测试为 SQLite 本地门禁（<5s）；MySQL 生产规模压测需在部署环境执行。
- 结构化日志的 JSON 模式需在真实采集场景下校验字段兼容性。

### 测试证据

- `pytest tests/hotspot/test_metrics.py tests/hotspot/test_monitor.py tests/hotspot/test_alerts.py tests/hotspot/test_monitoring_api.py tests/hotspot/test_fault_recovery.py tests/hotspot/test_load_scale.py`：27 passed（指标渲染、聚合正确性、五类告警规则、API 契约/鉴权、故障注入/恢复/备份/漂移/重建、负载门禁）。
- 后端全量回归：`pytest -q`：292 passed。
- 前端构建与测试：`npm test` 3 passed、`npm run build` 成功（Phase 8 后未再改动前端）。

### 完成总览

V1 全部 12 个 Phase（0–11）完成：审计→Collector→四平台接入→快照→标准化去重→聚类→趋势→AI 分类→Dashboard→日报/周报→飞书投递→监控运维，各阶段独立 commit、测试证据与任务文档齐备。V1 目标链路（Platform → ... → ReportEngine → Feishu → Monitoring）全部落地。

### Commit

本节随 `feat(phase-11): add observability, alerts and runbook` 独立提交。

## Frontend V2 · UX Phase 1：融合式情报工作台

- [x] 确认 D 融合方案与产品信息架构。
- [x] 重构专业应用外壳与分组导航。
- [x] 实现平台状态条、真实指标和事件研判队列。
- [x] 实现列表/卡片视图、快捷筛选和高级筛选。
- [x] 将事件详情升级为研判/证据双栏目的右侧抽屉。
- [x] 完成浅色、深色、桌面和移动端响应式验证。
- [x] 补充前端真实性工具测试并完成构建回归。

### 完成项

- 新增 `docs/HOTSPOT_V2_UI.md`，记录 D 融合方案、信息架构、API 映射和数据真实性约束。
- 全局应用外壳从 HotPush 原始导航升级为“情报工作台 / 数据与交付 / 系统管理”分区；保留 HotPush 架构来源链接。
- 情报总览完全复用 Phase 8 API，不新增虚构指标或演示数据；平台无数据、stale 和失败均保留明确状态。
- 四平台状态条支持直接筛选；事件队列支持生命周期快捷筛选、全文搜索和高级条件组合。
- 事件列表支持高密度与卡片模式；移动端自动收敛为卡片式阅读。
- 事件详情抽屉保留 AI 缺失状态、数据质量、趋势速度、酒旅相关性和所有 RawHotItem 证据链接。

### 遗留问题

- 报告、投递与监控后端已有 API，但尚未制作 Frontend V2 页面。
- EventCluster 暂无历史序列读取 API，因此本阶段没有绘制趋势折线，避免用推测点位冒充真实历史。
- 事件详情抽屉已通过构建和空数据态浏览器检查；有真实采集数据后的完整证据长列表仍需在部署环境复核。

### 测试证据

- `npm test`：6 passed（查询参数、freshness 文案、平台/生命周期/酒旅标签、平台健康汇总、时间格式）。
- `npm run build`：Vite 生产构建成功。
- 浏览器检查：桌面浅色、桌面深色、390×844 移动端；移动端 `scrollWidth <= innerWidth`，高级筛选可展开。
- 后端全量回归：`pytest -q`：292 passed，确认 Frontend V2 未改变既有 API 与数据链路。

### 下一 UI Phase 计划

新增“报告中心”第一批页面，连接 Phase 9/10 的日报、周报、投递历史和重放 API；先完成 API 契约与前端测试，再进入监控中心。

### Commit

本节随 `feat(frontend): introduce intelligence workspace UX` 独立提交。

## 部署修补：Docker 首次启动兼容性

- [x] 将前端生产构建镜像从 Node 18 升级到 Node 22，并声明 Vite 8 所需的运行时契约。
- [x] 修复 MySQL 事件聚类迁移中的跨表外键名称冲突。
- [x] 支持 MySQL DDL 中断后续跑定义一致的已创建索引；定义不一致时仍立即失败，禁止掩盖漂移。
- [x] 补充 MySQL 外键名称唯一性和索引续跑测试。
- [x] 收紧后端 Docker 构建上下文，排除测试虚拟环境和缓存目录。
- [x] 完成真实 Docker Compose 首次启动、管理员登录和热点总览 API 验证。

### 测试与运行证据

- 后端定向回归：11 passed（MySQL 约束、部分迁移续跑、迁移/仓储幂等）。
- 后端全量回归：`pytest -q`：295 passed。
- 前端：`npm test`：7 passed；`npm run build`：Vite 生产构建成功。
- Docker：MySQL/Redis/RSSHub healthy，Backend/Frontend 持续运行；7 个热点迁移版本全部登记。
- 登录/API：默认管理员登录成功；`GET /api/v1/hotspots/overview` 返回 `generated_at/has_data/event_count/trend_run/platforms` 真实字段。
- 后端 Docker 上下文由约 51 MB 降至约 189 KB。

### 遗留问题

- Docker Hub/CloudFront 在当前网络下偶发 TLS 握手超时；镜像已通过逐个重试拉取，不属于应用数据或代码故障。
- 对外部署前必须替换 Compose 中的默认管理员密码、MySQL 密码和 JWT Secret。

### Commit

本节随 `fix(docker): repair first-run build and MySQL migrations` 独立提交。

## 采集可用性修补：四平台 Provider 增强

- [x] 审计四平台 30 分钟采集运行记录，确认原公共 Provider 的真实失败原因。
- [x] 新增原生 RSSHub Provider，接入微博与 B站热搜，保留 XML 原文并按 feed build time 判定 freshness。
- [x] 将官方 DailyHotApi 作为独立 Compose 服务，固定验证过的镜像 digest，并接入抖音主 Provider。
- [x] 扩展 Provider Factory 的顺序、URL、RSS freshness 和 OpenCLI bridge 配置，继续支持后台显式覆盖与 fallback。
- [x] 扩展 OpenCLI 为小红书/微博/B站固定只读命令，并新增带 Bearer Token 的主机 Chrome 桥接器。
- [x] 增加 RSSHub、Provider Factory、OpenCLI 与桥接认证测试。
- [x] 用真实 Compose 采集验证抖音、微博、B站，保存 raw payload 长度与 SHA-256 证据。
- [x] 修复容器验收发现的 MySQL readiness DB-API 游标兼容问题并增加回归测试。
- [ ] 完成 Chrome Browser Bridge 扩展安装与小红书登录授权，再补录小红书 fresh 实采证据。

### 完成项

- Collector 与 Provider 继续通过合同解耦；RSSHub、DailyHotApi、NewsNow、OpenCLI 均可独立失败、替换与记录 attempt。
- 默认链路调整为抖音 `dailyhotapi → newsnow`，微博/B站 `rsshub → dailyhotapi → newsnow`，小红书 `opencli`。
- 失败响应仍保留 raw evidence；缺时间、过期 RSS 或 `fromCache=true` 不会被标成 fresh。
- 桥接器不接收任意命令、不记录 Cookie、不提供平台写操作；认证失败和扩展断开都显式失败。
- 许可证记录已更正 RSSHub 为 AGPL-3.0，并记录独立未修改容器的部署边界。

### 测试与运行证据

- Provider/桥接器定向测试：21 passed，`DeprecationWarning` 作为错误处理。
- 后端全量回归：`pytest -q -W error::DeprecationWarning`：307 passed。
- 前端回归：`npm test`：7 passed；`npm run build` 成功。
- Docker Compose 配置校验通过；DailyHotApi healthcheck 正常。
- 真实采集：抖音 50 条 fresh（DailyHotApi）、微博 51 条 fresh（RSSHub）、B站 10 条 fresh（RSSHub）。
- 原始 payload 长度与 SHA-256 见 `docs/evidence/PLATFORM_COLLECTION_2026-08-25.md`。

### 遗留问题

- 小红书依赖用户本机 Chrome 的官方 OpenCLI Browser Bridge 扩展与登录态；当前扩展未连接，因此按真实状态 failed/0 条。
- RSSHub 与 DailyHotApi 都是外部网络 Provider，后续仍需监控路由变更、上游频控、镜像安全更新和许可证义务。
- 对外部署前需把镜像版本/摘要和 Python/npm 依赖纳入 Phase 11 SBOM 流程。

### 下一步计划

1. 用户完成小红书 Chrome 授权后重跑真实采集验收。
2. 在系统设置页增加 Provider 顺序、RSS freshness 与 OpenCLI bridge 状态的可视化配置和健康检查。
3. 继续 Phase 11 运行稳定性与监控，增加连续失败、stale 比例和 Provider fallback 告警。

### Commit

本节随 `feat(collectors): add live providers for core platforms` 独立提交。
