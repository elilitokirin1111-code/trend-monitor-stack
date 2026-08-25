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

Phase 3 已将原始层实体落为 `hotspot_*` 独立表；后续派生层仍不得与原始层合并：

| 实体 | 核心职责 |
| --- | --- |
| `hotspot_collection_runs` | 一次平台采集运行的窗口、状态、耗时、最终 freshness |
| `hotspot_provider_attempts` | 每次 Provider 尝试、顺序、错误、状态码、重试信息 |
| `hotspot_raw_payloads` | 原始响应正文、SHA-256 和媒体类型 |
| `hotspot_raw_items` | 不可变原始热点；保留 Provider 原字段和原始载荷哈希 |
| `hotspot_snapshots` | 平台在 30 分钟窗口的一次 fresh 观测 |
| `hotspot_snapshot_members` | 快照与原始条目的成员关系及当次顺序 |
| `hotspot_normalization_runs` | 快照、规则版本、配置哈希、处理状态和计数 |
| `hotspot_normalized_items` | 标准标题、URL、数值热度、时间精度、warning 等派生字段 |
| `hotspot_dedup_groups` | 快照内低误判的确定性去重结果和代表项 |
| `hotspot_dedup_members` | 去重成员、匹配类型、对象和哈希证据 |
| `hotspot_clustering_runs` | 聚类输入哈希、算法/配置版本、窗口、状态和规模计数 |
| `hotspot_cluster_candidates` | 有界召回原因、确定性分数、语义边界状态和最终决策 |
| `hotspot_events` | 某次版本化聚类运行产出的跨平台热点事件 |
| `hotspot_event_members` | 事件与 Phase 4 去重组代表项的成员关系 |
| `hotspot_trend_runs` | 一次版本化趋势评估的聚类来源、采集水位、配置/输入哈希和状态计数 |
| `hotspot_trend_states` | 事件序列在各评估水位的生命周期、特征、质量和跨运行 lineage |
| `hotspot_classification_runs` | 一次版本化 AI 分类的趋势来源、模型/提示词/配置/输入哈希和状态计数 |
| `hotspot_ai_classifications` | 逐事件分类、酒旅相关性、摘要、证据引用、响应、token/成本、耗时与失败 |
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

Phase 5 已采用字符 n-gram 倒排表和关键词特征落地有界召回：每个倒排键限制 posting 数，每个输入限制候选数，因此候选对最多为 `输入数 × max_candidates_per_item`，不会枚举全量组合。精确标题或 canonical URL 直接进入确定性高置信路径；其余候选按标题序列、n-gram、关键词和时间相似度加权。只有 `[semantic_lower_threshold, accept_threshold)` 灰区且显式开启语义端口时才会调用 AI。

语义端口未配置、调用超时、结果类型非法或预算耗尽时，候选保守拒绝并记录 `unavailable/error/invalid/budget_exhausted`；不得用模型失败制造事件合并。默认不启用语义端口，Phase 5 也不接入分类或摘要模型。

## 8. 趋势生命周期

Phase 6 的趋势引擎只消费版本化 Phase 5 事件成员和其 Phase 3 真实快照观测，状态为：`emerging`、`rising`、`peaking`、`declining`、`dormant`、`recurrent`。它不读取 Provider 临时响应，也不与 HotPush 兼容 `/api/trends` 的 `hot_item_snapshots` 评分混用。

每条 fresh 观测先根据名次和对数热度得到有界基础强度，再按 30 分钟桶计算 current/previous/earlier strength、速度和加速度。事件特征另含平台覆盖、持续度、观测数、最近 fresh 年龄、复发间隔，以及本评估水位的失败/stale/缺失平台计数和完整度。趋势总分默认由当前强度、平台覆盖、正速度、正加速度和持续度加权，所有窗口、阈值、权重与算法版本均来自 `hotspot_trend_*` settings 并进入稳定配置哈希。

freshness 是硬边界：只有 `fresh` 观测能贡献强度、速度和加速度；`stale` 只保存为质量证据，不能触发 rising。最新采集运行是评估水位，因此失败采集在不创建快照的前提下仍能推进事件年龄并触发 declining/dormant。若没有 fresh 证据，质量明确标为 `stale_only` 或 `no_fresh_data`，不得伪造实时趋势。

