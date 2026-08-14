# 多平台热点情报中心 V1 架构

## 1. 文档状态

- 状态：Phase 0 架构基线
- 更新时间：2026-08-14
- 目标平台：`douyin`、`weibo`、`bilibili`、`xiaohongshu`
- 默认采集频率：30 分钟，可由后台配置
- 二次开发基线：HotPush `c9d6fce9213637ec0515fb806230e26c955c4031`

本文记录 V1 的边界、演进路径和质量门禁。Phase 0 不新增生产采集逻辑。

## 2. 当前代码基线

目标目录最初只有 `bin/autocli.exe`，没有业务源码、数据库、API、调度器或 Git 元数据。Phase 0 将 HotPush `main` 作为上游历史导入 `hotspot-v1` 分支，避免从零重建其已有能力，也便于后续同步和审计来源。

当前代码分层：

```text
frontend/                    Vue 3 + Vite + Tailwind CSS
  src/views/                 热榜、趋势、调度、推送、规则、用户页面
backend/
  app/main.py                FastAPI 入口与路由装配
  app/routers/               API、认证、配置、数据源、规则、历史、调度、趋势、用户
  app/services/              RSS 抓取、数据库、缓存、调度、AI 摘要、推送
  app/models/schemas.py      Pydantic API/业务模型
  app/utils/sources.py       RSSHub 数据源静态定义
  tests/                     后端单元/API 测试
docker-compose.yml           MySQL、Redis、RSSHub、后端、前端
```

现有主链路实际为：

```text
RSSHub/RSS -> RSSFetcher -> HotList/HotItem -> Redis + hot_item_snapshots
                                        \-> Scheduler -> Rules -> PushService
```

它不具备 Provider 抽象、原始数据层、采集批次、事件聚类、趋势生命周期或报告实体，不能直接等同于目标链路。

## 3. 现有能力处置

### 3.1 直接保留

以下能力原则上保留，仅在对应 Phase 做兼容性增强：

- FastAPI 应用生命周期、路由装配和健康检查。
- Vue 3/Vite/Tailwind 前端工程、登录态、路由与通用 UI 组件。
- 用户、角色和认证能力。
- 系统设置、推送渠道、推送规则和推送历史管理。
- Redis 缓存服务及分布式抓取锁思路。
- SQLite/MySQL 双数据库运行能力。
- APScheduler 的启动、暂停、恢复、立即触发与后台配置入口。
- 趋势图表的前端基础组件。
- Telegram、Discord、企业微信、飞书、钉钉、Webhook、邮件推送框架。
- Docker Compose 部署骨架和现有 CI 流程。

### 3.2 必须重构

| 现有位置 | 问题 | V1 方向 |
| --- | --- | --- |
| `services/rss_fetcher.py` | 采集、解析、缓存、快照、去重混在一个类中 | Collector 只编排；Provider 只访问数据源；映射器只生成领域输入 |
| `services/scheduler.py::_fetch_and_push_job` | 单任务同时抓取、过滤、推送，失败边界不清 | 拆成采集、快照后处理、报告、投递任务；每步可重试和观测 |
| `models/schemas.py::HotItem` | 缺少 provider、批次、原始载荷、fresh/stale、采集时间 | 引入不可变 `RawHotItem` 及独立的规范化模型 |
| `services/database.py` | 单文件手写建表，数据库演进不可追踪 | 引入版本化迁移；保留兼容读取接口，逐步拆 Repository |
| `hot_item_snapshots` | 直接保存展示模型，无法回溯原始响应 | 快照引用原始条目；原始层与分析层分离 |
| Redis 热榜缓存 | 缓存命中不向调用方暴露数据年龄 | API 必须返回 `freshness`、`observed_at`、`stale_reason` |
| AI 摘要 | 摘要与定时推送耦合，输入边界宽 | AI 仅做语义边界、分类和摘要，不参与全量两两比较 |
| 静态 `HOT_SOURCES` | 平台和传输实现耦合 | 平台、Provider、凭据和 fallback 策略分别配置 |

## 4. 目标数据链路

```text
Platform
  -> Collector
  -> Provider
  -> RawHotItem
  -> Database
  -> Snapshot
  -> Normalize
  -> Dedup
  -> EventCluster
  -> TrendEngine
  -> AI Classification
  -> Dashboard
  -> ReportEngine
  -> Feishu
```

关键边界：

- `Platform` 是业务枚举，不等于具体数据供应方。
- `Collector` 负责一次采集运行的编排、fallback、超时和结果汇总，不解析平台私有响应。
- `Provider` 负责外部访问和响应到 Provider DTO 的转换，不访问业务聚类、趋势、报告或推送代码。
- `RawHotItem` 是 append-only 原始事实。后续算法变化不得回写或覆盖它。
- `Snapshot` 表示特定采集窗口的观测集合，与单条原始事实分开。
- `NormalizedHotItem`、`EventCluster`、`TrendState`、`AIClassification` 都是可重建派生数据。
- `ReportEngine` 消费已经形成的事件和趋势，不直接遍历 Provider 响应。

