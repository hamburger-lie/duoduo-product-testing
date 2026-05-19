# 生产级升级任务清单 (Production Upgrade Tasks)

> 项目：多角色 AI 测品工具  
> 目标：将 MVP 升级为生产级后端  
> 执行方式：每个任务由 Codex 独立执行，任务之间无依赖（除非标注）  
> 约束：**严格遵守 AGENTS.md 所有规则，不改 API 契约，不删现有功能**

---

## 执行须知（Codex 必读）

1. 每个任务是**独立的一个 PR**，分支命名 `prod/<任务编号>`（如 `prod/p0-01`）
2. 每个任务完成后必须通过：`uv run ruff check .` + `uv run mypy app` + `uv run pytest`
3. 不允许修改 `API_CONTRACT.md` 中定义的接口路径、请求参数、响应格式
4. 不允许删除现有测试、现有功能
5. 新增代码必须有对应测试
6. 所有新文件必须有 `from __future__ import annotations`
7. 所有 IO 使用 async
8. 遵守架构分层：`routers → services → ai/db/tasks/storage → core`

---

## P0 — 上线底线（必须完成才能上线）

---

### P0-01：AI 客户端熔断器

**问题**：`ArkOpenAIClient` 调用 DeepSeek / 智谱 API 时，如果对方服务持续故障或高延迟，所有请求会堆积等待超时，拖垮整个后端。

**目标**：为 AI 客户端引入 Circuit Breaker 模式。

**修改文件**：
- 新建 `backend/app/ai/circuit_breaker.py`
- 修改 `backend/app/ai/client.py`（在 `ArkOpenAIClient` 的 `complete`、`complete_json`、`stream` 方法外层包装熔断器）
- 新建 `backend/tests/test_circuit_breaker.py`

**技术方案**：

```python
# backend/app/ai/circuit_breaker.py
"""
轻量级异步 Circuit Breaker，不引入外部依赖。

三种状态：
- CLOSED（正常）：请求正常通过，统计失败次数
- OPEN（熔断）：直接拒绝请求，抛出 AIServiceUnavailable
- HALF_OPEN（半开）：允许一个探测请求，成功则恢复 CLOSED，失败则回到 OPEN

配置参数：
- failure_threshold: int = 5    # 连续失败多少次后熔断
- recovery_timeout: float = 30.0  # 熔断后多少秒进入半开状态
- success_threshold: int = 2    # 半开状态连续成功多少次后恢复
"""
```

**约束**：
- 不引入外部依赖（不用 pybreaker、tenacity 等），纯 Python 实现
- 熔断器实例挂在 `ArkOpenAIClient` 上，每个 client 实例独立
- 熔断时抛出 `AIServiceUnavailable("Circuit breaker is open")`
- 必须是线程安全的（使用 `asyncio.Lock`）
- 熔断状态变化时打日志：`logger.warning("circuit_breaker_state_change from=%s to=%s")`

**测试要求**：
- 测试 CLOSED → OPEN 转换（连续失败 N 次后熔断）
- 测试 OPEN 状态直接拒绝请求
- 测试 OPEN → HALF_OPEN 转换（等待 recovery_timeout 后）
- 测试 HALF_OPEN → CLOSED 恢复
- 测试 HALF_OPEN → OPEN 回退

**验收标准**：
- `uv run ruff check .` 通过
- `uv run mypy app` 通过
- `uv run pytest` 全部通过（包括新测试）
- 熔断器不影响 mock AI 客户端（MockAIClient 不走熔断）

---

### P0-02：JWT Token 吊销机制

**问题**：JWT 签发后 7 天内无法主动失效。用户登出、改密码、账号被盗等场景下 token 仍可使用。

**目标**：通过 Redis 黑名单实现 token 吊销，新增 logout 端点。

**修改文件**：
- 新建 `backend/app/core/token_blacklist.py`
- 修改 `backend/app/core/security.py`（`decode_access_token` 后检查黑名单）
- 修改 `backend/app/routers/auth.py`（新增 `POST /api/v1/auth/logout`）
- 修改 `backend/app/services/auth_service.py`（新增 `logout` 方法）
- 新建 `backend/tests/test_token_blacklist.py`

**注意**：`POST /api/v1/auth/logout` 是新端点，不在当前 API_CONTRACT.md 中。这是安全基础设施，允许新增。响应格式遵守现有错误码规范。

**技术方案**：

```python
# backend/app/core/token_blacklist.py
"""
Redis-based JWT token blacklist.

当用户登出时，将 token 的 jti (JWT ID) 存入 Redis，
key 格式: "bl:{jti}"，TTL = token 剩余有效时间。

token 过期后 Redis key 自动删除，不会无限增长。
"""

async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """将 token 加入黑名单。TTL = expires_at - now。"""
    ...

async def is_blacklisted(jti: str) -> bool:
    """检查 token 是否在黑名单中。Redis 不可用时返回 False（fail-open）。"""
    ...
```