Phase 5 event ID 隶属于单次聚类运行。Phase 6 使用共享去重组重叠优先、代表指纹兜底的确定性 lineage 建立稳定 `trend_series_id`，并保存匹配类型、重叠数、上一事件和上一状态。复发状态要求既有 dormant 历史且 fresh 证据在配置化间隔后重新出现；旧 Phase 5/6 结果都不回写。

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

Phase 7 已把分类实现为 `ClassificationProvider` 可替换端口；业务服务只消费版本化趋势状态和不可变事件成员，不读取 Provider 临时响应，也不允许模型修改趋势或 freshness。生产适配器复用已有 LiteLLM，但默认独立关闭，旧摘要开关不会触发分类费用。

输出字段集合固定为 `category/tags/hospitality_relevance/hospitality_score/confidence/rationale/summary/evidence_ids`。响应必须是严格 JSON，证据 ID 必须是当前事件成员；Markdown 包裹、额外/缺失字段、非法类型或证据越界均保存为失败而不是猜测修复。主题类别、酒旅相关性和摘要属于派生判断，Dashboard/报告必须同时显示输入证据和数据质量。

运行按 `source_trend_run + classifier_version + prompt_version + model + config_hash + input_hash` 幂等，并在外部调用前检查已有 run。逐事件记录保存实际模型、request/response hash、完整模型响应、结构化决定、耗时、token、可用时的成本和独立错误码。禁用、缺 Key、超时、限流、Provider 异常、非法 JSON 和 schema 漂移不会阻断其余事件或上游数据链。

Phase 7 的固定评测资源含 12 条可人工审阅标签，ground truth 与预测分离，离线 evaluator 只比较分类与相关性并将缺失预测计错；它不是模型自评，也不是生产热点。真实模型上线仍需业务负责人扩充/复核标注集并设定验收阈值。

## 10. API 基线与演进

现有 HotPush API 保留兼容：

- 公开：`/health`、`/api/sources`、`/api/categories`、`/api/hot`、`/api/hot/stream`、`/api/hot/{source_id}`、`/api/stats`。
- 认证：`/api/auth/login|register|logout|check|me`。
- 配置：`/api/config/settings`、`/api/config/push*`、`/api/config/push-sources`。
- 数据源：`/api/sources/custom*`、`/api/sources/validate`。
- 规则/历史：`/api/rules*`、`/api/history*`。
- 调度：`/api/scheduler/status|trigger|hotspots/trigger|config|pause|resume|digest*|ai-config`；`config` 已支持独立 V2 快照频率。
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

HotPush 使用 APScheduler：一个间隔任务执行抓取和推送；摘要任务可配置；每日 03:00 清理旧快照。该兼容任务仍使用 `FETCH_INTERVAL_MINUTES=5`。Phase 3 新增独立 `hotspot_collect_v2` 任务，默认 `HOTSPOT_COLLECTION_INTERVAL_MINUTES=30`，避免改变旧推送语义。该 V2 任务当前按 `Collection -> Normalize -> EventCluster -> TrendEngine -> AI Classification` 顺序执行并分别保存最近状态；AI 失败不回滚已完成的上游阶段。

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
backend/app/clustering/                 候选召回、确定性评分、语义边界端口和事件聚类
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

## 16. Phase 2 Provider 实现

Phase 2 只把外部数据转换为 `ProviderResult`，不写快照、不做标准化、聚类、趋势、AI、报表或推送。

| 平台 | 默认 Provider 链 | 当前能力边界 |
| --- | --- | --- |
| douyin | `newsnow -> dailyhotapi` | 两个 HTTP 合同均实现；公开实例当前不可用时明确失败 |
| weibo | `newsnow -> dailyhotapi` | 同上；HTTP 403/429/5xx 分开分类 |
| bilibili | `newsnow -> dailyhotapi` | 同上；保留上游原始 item 和完整响应 |
| xiaohongshu | `opencli` | 仅使用登录态首页推荐 feed；Browser Bridge/登录失效时失败，不伪装成热榜成功 |

Provider 默认顺序可以由现有后台 settings 形状覆盖：

- `hotspot_provider_order_<platform>`：逗号分隔 Provider ID。
- `hotspot_newsnow_base_url`：NewsNow 公共或自建地址。
- `hotspot_newsnow_trust_success_as_fresh`：默认 `false`。仅当管理员能证明自建实例不会返回缓存时开启。
- `hotspot_dailyhotapi_base_url`：DailyHotApi 公共或自建地址。
- `hotspot_opencli_executable`：外置 OpenCLI 可执行文件路径；不通过 shell 执行。
- `hotspot_opencli_limit`：单次获取上限，合法范围 1–100。