## 5. Collector V2 与 Provider 合同

Phase 1 已落地的核心合同：

```python
class HotspotProvider(Protocol):
    provider_id: str
    supported_platforms: frozenset[Platform]

    async def collect(self, request: CollectRequest) -> ProviderResult: ...
    async def health(self) -> ProviderHealth: ...
```

实现位置：

- `backend/app/domain/hotspot/models.py`：不可变领域合同、状态、错误、Provider 条目、原始条目和采集结果。
- `backend/app/providers/hotspot/base.py`：Provider、原始写入和 stale 读取端口。
- `backend/app/providers/hotspot/registry.py`：可替换 Provider 注册表及平台能力校验。
- `backend/app/collectors/config.py`：Provider 顺序、超时、有限重试和 stale 策略。
- `backend/app/collectors/hotspot.py`：Collector V2 编排，不含平台解析、数据库实现或业务分析。

Collector 配置沿用现有通用后台 settings API，可写入以下字符串键：

- `hotspot_collector_timeout_seconds`
- `hotspot_collector_max_retries_per_provider`，限制为 0 到 3
- `hotspot_collector_allow_stale`
- `hotspot_provider_order_<platform>`，值为逗号分隔 Provider ID

Phase 1 不预置任何 Provider 顺序，防止在 Phase 2 真实契约测试前把候选来源误标为可用。

`ProviderResult` 必须明确表达：

- `status`: `success`、`partial`、`failed`。
- `freshness`: `fresh` 或 `stale`。
- `observed_at`、`fetched_at`、可选 `source_updated_at`。
- 原始响应引用或原始响应内容哈希。
- Provider 错误分类、可重试性和上游状态码。
- 规范化前的 Provider DTO 列表。

fallback 规则：

1. 每个平台由后台配置有序 Provider 链。
2. 仅在超时、连接失败、限流、响应无效或明确空结果异常时尝试下一个 Provider。
3. 实时 Provider 全部失败时，不生成或伪造实时条目。
4. 允许返回最后一次成功缓存，但必须标记 `stale=true`，并携带数据年龄与失败原因。
5. Provider 成功返回真实空榜时，不能自动把旧数据伪装成当前结果；是否展示旧榜由读取策略决定。
6. fallback 的每次尝试都写入采集运行明细，不能只保留最终结果。

计划的 Provider 优先级在 Phase 2 通过真实连通性测试后定稿，初始候选为：

| 平台 | 首选候选 | 备用候选 | 登录态备用 |
| --- | --- | --- | --- |
| douyin | DailyHotApi | NewsNow | OpenCLI |
| weibo | NewsNow | DailyHotApi | OpenCLI |
| bilibili | NewsNow | DailyHotApi | OpenCLI |
| xiaohongshu | 待真实能力验证 | 待真实能力验证 | OpenCLI |

不得仅根据文档宣称某 Provider 可用；Phase 2 必须保存真实契约测试证据。小红书没有可用实时 Provider 时，API 返回明确不可用状态，不用其他平台或样例数据补位。

## 6. 数据模型

### 6.1 现有表

HotPush 当前通过 `database.py` 为 SQLite/MySQL 创建以下 9 张表：

| 表 | 用途 | V1 处置 |
| --- | --- | --- |
| `pushed_items` | 已推送条目判重 | 保留兼容，报告投递将新增独立幂等键 |
| `fetch_records` | 按来源记录抓取数量 | 迁移到更完整的采集运行模型 |
| `settings` | 系统设置 | 保留；增加强类型热点配置层 |
| `push_channels` | 推送渠道配置 | 保留；敏感字段需加密/脱敏 |
| `custom_sources` | 自定义 RSS | 保留，划入 RSS Provider |
| `push_rules` | 推送过滤规则 | 保留，后续作用于事件/报告层 |
| `push_history` | 推送历史 | 保留兼容，扩展报告投递状态 |
| `users` | 用户和角色 | 保留 |
| `hot_item_snapshots` | 排名快照 | 兼容读取后迁移到 V1 快照模型 |

### 6.2 V1 新实体

命名可在 Phase 1/3 的迁移设计中调整，但语义不能合并：