**约束**：
- Redis 不可用时 fail-open（放行），不阻塞正常请求
- 黑名单检查在 `get_current_user` 中执行，位于 `decode_access_token` 之后
- 黑名单 key 的 TTL = token 的 `exp` 减去当前时间（token 过期后自动清理）
- logout 端点需要认证（只有登录用户才能登出）
- logout 响应：`{"message": "ok"}`，状态码 200
- 测试环境（APP_ENV=testing）跳过黑名单检查，与限速器逻辑一致

**测试要求**：
- 测试 logout 成功后，同一 token 再请求返回 401
- 测试 Redis 不可用时 fail-open
- 测试 token 过期后 blacklist key 自然清理（mock time）

**验收标准**：
- 现有 299 个测试全部通过（logout 不影响现有流程）
- 新增测试覆盖上述场景
- `uv run ruff check .` + `uv run mypy app` 通过

---

### P0-03：Prometheus 指标收集

**问题**：没有任何运行时指标，无法监控 API 性能、错误率、AI 调用延迟等。

**目标**：集成 Prometheus 指标，暴露 `/metrics` 端点。

**修改文件**：
- `backend/pyproject.toml`（新增依赖 `prometheus-client`）
- 新建 `backend/app/core/metrics.py`
- 修改 `backend/app/main.py`（注册 metrics 中间件和 `/metrics` 路由）
- 新建 `backend/tests/test_metrics.py`

**技术方案**：

```python
# backend/app/core/metrics.py
"""
Prometheus metrics for the application.

暴露以下指标：
- http_requests_total (Counter): labels=[method, path_template, status_code]
- http_request_duration_seconds (Histogram): labels=[method, path_template]
  buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
- ai_requests_total (Counter): labels=[provider, endpoint_id, status]
- ai_request_duration_seconds (Histogram): labels=[provider, endpoint_id]
- celery_tasks_total (Counter): labels=[task_name, status]
- db_pool_size (Gauge): 当前连接池大小
- db_pool_checked_out (Gauge): 当前使用中的连接数
"""
```

**约束**：
- 使用 `prometheus_client` 官方库，不用 `prometheus-fastapi-instrumentator`（减少黑盒依赖）
- `/metrics` 路由不需要认证（Prometheus scraper 需要直接访问）
- path label 使用路由模板（如 `/api/v1/products/{product_id}`），不使用实际路径（防止高基数）
- 中间件必须放在 `request_logging_middleware` 之前（先记录指标，再记录日志）
- AI 指标在 `ArkOpenAIClient` 的方法中埋点，MockAIClient 不埋点
- 健康检查路径 `/health/*` 不计入指标（避免噪音）

**测试要求**：
- 测试 `/metrics` 返回 200 且包含 `http_requests_total`
- 测试请求后 Counter 递增
- 测试 AI 调用后 AI Counter 递增（mock redis + mock ai）

**验收标准**：
- 现有测试全部通过
- `curl http://localhost:8000/metrics` 返回 Prometheus 文本格式
- `uv run ruff check .` + `uv run mypy app` 通过

---

### P0-04：CD 流水线（自动构建 + 推送镜像）

**问题**：CI 只做代码检查，没有自动构建 Docker 镜像和推送到镜像仓库。

**目标**：main 分支合并后自动构建 Docker 镜像并推送。

**修改文件**：
- 新建 `.github/workflows/backend-cd.yml`

**技术方案**：

```yaml
# .github/workflows/backend-cd.yml
# 触发条件：push to main（backend/** 变更时）
# 步骤：
# 1. Checkout
# 2. Set up Docker Buildx
# 3. Login to GitHub Container Registry (ghcr.io)
# 4. Build and push image with tags:
#    - ghcr.io/<owner>/duoduo-api:latest
#    - ghcr.io/<owner>/duoduo-api:<git-sha-short>
#    - ghcr.io/<owner>/duoduo-api:<date-YYYYMMDD>
# 5. Output image digest for audit trail
```

**约束**：
- 只在 `backend/**` 文件变更时触发
- 使用 GitHub Container Registry（ghcr.io），不用 Docker Hub
- 使用 `docker/build-push-action@v5` 官方 Action
- 镜像 tag 必须包含 git short SHA（可追溯）
- 构建上下文（context）为 `backend/`
- 不包含部署步骤（部署策略由运维决定）
- 使用 `${{ github.token }}` 认证，不需要额外 secret

**测试要求**：
- YAML 语法正确（可用 `actionlint` 检查）
- 不影响现有 `backend-ci.yml`

**验收标准**：
- push to main 后触发 CD workflow
- ghcr.io 上出现新镜像
- 镜像可正常 `docker run` 启动

---

### P0-05：数据库定时备份脚本

**问题**：PostgreSQL 数据存在 Docker volume 中，没有定期备份。volume 损坏或误删则数据全丢。

**目标**：提供一个备份脚本和定时任务配置。

**修改文件**：
- 新建 `backend/scripts/backup_db.sh`
- 新建 `backend/docs/BACKUP.md`