## 17. Phase 3 快照持久化实现

Phase 3 在 Collector 端口之后新增 `HotspotRepository`，不改变 Provider 或 Collector 对数据库的认知。每次 Provider 尝试先保存运行、错误、原始响应字节、SHA-256 和原始条目，再决定是否创建窗口快照。

快照规则：

- 窗口为 UTC 半开区间 `[start, end)`，默认 30 分钟，设置键 `hotspot_collection_interval_minutes` 可在后台调整为 1–1440 分钟。
- 只有 `fresh` 且非失败的 Collector 结果创建 `hotspot_snapshots`；真实空榜允许创建零成员快照，表示该窗口已成功观测为空。
- `stale` 回退只记录本次运行和实际 Provider 尝试，不复制历史成员形成新快照；历史数据通过原快照 ID 返回并明确标记 `stale`。
- 所有运行和原始证据均保留；同一窗口发生额外采集时仍保存新的原始运行，但唯一窗口快照保持不变。
- `hotspot_collection_locks` 是可过期、按 owner 释放的操作锁表，不属于 append-only 原始业务数据。

Scheduler 保留 HotPush 原有 `fetch_and_push` 兼容任务，并新增 `hotspot_collect_v2`。两者频率分别配置；暂停/恢复会同时作用于两项任务，手动 V2 入口与定时任务调用同一个应用服务。V2 任务限制单实例执行并开启 coalesce/misfire 控制，数据库窗口锁负责跨进程互斥。

## 18. Phase 4 标准化与基础去重实现

Phase 4 只消费 fresh `hotspot_snapshots` 的成员，不扫描未获选 Provider 条目，也不把 stale 重放转成新派生窗口。`HotspotNormalizationService` 查询当前规则版本和配置哈希尚未处理的快照，通过纯函数 `HotspotNormalizer` 生成完整批次，再由 `NormalizationRepository` 单事务追加派生结果。

规则与证据：

- `hotspot_normalization_rule_version` 和 `hotspot_dedup_algorithm_version` 控制语义版本；tracking 参数、热度单位和平台时间字段可通过现有 settings API 配置。
- 配置序列化采用稳定排序并保存 SHA-256；同一快照、规则和配置只有一个成功落库批次，竞态写入由数据库唯一约束收敛。
- 每个 raw 快照成员都产生 success、partial 或 failed 标准化记录；失败不删除 raw，warning 与错误码随派生记录保存。
- 去重键按平台作用域构建；外部 ID 额外按 Provider 作用域，避免不同 Provider 的 ID 空间碰撞。
- 候选召回使用哈希表，连通分量使用并查集；算法不会枚举所有热点对，也没有 LLM 依赖。
- 每个非失败标准化项恰好属于一个去重组，包括单例组；代表项与所有成员证据均受领域合同和数据库外键约束。

本阶段的去重组不是跨平台事件。Phase 5 只能读取版本化标准化/去重结果建立有界候选集，不能直接修改 Phase 4 记录或回退到全量 LLM 两两比较。

## 19. Phase 5 跨平台事件聚类实现

Phase 5 只读取与当前 `NormalizationRules` 版本、配置哈希完全匹配的 `hotspot_dedup_groups` 代表项。输入窗口以该版本最新真实 `observed_at` 为锚，默认回看 48 小时；这使旧快照可以离线回放，也避免用当前墙上时间误删历史输入。聚类不会重新扫描 Phase 3 raw item，也不会修改 Phase 4 派生记录。

候选与决策边界：

- 默认候选时间窗 36 小时、每条最多 20 个候选、每个倒排键最多保留 200 个 posting；以上参数均可通过现有 settings API 修改并进入稳定配置哈希。
- 候选由严格标题、canonical URL 和字符 n-gram 倒排召回；同一 Phase 4 快照内的条目不重复聚类。
- 确定性分数默认由标题序列 0.45、n-gram 0.35、关键词 0.15、时间 0.05 加权，默认灰区下界 0.68、自动接受阈值 0.82。
- 直接接受、直接拒绝、语义接受/拒绝和降级拒绝均保存原因、分数组件与可选模型证据；并查集只连接明确接受的边。
- 每个输入去重组恰好属于一个事件，包括单例；事件标题仅取确定性代表项，不由 AI 生成。