| 实体 | 核心职责 |
| --- | --- |
| `collector_runs` | 一次平台采集运行的窗口、状态、耗时、最终 freshness |
| `provider_attempts` | 每次 Provider 尝试、顺序、错误、状态码、重试信息 |
| `raw_payloads` | 原始响应正文或对象存储引用、哈希、媒体类型 |
| `raw_hot_items` | 不可变原始热点；保留 Provider 原字段和原始载荷引用 |
| `snapshots` | 平台在 30 分钟窗口的一次观测 |
| `snapshot_items` | 快照与原始条目的成员关系及当次排名/热度 |
| `normalized_hot_items` | 标准标题、URL、数值热度、时间、语言等派生字段 |
| `dedup_groups` | 单平台/同 Provider 的确定性去重结果 |
| `events` | 跨平台热点事件主记录 |
| `event_members` | 事件与规范化条目的成员关系和匹配证据 |
| `trend_states` | 事件在各时间窗的生命周期、速度、加速度和评分 |
| `ai_classifications` | 分类、酒旅相关性、摘要、模型/提示词版本与证据 |
| `reports` | 日报/周报内容、版本、时间窗和生成状态 |
| `report_deliveries` | 飞书等渠道的幂等投递、响应、重试与失败记录 |

数据库约束：

- 所有时间用带时区 UTC 存储，展示层转换为 `Asia/Shanghai`。
- 原始层只追加，不物理更新业务字段；纠错通过新记录或派生层重建。
- 原始载荷必须有 SHA-256，允许压缩或转存，但不能无记录丢弃。
- 每个派生实体记录 `algorithm_version`/`config_version`，AI 结果另记录模型与提示词版本。
- 唯一约束不得仅依赖标题；至少包含平台、Provider、外部 ID 或稳定内容指纹。
- 生产迁移必须版本化，禁止继续只靠应用启动时的 `CREATE TABLE IF NOT EXISTS` 演进新结构。

## 7. 标准化、去重与聚类

### 7.1 标准化

确定性处理优先：Unicode 规范化、空白/标点归一、URL canonicalization、热度单位解析、平台时间解析、无损保留原字段。标准化失败只影响派生记录，不删除原始条目。

### 7.2 基础去重

Phase 4 只做低风险规则：同平台稳定外部 ID、canonical URL、严格标题指纹。规则和阈值配置化，并保留匹配原因。

### 7.3 跨平台事件聚类

禁止 LLM 对所有热点进行两两比较。候选生成采用确定性阻塞：时间窗、实体/关键词、字符 n-gram/MinHash 或向量近邻索引，只对小规模边界候选调用 AI 判断。聚类应满足：

- 每个成员保存候选召回原因、相似度和最终决策来源。
- AI 只能判断模糊边界，不能覆盖确定性冲突事实。
- 算法、阈值和特征权重全部配置化、版本化。
- 支持离线重放原始数据并比较聚类版本。

## 8. 趋势生命周期

趋势引擎只消费快照与事件成员，初始状态建议为：`emerging`、`rising`、`peaking`、`declining`、`dormant`、`recurrent`。评分候选维度：平台覆盖、排名、热度、上升速度、持续时间、新增内容量、可信度与 freshness。

任何评分公式、窗口、阈值、衰减和权重必须来自版本化配置。`stale` 数据不得增加实时速度或触发“正在上升”的结论。

## 9. AI 使用边界

允许：

- 事件边界候选的语义判断。
- 事件主题分类。
- 酒旅/住宿/文旅/本地生活相关性与理由。
- 基于已选事件证据的日报/周报摘要。

禁止：

- 全量热点两两比较。
- 用模型生成不存在的实时热点、热度或来源。
- 让模型直接决定 Provider 成功/失败或 freshness。
- 在没有来源证据时输出事实性趋势判断。

AI 输出必须结构化校验，并记录输入引用、模型、提示词版本、耗时和失败原因。AI 不可用时，分类/摘要状态为失败或待处理，核心采集链仍可运行。

## 10. API 基线与演进

现有 HotPush API 保留兼容：

- 公开：`/health`、`/api/sources`、`/api/categories`、`/api/hot`、`/api/hot/stream`、`/api/hot/{source_id}`、`/api/stats`。
- 认证：`/api/auth/login|register|logout|check|me`。
- 配置：`/api/config/settings`、`/api/config/push*`、`/api/config/push-sources`。
- 数据源：`/api/sources/custom*`、`/api/sources/validate`。
- 规则/历史：`/api/rules*`、`/api/history*`。
- 调度：`/api/scheduler/status|trigger|config|pause|resume|digest*|ai-config`。
- 趋势：`/api/trends/ranking/{source_id}`、`/item/{item_id}`、`/overview`、`/top`。
- 用户：`/api/users*`。

V1 新接口放入 `/api/v1/hotspots` 命名空间，预计包括：

- 平台、Provider、fallback 和 freshness 状态。
- 采集运行及 Provider 尝试记录。
- 原始热点与原始载荷审计读取。
- 快照、规范化条目、事件、趋势生命周期。
- AI 分类和酒旅相关性。
- 日报/周报与投递状态。