**技术方案**：

```bash
# backend/scripts/backup_db.sh
#!/bin/bash
# PostgreSQL 数据库备份脚本
#
# 功能：
# 1. 使用 pg_dump 导出完整数据库
# 2. 压缩为 .sql.gz
# 3. 文件名包含日期时间：duoduo_backup_20260519_120000.sql.gz
# 4. 保留最近 7 天的备份，自动清理旧文件
# 5. 备份完成后输出文件大小和 SHA256 校验和
#
# 环境变量：
# PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSWORD
# BACKUP_DIR (默认: /backups)
# BACKUP_RETENTION_DAYS (默认: 7)
```

**约束**：
- 脚本必须是幂等的（重复运行不会出错）
- 备份失败时返回非零退出码
- 不包含硬编码密码
- `BACKUP.md` 说明：如何手动运行、如何配置 crontab、如何恢复

**验收标准**：
- `shellcheck backend/scripts/backup_db.sh` 无错误
- 脚本可在 docker compose 环境中执行
- 文档清晰说明恢复步骤

---

### P0-06：SLO 定义与 PRR Checklist

**问题**：没有定义服务级别目标和上线检查清单。

**目标**：编写 SLO 文档和 PRR Checklist。

**修改文件**：
- 新建 `backend/docs/SLO.md`
- 新建 `backend/docs/PRR_CHECKLIST.md`

**SLO.md 内容要求**：

```markdown
# 服务级别目标 (SLO)

## 可用性
- API 整体可用性目标：99.5%（月度）
- 计算方式：成功请求数 / 总请求数（排除 4xx 客户端错误）

## 延迟
- 普通 CRUD 接口 P99 < 500ms
- AI 生成接口（问卷生成、报告生成）P99 < 60s
- AI 流式对话首 token 延迟 P99 < 5s

## AI 调用
- AI 调用成功率 > 95%（含重试后成功）
- 熔断恢复时间 < 60s

## 错误预算
- 月度错误预算 = 1 - 0.995 = 0.5%
- 错误预算耗尽时冻结非关键发布
```

**PRR_CHECKLIST.md 内容要求**：

```markdown
# 生产就绪评审 Checklist (PRR)

上线前必须逐项确认：

## 基础设施
- [ ] 数据库备份已配置并验证恢复流程
- [ ] Redis 持久化已开启（AOF 或 RDB）
- [ ] TLS/HTTPS 已配置
- [ ] 域名和 DNS 已就位

## 监控与告警
- [ ] Prometheus 指标正常采集
- [ ] 5xx 错误率告警已配置
- [ ] AI 服务故障告警已配置
- [ ] 数据库连接池告警已配置

## 安全
- [ ] APP_SECRET_KEY 已更换为强随机值（≥32字节）
- [ ] CORS_ALLOWED_ORIGINS 已限制为实际域名
- [ ] 依赖漏洞扫描通过
- [ ] 生产环境 APP_ENV=production

## 应用
- [ ] 所有 Alembic 迁移已执行
- [ ] Persona 种子数据已导入
- [ ] 健康检查端点 /health/ready 返回 ok
- [ ] 限速器 Redis 连接正常

## 回滚方案
- [ ] Docker 镜像支持按 tag 回退
- [ ] 数据库迁移有 downgrade 脚本
- [ ] 回滚操作已文档化并演练过
```

**约束**：
- 纯文档，不涉及代码修改
- SLO 数值基于当前 MVP 规模（1000 用户），后续可调整

---

## P1 — 生产加固（上线后 2~3 周内完成）

---

### P1-01：CI 集成安全扫描

**问题**：CI 中没有依赖漏洞扫描。

**目标**：在 CI 中加入 `pip-audit` 安全扫描步骤。

**修改文件**：
- 修改 `.github/workflows/backend-ci.yml`
- `backend/pyproject.toml`（新增 dev 依赖 `pip-audit`）

**技术方案**：
在 `backend-ci.yml` 的 Ruff 步骤之后，Pytest 之前，新增：

```yaml
      - name: Security audit
        run: uv run pip-audit --strict --desc
```

**约束**：
- `--strict` 模式：有已知漏洞则 CI 失败
- 如果当前依赖存在已知漏洞，允许在 PR 中同时修复（升级依赖版本）
- 不引入 bandit、semgrep 等重量级工具（MVP 阶段 pip-audit 足够）

**验收标准**：
- CI 中 Security audit 步骤通过
- `uv run pip-audit` 本地也能运行

---

### P1-02：HTTPS/TLS 反向代理配置

**问题**：应用层没有 TLS，通信是明文的。

**目标**：提供 Nginx 反向代理配置，强制 HTTPS。

**修改文件**：
- 新建 `backend/deploy/nginx.conf`
- 新建 `backend/deploy/docker-compose.prod.yml`（生产用 compose，包含 nginx）
- 新建 `backend/docs/DEPLOY.md`

**技术方案**：

