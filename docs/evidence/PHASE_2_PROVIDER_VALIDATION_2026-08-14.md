# Phase 2 Provider 真实验证证据

验证日期：2026-08-14

验证环境时区：Asia/Shanghai；记录时间为 UTC

主仓库分支：`hotspot-v1`

## 验证规则

- 只记录真实网络/进程结果，不把测试 fixture、sample、mock 或旧缓存冒充生产热点。
- 不在文档中保存热点标题、响应正文、cookie、token 或浏览器资料。
- 若有响应正文，只记录字节数和 SHA-256；原始字节由 `ProviderResult.raw_payload` 承载，Phase 3 再落 append-only 数据库。
- `failed` 结果的 `freshness=fresh` 表示本次失败尝试是当前发生的，不代表存在 fresh 数据；失败结果的 item count 必须为 0。

## 上游合同固定点

| Provider | 审计 commit / version | 许可证 | 本项目使用方式 |
| --- | --- | --- | --- |
| NewsNow | `2173126f804bec0201769f59d933add6c4632d17` | MIT | 原创 `/api/s?id=<platform>` HTTP adapter |
| DailyHotApi | `36c77e3bd891c11642d314cfb229bf31646704de` | MIT | 原创 `/<platform>` HTTP adapter |
| OpenCLI | `a86d64705c526dc710f790e66cfcabf6ecf786b9` / npm 1.8.6 | Apache-2.0 | 原创无 shell 子进程 adapter |

## 公共地址与本地登录态探测

执行入口：

```powershell
uv run --with-requirements requirements.txt python -m tools.validate_hotspot_providers
```

使用项目默认 HTTP 地址；OpenCLI 进程探测使用工作区已有、未跟踪的 `autocli 0.3.8` 兼容命令进行 adapter 端到端验证。该旧二进制不在 Git 或发行包中。当前官方 OpenCLI 另行验证见下一节。

| UTC 时间 | Provider | 平台 | 结果 | items | HTTP/错误 | raw bytes | raw SHA-256 |
| --- | --- | --- | --- | ---: | --- | ---: | --- |
| 08:20:52 | NewsNow | douyin | failed | 0 | HTTP 403 / `upstream:http_403` | 4548 | `c13a67aa857ba1678ad175c912fc6759dbd820af40ed2944ac83c0b46d97ad00` |
| 08:20:52 | DailyHotApi | douyin | failed | 0 | `connection:http_connection_error` | 0 | — |
| 08:20:56 | NewsNow | weibo | failed | 0 | HTTP 403 / `upstream:http_403` | 4548 | `884ff32000cac1a33403f3585060eb3c46c876feffc508ea601ed42ef16d5c3d` |
| 08:20:56 | DailyHotApi | weibo | failed | 0 | `connection:http_connection_error` | 0 | — |
| 08:21:00 | NewsNow | bilibili | failed | 0 | HTTP 403 / `upstream:http_403` | 4548 | `b0631069dd29154f79a5280827177155933e2d9aa979d977df19b1b693a8c113` |
| 08:21:01 | DailyHotApi | bilibili | failed | 0 | `connection:http_connection_error` | 0 | — |
| 08:21:05 | OpenCLI-compatible process | xiaohongshu | failed | 0 | `configuration:opencli_bridge_unavailable` | 182 | `af4aada8710cffb3638f461757f6e4525d3302fb4524bf28100835b2a7199c79` |

NewsNow 三次响应均为 Cloudflare HTML 403，不是热点 JSON。DailyHotApi 的文档公共 hostname `api-hot.imsyy.top` 在当前环境无法解析，adapter 因而记录连接失败。

## DailyHotApi 未修改本机上游副本

为区分“公共部署失效”和“adapter 合同错误”，使用 commit `36c77e3...` 的未修改研究副本在 `localhost:16688` 启动服务，然后由本项目的真实 `DailyHotApiProvider` 请求三条路由。研究副本没有复制到主仓库。

| UTC 时间 | 平台 | 本机服务结果 | items | raw bytes | 空正文 SHA-256 |
| --- | --- | --- | ---: | ---: | --- |
| 08:17:18 | douyin | HTTP 502 / retryable upstream failure | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 08:17:19 | weibo | HTTP 502 / retryable upstream failure | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 08:17:24 | bilibili | HTTP 502 / retryable upstream failure | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

这证明本机服务路由可达，但其对平台上游的真实请求失败；不能用本机启动成功替代平台数据成功。

## 当前官方 OpenCLI 验证

- `npm view @jackwener/opencli version license engines --json`：版本 `1.8.6`，Apache-2.0，Node.js `>=20.0.0`。
- `npx -y @jackwener/opencli@1.8.6 --version`：成功输出 `1.8.6`。
- `npx -y @jackwener/opencli@1.8.6 xiaohongshu feed --limit 5 --format json`：退出码 69，错误码 `BROWSER_CONNECT`，Browser Bridge extension 未连接。
- 工作区旧 `autocli 0.3.8` 通过相同站点/命令合同也报告 Chrome extension/daemon 未连接。

因此小红书没有 live item；没有回退到假数据、sample 或旧缓存。

## 结论

- 四个平台的可替换 Provider 合同、错误分类、原始响应保留和 fallback 已完成并由自动化测试覆盖。
- 本次外部环境没有一个平台取得可证明的 live 数据，生产可用性状态为受限。
- 下一次真实验收必须提供可访问的自建 NewsNow/DailyHotApi 地址，或在已授权 Chrome profile 中连接 OpenCLI Browser Bridge；成功前 Dashboard/报告/飞书不得显示实时热点。