运行采用 `algorithm_version + config_hash + normalization_config_hash + input_hash` 幂等。同一输入和配置重跑跳过；配置或输入变化会追加新的 `hotspot_clustering_runs`、事件、成员和候选证据，旧运行保持可审计。Scheduler 在标准化后调用独立 `HotspotClusteringService`，聚类失败只记录明确失败结果，不伪造事件，也不阻断后续窗口重试。

Phase 5 未实现跨运行稳定事件 ID 或趋势生命周期；当前 event ID 隶属于某次版本化聚类运行。Phase 6 应消费连续运行的事件成员与窗口观测，建立生命周期状态和跨运行关联，不得回写 Phase 5 历史结果。

## 20. Provider Freshness 保守证据补充

Freshness 采用保守证据规则：

- NewsNow 的源码路径会在刷新间隔内从缓存返回 `status=success`，因此默认结果仍标记 `stale`；`status=cache` 必为 `stale`。
- DailyHotApi 的 `fromCache=true` 必为 `stale`，`false` 才可为 `fresh`。
- OpenCLI 只有进程成功、输出为合法 JSON 数组且条目合同有效时才为 `fresh`。
- Provider 2xx 但响应缺字段、类型漂移或全部条目非法时为失败；部分非法时为 partial。
- HTTP/CLI 失败的响应体也保留在 `ProviderResult.raw_payload`，但验证工具只输出长度和 SHA-256，不泄漏原文。

公开 Provider 的在线可用性不作为代码成功的替代证据。2026-08-14 的真实验证结果记录在 `docs/evidence/PHASE_2_PROVIDER_VALIDATION_2026-08-14.md`；当时四个平台均未取得可证明的 live 数据，因此任何 Dashboard、报告或推送都不得把本阶段测试 fixture 当成生产热点。

## 21. 四平台采集可用性修补（2026-08-25）

运行审计发现原默认链路在当前网络中无法完成生产采集：NewsNow 公共服务被 Cloudflare 拒绝，DailyHotApi 公共域名连接失败，Docker 后端没有 OpenCLI 可执行环境。旧 HotPush 的 5 分钟 RSS 抓取虽能取得部分微博/B站数据，但不进入 `RawHotItem → Snapshot` 链路。修补后 Collector V2 仍是唯一写入热点情报表的入口。

默认 Provider 顺序如下，后台保存的显式配置仍可覆盖：

| 平台 | Provider 顺序 | 证据/边界 |
| --- | --- | --- |
| douyin | DailyHotApi → NewsNow | 独立 DailyHotApi 容器；`fromCache=true` 必为 stale |
| weibo | RSSHub → DailyHotApi → NewsNow | RSS `lastBuildDate` 超龄或缺失即 stale |
| bilibili | RSSHub → DailyHotApi → NewsNow | RSS `lastBuildDate` 超龄或缺失即 stale |
| xiaohongshu | OpenCLI | 必须使用已登录 Chrome；失败不回填旧榜单或假数据 |

DailyHotApi 与 RSSHub 均保持为独立、可替换的网络服务，应用仓库只包含自行实现的 Provider 合同适配器，没有复制上游采集代码。RSSHub 当前使用 AGPL-3.0 上游容器，许可证和网络服务边界记录在 `THIRD_PARTY.md`。

小红书采用主机桥接而不是把浏览器 Profile/Cookie 注入容器：主机上的 OpenCLI 连接 Chrome 官方 Browser Bridge，应用容器只向 `HOTSPOT_OPENCLI_BRIDGE_URL` 发送带 `HOTSPOT_OPENCLI_BRIDGE_TOKEN` 的固定只读请求。桥接器只映射预定义平台命令，不接受调用方提供的 shell 或写操作。未配置桥接、认证失败、扩展断开或登录过期都返回明确 Provider 失败。

新增运行配置：

- `HOTSPOT_DAILYHOTAPI_BASE_URL`
- `HOTSPOT_RSSHUB_BASE_URL`（兼容已有 `RSSHUB_URL`）
- `HOTSPOT_RSSHUB_MAX_AGE_MINUTES`
- `HOTSPOT_OPENCLI_BRIDGE_URL`
- `HOTSPOT_OPENCLI_BRIDGE_TOKEN`

本次实采证据见 `docs/evidence/PLATFORM_COLLECTION_2026-08-25.md`。抖音、微博、B站取得 fresh 原始数据；小红书因 Chrome 扩展未连接保持 failed，零条实时数据。