```nginx
# backend/deploy/nginx.conf
# - 监听 443 (HTTPS) + 80 (重定向到 HTTPS)
# - TLS 证书路径通过环境变量或 volume 挂载
# - 反向代理到 api:8000
# - 添加 Strict-Transport-Security 头
# - 添加 proxy_read_timeout 120s（AI 流式接口需要长连接）
# - WebSocket / SSE 支持（proxy_buffering off）
# - /metrics 端点仅允许内网访问
```

**约束**：
- 不在应用层加 HSTS（在 Nginx 层加，开发环境是 HTTP）
- nginx.conf 中 TLS 证书路径使用占位符，DEPLOY.md 中说明如何替换
- docker-compose.prod.yml 不替换开发用的 docker-compose.yml，是独立文件
- SSE 流式接口需要 `proxy_buffering off` 和足够长的 timeout

**验收标准**：
- `nginx -t` 配置语法检查通过
- DEPLOY.md 说明完整的部署步骤

---

### P1-03：Redis 缓存层（产品详情 + 人设列表）

**问题**：所有请求直接查数据库，没有缓存层。产品详情和人设列表是高频读取、低频更新的数据。

**目标**：为产品详情和人设列表引入 Redis 缓存。

**修改文件**：
- 新建 `backend/app/core/cache.py`
- 修改 `backend/app/services/product_service.py`
- 修改 `backend/app/services/persona_service.py`
- 新建 `backend/tests/test_cache.py`

**技术方案**：

```python
# backend/app/core/cache.py
"""
通用 Redis 缓存工具。

功能：
1. get / set / delete 基础操作
2. TTL 随机偏移（防缓存雪崩）：base_ttl ± 10%
3. 空值缓存（防缓存穿透）：缓存 None 值，TTL 较短（60s）
4. 缓存失效时 fail-open（Redis 不可用不影响请求）

使用方式：
cache = RedisCache(prefix="product")
result = await cache.get_or_set(
    key=f"detail:{product_id}",
    factory=lambda: repo.get_by_id(product_id),
    ttl=300,  # 5分钟
)
"""
```

**约束**：
- 遵守架构分层：`cache.py` 在 `core/` 层，service 层调用
- 缓存 key 前缀：`product:detail:{id}`、`persona:visible:{user_id}`
- 产品创建 / 更新 / 删除时必须清除对应缓存
- 人设创建 / 删除时清除该用户的人设列表缓存
- Redis 不可用时 fail-open（直接查数据库）
- 不使用装饰器模式（显式调用，方便理解和调试）
- 不引入互斥锁（MVP 规模不需要防缓存击穿）

**测试要求**：
- 测试缓存命中（第二次调用不查数据库）
- 测试缓存失效后重新查询
- 测试 Redis 不可用时 fallback 到数据库
- 测试空值缓存（查不到的 product 也缓存）

**验收标准**：
- 现有测试全部通过
- 新增缓存测试通过
- `uv run ruff check .` + `uv run mypy app` 通过

---

### P1-04：OpenTelemetry 分布式追踪

**问题**：request_id 只在单次 HTTP 请求内有效，无法追踪 API → Celery → AI 调用链。

**目标**：引入 OpenTelemetry，在 API、Celery task、AI 调用之间传递 trace context。

**修改文件**：
- `backend/pyproject.toml`（新增依赖：`opentelemetry-api`、`opentelemetry-sdk`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-exporter-otlp-proto-grpc`）
- 新建 `backend/app/core/tracing.py`
- 修改 `backend/app/main.py`（初始化 tracer）
- 修改 `backend/app/tasks/evaluation_tasks.py`（传递 trace context）
- 新建 `backend/tests/test_tracing.py`

**技术方案**：

```python
# backend/app/core/tracing.py
"""
OpenTelemetry 初始化。

- 开发环境：ConsoleSpanExporter（打印到日志）
- 生产环境：OTLPSpanExporter（发送到 Jaeger / Tempo）
- OTEL_EXPORTER_OTLP_ENDPOINT 环境变量控制目标地址
- 如果未配置 endpoint，tracing 完全禁用（NoopTracer）

新增配置项（config.py）：
- otel_enabled: bool = False
- otel_endpoint: str = ""
- otel_service_name: str = "duoduo-api"
"""
```

**约束**：
- 默认禁用（`otel_enabled=False`），不影响现有行为
- 启用后 trace_id 写入 JSON 日志的 `trace_id` 字段
- Celery task 通过 header 传递 trace context
- 不引入自动 instrumentation 的所有包（只用 fastapi 和手动 span）
- AI 调用手动创建 span：`with tracer.start_as_current_span("ai.complete")`
- 测试使用 InMemorySpanExporter 验证 span 创建

**验收标准**：
- `otel_enabled=False` 时现有测试全部通过，无性能影响
- `otel_enabled=True` 时 span 正确创建
- `uv run ruff check .` + `uv run mypy app` 通过

---

### P1-05：告警规则定义

**问题**：没有任何告警配置，出问题要等用户反馈才知道。

**目标**：提供 Prometheus 告警规则文件。

**前置依赖**：P0-03（Prometheus 指标收集）

**修改文件**：
- 新建 `backend/deploy/prometheus/alert_rules.yml`
- 新建 `backend/deploy/prometheus/prometheus.yml`

**告警规则**：

```yaml
groups:
  - name: duoduo-api
    rules:
      # 5xx 错误率 > 5%（5分钟窗口）
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.05
        for: 2m
        labels:
          severity: critical

      # API P99 延迟 > 2s（排除 AI 接口）
      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            rate(http_request_duration_seconds_bucket{
              path_template!~"/api/v1/(surveys/generate|evaluations/.*/run|conversations/.*/messages)"
            }[5m])
          ) > 2
        for: 5m
        labels:
          severity: warning

      # AI 服务连续失败
      - alert: AIServiceDown
        expr: |
          sum(rate(ai_requests_total{status="error"}[5m]))
          / sum(rate(ai_requests_total[5m])) > 0.5
        for: 3m
        labels:
          severity: critical

      # DB 连接池即将耗尽（使用率 > 80%）
      - alert: DBPoolExhaustion
        expr: db_pool_checked_out / db_pool_size > 0.8
        for: 5m
        labels:
          severity: warning