API 响应 freshness 最低要求：

```json
{
  "freshness": "stale",
  "observed_at": "2026-08-14T02:00:00Z",
  "served_at": "2026-08-14T03:10:00Z",
  "stale_reason": "all_providers_failed",
  "provider_attempt_ids": [101, 102]
}
```

## 11. Scheduler 基线与演进

HotPush 使用 APScheduler：一个间隔任务执行抓取和推送；摘要任务可配置；每日 03:00 清理旧快照。Compose 当前默认 `FETCH_INTERVAL_MINUTES=5`。

V1 要求：

- 默认改为 30 分钟，后台可配置，合法范围和时区明确。
- 采集任务使用窗口幂等键，避免多实例重复写入同一快照。
- 采集、后处理、报告生成、飞书投递分别调度和记录状态。
- 清理策略不得删除原始热点；只允许按明确保留策略归档原始载荷和清理可重建缓存。
- 多实例部署时使用数据库/Redis 锁和 misfire/coalesce 策略。
- 手动触发和定时触发使用同一业务入口。

## 12. 飞书基线与演进

现有 `FeishuPusher` 通过群机器人 Webhook 发送富文本 `post`，支持 AI 摘要和按平台分组。保留其 PushService 接口，但在 Phase 10 增加：

- webhook 签名/密钥能力和凭据脱敏。
- 超时、有限重试、指数退避和错误分类。
- 报告长度分片和飞书返回业务码校验。
- `report_id + channel + content_version` 幂等键。
- 完整投递记录、重放入口和告警。
- 日报/周报模板只消费 `Report`，不从实时 Collector 临时拼装。

## 13. 依赖与许可证边界

权威清单见根目录 `THIRD_PARTY.md`。工程边界如下：

- HotPush：MIT，作为代码基线，保留其 LICENSE、版权和上游历史。
- NewsNow、DailyHotApi：MIT，作为 Provider；优先调用稳定公开接口或编写最小适配，不整仓复制。
- OpenCLI：Apache-2.0，仅作为登录态备用 Provider；进程隔离，凭据不落业务日志。
- TrendRadar：GPL-3.0，仅允许参考公开功能和思想；不复制代码、配置、模板、测试或派生片段。
- MediaCrawler：非商业学习许可证；不得复制、集成、打包、部署或成为商业运行依赖。
- 平台服务条款、robots、账号授权、频率限制和个人信息处理义务独立于开源许可证，Phase 2 上线前必须完成合规复核。

Phase 0 安全审计补充：HotPush 导入时的前端锁文件曾报告 6 个已知问题（1 moderate、5 high）。Phase 0 修补提交已将 Vite、Vue 插件和 PostCSS 升级到无已知审计漏洞的兼容版本，更新传递依赖，并通过 `npm audit` 和生产构建；未使用 `npm audit fix --force`。

## 14. 建议文件变更清单

Phase 0 仅修改：

- `docs/HOTSPOT_V1_ARCHITECTURE.md`
- `docs/HOTSPOT_V1_TASKS.md`
- `THIRD_PARTY.md`

后续候选（实际按 Phase 提交）：

```text
backend/app/domain/hotspot/             领域枚举、值对象、状态模型
backend/app/collectors/                 Collector V2 编排与 fallback
backend/app/providers/                  Provider 合同、registry、各数据源 adapter
backend/app/repositories/hotspot/       原始与派生数据访问
backend/app/services/normalization/     标准化和确定性去重
backend/app/services/clustering/        候选生成、事件聚类
backend/app/services/trends/            生命周期和评分
backend/app/services/classification/    AI 分类边界
backend/app/services/reports/           日报/周报
backend/app/routers/hotspots_v1.py       V1 API
backend/migrations/                     版本化数据库迁移
backend/tests/hotspot/                  单元、契约、集成和重放测试
frontend/src/views/hotspot/              Dashboard 页面
frontend/src/stores/hotspot.js           V1 状态管理
config/hotspot/                          算法、阈值、权重配置
```

## 15. Phase 质量门禁

每个 Phase 必须按以下顺序完成，禁止跨 Phase 合并：

1. 完成该 Phase 的实现和测试。
2. 运行相关单元、契约、集成、迁移或前端构建测试。
3. 修复错误，记录无法自动验证的真实外部依赖。
4. 更新 `docs/HOTSPOT_V1_TASKS.md` 的完成项和遗留项。
5. 输出完成项、遗留问题和下一 Phase 文件计划。
6. 创建一个独立 Git commit。

测试或真实数据验证未通过时，该 Phase 保持未完成；不得用 sample/fake/mock 数据对外冒充生产结果。
