# HotPush 多平台热点情报中心 V1 运行手册

> 对应 `docs/HOTSPOT_V1_TASKS.md` Phase 0–11。本手册面向部署与值班运维。

## 1. 架构速览

```text
Provider(NewsNow/DailyHotApi/OpenCLI)
  -> Collector V2（编排、fallback、stale 边界）
  -> 版本化迁移 + 原始层（append-only）
  -> Normalization -> Dedup -> Clustering -> TrendEngine -> AI Classification
  -> Dashboard API
  -> ReportEngine（日报/周报）
  -> FeishuDelivery（签名/分片/幂等投递）
  -> Monitoring（指标/告警/健康检查）
```

分层铁律：**派生层永不回写原始层**；**stale 数据永不冒充实时**；**报告只消费版本化事件与趋势**；**测试 fixture 永不对外冒充生产数据**。

## 2. 启动与配置

### 环境要求

- Python 3.11+（开发建议 uv 管理）
- Node.js 18+（前端）
- MySQL 8.0+ 与 Redis 6.0+（生产）；本地可用 SQLite（`DATABASE_URL=sqlite:///hotpush.db`）

### 本地开发

```bash
cd backend
uv venv --python 3.11 .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
cp .env.example .env            # 修改 DATABASE_URL / JWT_SECRET / ADMIN_PASSWORD
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
cd ../frontend && npm install && npm run dev
```

### Docker 部署

```bash
docker compose up -d
# 首次部署后必须修改 docker-compose.yml 中的 ADMIN_PASSWORD 与 JWT_SECRET
```

### 关键配置（settings 表 / 环境变量）

| 配置键 | 默认 | 说明 |
| --- | --- | --- |
| `hotspot_collection_interval_minutes` | 30 | V2 采集间隔（1–1440） |
| `hotspot_ai_classification_enabled` | false | AI 分类开关（默认关闭，不产生费用） |
| `hotspot_report_max_items` | 30 | 报告事件上限 |
| `hotspot_feishu_webhook_url` / `hotspot_feishu_secret` | - | 飞书报告投递与签名密钥 |
| `hotspot_delivery_max_retries` | 2 | 投递重试上限（0–5） |
| `hotspot_alerts_enabled` | false | 告警评估开关 |
| `HOTSPOT_STRUCTURED_LOGS` | 未设置 | 设为 `1` 启用 JSON 结构化日志 |

## 3. 定时任务

| 任务 ID | 频率 | 说明 |
| --- | --- | --- |
| `fetch_and_push` | 5 分钟 | HotPush 兼容抓取推送（旧链路） |
| `hotspot_collect_v2` | 30 分钟 | 采集→标准化→聚类→趋势→分类→告警检查 |
| `hotspot_report_daily` | 每天 01:00 (Asia/Shanghai) | 热点日报生成 |
| `hotspot_report_weekly` | 每周一 01:00 | 热点周报生成 |
| `cleanup_snapshots` | 每天 03:00 | 旧快照清理（不删原始数据） |

手动触发：`/api/scheduler/hotspots/trigger`；报告重跑：`POST /api/v1/hotspots/reports/{daily|weekly}/regenerate`；报告投递：`POST /api/v1/hotspots/reports/{report_run_id}/deliver`。

## 4. 监控

### 端点

| 端点 | 鉴权 | 说明 |
| --- | --- | --- |
| `GET /health` | 公开 | liveness |
| `GET /health/ready` | 公开 | 就绪（数据库连通） |
| `GET /api/v1/hotspots/monitoring/metrics` | 公开 | Prometheus 文本（运行时指标） |
| `GET /api/v1/hotspots/monitoring/summary` | 登录 | Provider 成功率/延迟/空榜/stale 年龄/fallback、管线状态 |
| `GET /api/v1/hotspots/monitoring/alerts` | 登录 | 当前告警评估 |
| `GET /api/v1/hotspots/monitoring/health` | 登录 | V1 管线健康视图 |

### 告警规则（settings）

| 规则 | 配置键 | 默认 |
| --- | --- | --- |
| 平台数据陈旧 | `hotspot_alert_max_stale_minutes` | 180（3 倍以上升 critical） |
| Provider 成功率过低 | `hotspot_alert_min_provider_success_rate` | 0.5（样本 ≥3 才评估） |
| 采集失败次数 | `hotspot_alert_max_failed_runs` | 3 |
| 标准化积压 | `hotspot_alert_max_pending_snapshots` | 12 |
| 投递失败 | 存在 failed 投递即告警 | - |

告警 webhook：`hotspot_alert_webhook`（可选）。通知去重：指纹存 `hotspot_alert_last_fingerprint`，变化才推送。

## 5. 故障处理

| 症状 | 排查步骤 |
| --- | --- |
| 某平台显示"采集失败" | `docker compose logs backend`；检查 `hotspot_provider_order_<platform>` 与 Provider 连通性；Dashboard 会如实显示失败，不伪造实时 |
| 数据"陈旧" | 查看 `stale_reason`（Provider 缓存 / 快照年龄 / 最近失败）；更新 Cookie 或等待下一窗口 |
| 报告未生成 | `GET /api/v1/hotspots/reports` 查看最近 run；`POST .../regenerate` 手动重跑；检查 `hotspot_report_version` 与数据完整性 |
| 投递失败 | `GET /api/v1/hotspots/deliveries?status=failed` 查看 error_kind/business code；检查 webhook URL 与签名密钥；`POST /api/v1/hotspots/deliveries/{id}/replay` 重放 |
| AI 分类失败 | 不影响采集链；检查 `hotspot_ai_*` 配置与模型输出 schema |
| 多实例重复采集 | 数据库窗口锁 + APScheduler max_instances=1 + coalesce 自动处理 |

## 6. 备份与恢复

- 原始层为 append-only，派生层可重建：先备份原始库，再按需重跑 Normalization→Clustering→Trend→Classification→Report。
- SQLite：文件复制即备份；恢复 = 用备份文件替换后启动（迁移幂等，启动自动补齐）。
- MySQL：使用 `mysqldump` 全量备份；迁移回滚等价于从备份重建（所有迁移可从头应用，见 `test_fault_recovery.py`）。
- 迁移漂移保护：已应用迁移的 SHA-256 校验和变化会触发 `MigrationDriftError`，禁止篡改历史迁移文件。

## 7. 回滚

- 代码回滚：`git revert` 对应 `feat(phase-N)` 提交；数据库向后兼容（新表不会破坏旧代码读取）。
- 数据回滚：派生层（快照后的所有表）可直接清空重建；原始层（`hotspot_raw_*`、`hotspot_collection_runs`）不可物理回滚，纠错通过新记录。

## 8. 质量门禁（每个 Phase 提交前）

1. 该 Phase 实现与测试完成
2. `pytest -q` 全量通过（当前 292 tests）
3. 前端 `npm test` + `npm run build` 通过
4. 更新 `docs/HOTSPOT_V1_TASKS.md`（完成项/遗留项/测试证据/commit）
5. 独立 Git commit

## 9. 已知限制（上线前复核）

- 四平台真实 live 数据依赖公开 Provider 可用性（见 Phase 2 证据），Dashboard/报告会如实标记失败与 stale。
- 平台条款、账号授权与个人信息采集合规性需业务负责人复核。
- AI 分类/摘要默认关闭；启用前需完成人工评测集验收（Phase 7）。
- 生产告警通道目前仅飞书 webhook（Phase 11 基础版）。