```

**约束**：
- 纯配置文件，不涉及 Python 代码
- prometheus.yml 中 scrape 目标为 `api:8000/metrics`
- 告警规则文件语法正确（可用 `promtool check rules` 验证）

---

### P1-06：Runbook 操作手册

**问题**：没有标准化的故障处理文档。

**目标**：编写常见故障的排查和处理手册。

**修改文件**：
- 新建 `backend/docs/RUNBOOK.md`

**内容要求**：

```markdown
# 运维操作手册 (Runbook)

## 1. 服务启动与停止
  - docker compose 启动完整服务
  - 单独重启 API / Worker / Redis / PostgreSQL

## 2. 常见故障排查

### 2.1 API 返回 503 (Service Unavailable)
  - 检查 /health/ready 确定哪个依赖挂了
  - PostgreSQL 故障：检查连接数、磁盘空间、日志
  - Redis 故障：检查内存、连接数
  - Qdrant 故障：检查端口、磁盘空间

### 2.2 AI 服务超时或熔断
  - 检查 AI provider 状态页
  - 查看熔断器状态日志
  - 手动重置熔断器（如果需要）
  - 降级方案：切换到 mock 模式

### 2.3 Celery 任务堆积
  - 查看队列深度：redis-cli LLEN evaluations
  - 检查 worker 日志
  - 扩容 worker 副本

### 2.4 数据库迁移回滚
  - alembic downgrade -1
  - 确认应用兼容旧 schema

## 3. 数据库备份与恢复
  - 手动备份
  - 从备份恢复
  - 验证恢复完整性

## 4. 紧急联系人
  - 服务负责人
  - 升级流程
