# 四平台真实采集验证（2026-08-25）

## 验证范围

- 环境：本项目 Docker Compose，MySQL/Redis/RSSHub/DailyHotApi/Backend/Frontend。
- 触发入口：`POST /api/scheduler/hotspots/trigger`。
- 数据要求：只统计落入 Collector V2 的 `ProviderAttempt`、`RawPayload`、`RawHotItem` 和 Snapshot；不把测试 fixture、旧 HotPush RSS 表或页面示例计为实时结果。
- Freshness：Provider 必须提供满足其合同的最新证据；缓存或超龄数据标记 stale，失败写零条实时数据。

## 结果

| 平台 | 结果 | Winning Provider | 条目数 | Raw payload 字节数 | Raw payload SHA-256 |
| --- | --- | --- | ---: | ---: | --- |
| douyin | success / fresh | dailyhotapi | 50 | 9,846 | `1444c5ff764b432471e862291f1ffdfa856422b200d978fcf0068d70f61c05f5` |
| weibo | success / fresh | rsshub | 51 | 25,928 | `788fe67724976d7a9743f88a41a1f4729aaa35e810092d9d6c55e0b0a00e8e9a` |
| bilibili | success / fresh | rsshub | 10 | 6,403 | `993827d489220c7091edde24f73c4ed22a68dcb2512849cf2890f801f87ad8f3` |
| xiaohongshu | failed | opencli | 0 | 0 | 无成功 payload |

对应采集 run：

- douyin：`c6b4ad56-8dd0-485d-9782-2564bf01e66f`
- weibo：`eb5870ca-fb30-4619-b58d-f3302cce4286`
- bilibili：`72df9b09-4e03-49ad-91db-f87557913276`
- xiaohongshu：`6553b19b-68ca-4da0-b343-b4db5594aab2`

## 小红书未完成项

OpenCLI 1.8.7 与本机认证桥接器均可启动，但 Chrome Browser Bridge 扩展未连接；直接调用返回 `BROWSER_CONNECT`（exit 69）。因此该轮保持 failed，不使用缓存、其他平台内容或模拟数据代替。完成官方扩展安装、登录小红书并把桥接 URL/Token 提供给 Docker 后端后，需要再次执行同一验证并补录成功 payload 的长度与 SHA-256。

## Provider 可替换性验证

- 微博、B站优先 RSSHub，失败后仍按 DailyHotApi、NewsNow 顺序留有独立 attempt。
- 抖音优先独立 DailyHotApi 服务，失败后回退 NewsNow。
- 小红书只使用需要登录态的 OpenCLI，不把没有该平台合同的 Provider 作为伪 fallback。
- 每次 attempt 和原始响应分别存储，聚合、标准化和业务逻辑不依赖具体 Provider 类型。