```

**约束**：
- 纯文档，不涉及代码修改
- 命令必须可直接复制执行
- 每个故障场景包含：症状 → 排查步骤 → 修复方案 → 验证方法

---

### P1-07：压力测试脚本

**问题**：没有做过负载测试，不知道系统在目标负载下的表现。

**目标**：提供 Locust 压力测试脚本。

**修改文件**：
- 新建 `backend/tests/load/locustfile.py`
- 新建 `backend/tests/load/README.md`

**技术方案**：

```python
# backend/tests/load/locustfile.py
"""
Locust 压力测试。

测试场景（模拟真实用户行为）：
1. 登录（权重 1）
2. 创建产品（权重 2）
3. 查看产品列表（权重 5）
4. 查看产品详情（权重 3）
5. 生成问卷（权重 2）
6. 查看人设列表（权重 3）
7. 发送对话消息（权重 2）

目标：
- 100 并发用户
- 普通接口 P99 < 500ms
- 零 5xx 错误
"""
```

**约束**：
- 不作为 pytest 测试的一部分（独立运行）
- 使用 mock AI 模式（`AI_PROVIDER=mock`）
- README.md 说明如何安装 locust、如何运行、如何看结果
- 不引入 locust 作为项目依赖（在 load test 目录独立安装）

---

## P2 — 成熟运维（按需实施）

---

### P2-01：Celery Worker 优雅停机

**修改文件**：`backend/app/tasks/celery_app.py`

**目标**：SIGTERM 时等待当前任务完成再退出。配置 `worker_max_tasks_per_child` 防内存泄漏。

---

### P2-02：AI 调用 Bulkhead 隔离

**修改文件**：`backend/app/ai/client.py`

**目标**：限制 AI 并发调用数（`asyncio.Semaphore`），防止 AI 慢请求耗尽所有资源。

---

### P2-03：RBAC 权限守卫

**修改文件**：新建 `backend/app/core/permissions.py`，修改各 router。

**目标**：基于 `role_type` 的路由级权限校验。

---

### P2-04：审计日志

**修改文件**：新建 `backend/app/db/models/audit_log.py`，新建中间件。

**目标**：记录敏感操作（删除、权限变更）到独立表。

---

### P2-05：RS256 JWT 升级

**修改文件**：`backend/app/core/security.py`、`backend/app/core/config.py`

**目标**：从 HS256 对称签名升级为 RS256 非对称签名。

---

## 补充任务 — 闭环差距分析后新增

> 以下任务是对照"7大生产闭环 + 8个关键问题"审计后发现的遗漏项。

---

### P0-07：Celery Watchdog + 僵尸任务恢复

**问题**：evaluation 一旦卡在 `answering` 状态（worker OOM、网络断开、Celery 重试耗尽），永远不会恢复。没有人知道任务卡住了。

**目标**：定时扫描僵尸任务并自动恢复或标记失败。

**修改文件**：
- 新建 `backend/app/tasks/watchdog.py`
- 修改 `backend/app/tasks/celery_app.py`（注册 beat 定时任务）
- 新建 `backend/tests/test_watchdog.py`

**技术方案**：

```python
# backend/app/tasks/watchdog.py
"""
Celery Beat 定时任务：每 5 分钟扫描一次。

逻辑：
1. 查询 status='answering' 且 started_at < now() - STALE_THRESHOLD 的 evaluation
2. STALE_THRESHOLD 默认 30 分钟（可配置）
3. 对每个 stale evaluation：
   a. 检查 Celery task 状态（通过 task_id 查 AsyncResult）
   b. 如果 task 已完成/失败/不存在 → 标记 evaluation 为 failed + 记录 error_message
   c. 如果 task 仍在运行 → 跳过（可能只是慢）
4. 打日志：evaluation_watchdog_recovered evaluation_id=X
"""
```

**约束**：
- 使用 Celery Beat 定时调度，不用外部 cron
- watchdog 本身必须是幂等的（重复运行不会多次标记同一个 evaluation）
- 不自动重试失败的 evaluation（只标记 failed，让用户决定是否重新发起）
- 恢复时更新 `finished_at` 和 `error_message`
- 测试环境跳过（APP_ENV=testing）

**测试要求**：
- 测试 stale evaluation 被正确标记为 failed
- 测试非 stale evaluation 不受影响
- 测试已经是 done/failed/canceled 的 evaluation 不受影响

---

### P0-08：Evaluation 任务幂等 + 分布式锁防重

**问题**：同一个 evaluation 可能被重复投递到 Celery（用户快速点击、网络重试），导致两个 worker 同时处理同一个 evaluation。

**目标**：通过 Redis 分布式锁确保同一个 evaluation 同一时间只有一个 worker 在处理。

**修改文件**：
- 新建 `backend/app/core/distributed_lock.py`
- 修改 `backend/app/tasks/evaluation_tasks.py`（在任务开头获取锁）
- 新建 `backend/tests/test_distributed_lock.py`

**技术方案**：

```python
# backend/app/core/distributed_lock.py
"""
Redis 分布式锁，用于保护 Celery 任务不被重复执行。

使用方式：
async with DistributedLock(key=f"eval:{evaluation_id}", ttl=1800) as acquired:
    if not acquired:
        logger.warning("evaluation already being processed")
        return {"status": "skipped", "reason": "duplicate"}
    # ... 执行任务

特性：
- TTL 自动过期（防止锁永远不释放）
- 非阻塞：获取不到锁直接返回 False，不等待
- Redis 不可用时 fail-open（允许执行，降级为无锁）
- 使用 SET NX EX 原子操作
"""
```

**约束**：
- 锁的 key：`lock:eval:{evaluation_id}`
- TTL：30 分钟（evaluation 最长运行时间）
- 任务正常结束或异常时都必须释放锁
- Redis 不可用时 fail-open
- 不使用 redlock（单 Redis 实例够用）

**测试要求**：
- 测试获取锁成功
- 测试锁已存在时返回 False
- 测试锁自动过期
- 测试 Redis 不可用时 fail-open

---

### P0-09：Evaluation 积分扣费 + 失败退款

**问题**：`credit_service.deduct()` 和 `credit_service.refund()` 都写好了，但 evaluation task 里 **credit_cost 始终为 0**，从未真正扣费。evaluation 失败后也没有退款逻辑。

**目标**：在 evaluation 开始前扣费，失败后自动退款。

**修改文件**：
- 修改 `backend/app/services/evaluation_service.py`（创建 evaluation 时计算并扣除积分）
- 修改 `backend/app/tasks/evaluation_tasks.py`（失败时调用 refund）
- 新建 `backend/tests/test_credit_flow.py`

**技术方案**：

```python
# evaluation_service.py 中创建 evaluation 时：
# 1. 计算 credit_cost = len(selected_persona_ids) * COST_PER_PERSONA
# 2. 检查用户余额是否足够（不足抛 INSUFFICIENT_CREDITS）
# 3. 调用 credit_service.deduct() 扣费
# 4. 将 credit_cost 写入 evaluation 记录

# evaluation_tasks.py 中任务失败时：
# 1. 获取 evaluation.credit_cost
# 2. 调用 credit_service.refund() 全额退款
# 3. 记录退款日志

# 部分失败时：
# 1. 计算实际成功数 success_count = total - failed_count
# 2. 退还失败部分的积分：refund_amount = failed_count * COST_PER_PERSONA
```

**约束**：
- `COST_PER_PERSONA` 暂定为 10 积分（写入 config.py 可配置）
- 扣费必须在 evaluation 创建时（service 层），不在 Celery task 里
- 退款在 task 层（因为只有 task 知道最终成功/失败数）
- 扣费和退款都必须写 CreditTransaction 记录
- 余额不足时返回 `INSUFFICIENT_CREDITS`（API_CONTRACT 中已定义此错误码）
- 不引入两阶段提交（单数据库事务足够）

**测试要求**：
- 测试创建 evaluation 时扣费成功
- 测试余额不足时返回 INSUFFICIENT_CREDITS
- 测试 evaluation 全部失败时全额退款
- 测试 evaluation 部分失败时部分退款
- 测试 evaluation 全部成功时不退款

---

### P0-10：启动时校验 APP_SECRET_KEY

**问题**：`APP_SECRET_KEY` 默认值是 `change_me_for_local_development_only`。如果忘记在生产环境替换，所有 JWT 都可以被轻易伪造。

**目标**：`APP_ENV=production` 时，如果 SECRET_KEY 是默认值则拒绝启动。

**修改文件**：
- 修改 `backend/app/core/config.py`（添加 `@model_validator`）
- 修改 `backend/tests/test_health.py`（验证开发环境不受影响）

**技术方案**：

```python
# config.py Settings 类中添加：
@model_validator(mode="after")
def validate_production_secrets(self) -> Settings:
    if self.app_env == "production":
        if self.app_secret_key == "change_me_for_local_development_only":
            raise ValueError(
                "APP_SECRET_KEY must be changed from default in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(self.app_secret_key) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters in production")
    return self
```

**约束**：
- 只在 `APP_ENV=production` 时校验，不影响开发和测试环境
- 拒绝启动时给出明确的生成密钥命令
- 同时校验长度（≥32 字符）

**测试要求**：
- 测试 production + 默认 key → ValueError
- 测试 production + 短 key → ValueError
- 测试 production + 合格 key → 正常
- 测试 development + 默认 key → 正常（不受影响）

---

### P1-08：微信 code 日志脱敏

**问题**：微信登录的 `code` 参数可能出现在请求日志中，泄露后可被重放。

**修改文件**：
- 修改 `backend/app/core/logging.py`（添加脱敏正则）
- 修改 `backend/tests/test_log_sanitization.py`（新增测试）

**技术方案**：
在 `_SENSITIVE_PATTERNS` 中添加对 `"code":"..."` 格式的脱敏规则：

```python
# 微信 code（JSON 格式）
(re.compile(r'("code"\s*:\s*")[^"]{4,}(")', re.IGNORECASE), r'\1***\2'),
```

**约束**：
- 只脱敏长度 ≥4 的 code 值（避免误伤短字符串）
- 保留前后引号结构，替换中间内容为 `***`

---

### P1-09：上传文件 Magic Number 校验

**问题**：上传接口只检查 `mime_type` 字符串，攻击者可以声称 `image/jpeg` 但上传可执行文件。

**修改文件**：
- 新建 `backend/app/storage/file_validation.py`
- 修改 `backend/app/services/product_service.py`（base64 图片校验）
- 新建 `backend/tests/test_file_validation.py`

**技术方案**：

```python
# backend/app/storage/file_validation.py
"""
通过文件头（magic number）验证图片真实类型。

JPEG: FF D8 FF
PNG:  89 50 4E 47

对 base64 上传的图片：解码前 16 字节，检查 magic number 是否匹配声称的 mime_type。
对 upload-url 流程：在实际对象存储的接收端校验（不在本层做）。
"""
```

**约束**：
- 不引入 `python-magic` 等 C 依赖（只检查文件头前 16 字节）
- 校验失败返回 `INVALID_FILE_TYPE`（复用现有错误码）
- 只校验 base64 上传的图片（upload-url 流程由存储层校验）

---

### P1-10：SSE 流式中断率指标

**前置依赖**：P0-03（Prometheus 指标）

**修改文件**：
- 修改 `backend/app/services/conversation_service.py`（SSE 生成器中记录中断）
- 修改 `backend/app/core/metrics.py`（新增 `sse_streams_total` Counter，labels=[status: complete|interrupted]）

**约束**：
- `complete` = 流式正常结束（收到 `[DONE]`）
- `interrupted` = 客户端断开或服务端异常
- 不改变 SSE 的行为，只埋点记录

---

### P1-11：Sentry 错误追踪集成

**修改文件**：
- `backend/pyproject.toml`（新增依赖 `sentry-sdk[fastapi]`）
- 新建 `backend/app/core/sentry.py`
- 修改 `backend/app/main.py`（初始化 Sentry）
- 修改 `backend/app/core/config.py`（新增 `sentry_dsn` 配置）

**技术方案**：

```python
# backend/app/core/sentry.py
"""
Sentry 初始化。

- SENTRY_DSN 为空时完全禁用（不影响开发/测试）
- 自动捕获 unhandled exceptions
- 附带 request_id、user_id 上下文
- traces_sample_rate = 0.1（采样 10% 的请求做性能追踪）
- 排除 4xx 错误（只追踪 5xx）
"""
```

**约束**：
- 默认禁用（`sentry_dsn=""`），不影响现有行为
- 不在 Sentry 中发送敏感数据（request body 中的 code、token 要 scrub）
- 测试环境始终禁用

---

### P1-12：真实 Provider Smoke Test 脚本

**修改文件**：
- 新建 `backend/scripts/smoke_test_ai.py`

**技术方案**：

```python
# backend/scripts/smoke_test_ai.py
"""
AI Provider 烟雾测试。用于部署后验证 AI 配置是否正常。

运行方式：uv run python scripts/smoke_test_ai.py

检查项：
1. DeepSeek complete → 返回非空文本
2. DeepSeek stream → 收到至少 1 个 chunk
3. 智谱 GLM vision → 返回非空文本（需要测试图片）
4. 打印每个 provider 的延迟和 token 使用量

退出码：
- 0 = 全部通过
- 1 = 有失败项（打印详细错误）
"""
```

**约束**：
- 不作为 pytest 测试（需要真实 API key，只在部署时手动运行）
- 需要环境变量 `AI_PROVIDER=deepseek`、`DEEPSEEK_API_KEY` 等
- 超时 60 秒
- 不消耗大量 token（prompt 尽量短）

---

### P1-13：Celery 死信队列（DLQ）

**修改文件**：
- 修改 `backend/app/tasks/celery_app.py`（配置 DLQ）
- 修改 `backend/app/tasks/evaluation_tasks.py`（重试耗尽后发送到 DLQ）

**技术方案**：

```python
# celery_app.py 中配置：
celery_app.conf.update(
    task_reject_on_worker_lost=True,  # worker 被杀时任务不丢失
    task_acks_late=True,               # 任务完成后才确认
)

# evaluation_tasks.py 中：
# 在 @celery_app.task 装饰器添加 on_failure 回调
# 重试耗尽后将 evaluation_id 写入 Redis list "dlq:evaluations"
# watchdog 定时扫描 DLQ 并发送告警
```

**约束**：
- DLQ 使用 Redis list（不引入 RabbitMQ）
- DLQ 中的消息保留 7 天（通过 key TTL）
- watchdog（P0-07）扫描 DLQ 并打日志

---

### P1-14：真实对象存储适配

**修改文件**：
- 修改 `backend/app/storage/adapters.py`（新增真实 TOS/OSS 适配器）
- 修改 `backend/app/core/config.py`（新增 `STORAGE_PROVIDER`、`TOS_BUCKET` 等配置）
- 新建 `backend/tests/test_storage_real.py`

**技术方案**：

```python
# storage/adapters.py
"""
新增 StorageProvider 枚举：mock | tos | oss

mock: 现有 MockStorageAdapter（开发用）
tos: 火山引擎 TOS（签名 URL 上传 + CDN 访问）
oss: 阿里云 OSS（备选）

工厂函数根据 STORAGE_PROVIDER 配置返回对应适配器。
"""
```

**约束**：
- 默认 `STORAGE_PROVIDER=mock`，不影响现有行为
- 签名 URL 有效期：上传 15 分钟，访问 1 小时
- 对象 key 格式：`products/{user_id}/{uuid}.{ext}`
- 不在代码中硬编码 bucket name 或 endpoint

---

## 总览（更新版）

| 阶段 | 任务数 | 代码任务 | 文档任务 | 配置任务 |
|------|--------|---------|---------|---------|
| P0 | 10 | 7 | 2 | 1 |
| P1 | 14 | 10 | 2 | 2 |
| P2 | 5 | 5 | 0 | 0 |
| **合计** | **29** | **22** | **4** | **3** |

### P0 任务完成状态

| 编号 | 任务 | 状态 |
|------|------|------|
| P0-01 | AI 客户端熔断器 | ✅ 已完成（PR #20） |
| P0-02 | JWT Token 吊销 + logout | TODO |
| P0-03 | Prometheus 指标收集 | TODO |
| P0-04 | CD 流水线 | TODO |
| P0-05 | 数据库备份脚本 | TODO |
| P0-06 | SLO + PRR Checklist | TODO |
| P0-07 | Celery Watchdog + 僵尸恢复 | TODO |
| P0-08 | Evaluation 分布式锁防重 | TODO |
| P0-09 | Evaluation 积分扣费 + 退款 | TODO |
| P0-10 | 启动时校验 SECRET_KEY | TODO |

每个任务独立一个 PR，分支命名 `prod/<编号>`，CI 全绿后合并。
