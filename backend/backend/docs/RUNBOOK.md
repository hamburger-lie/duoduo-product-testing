# 运维操作手册 (Runbook)

> 适用环境：Docker Compose 部署（单机或小集群）

---

## 1. 服务启动与停止

### 完整启动

```bash
cd backend
docker compose -f deploy/docker-compose.prod.yml up -d
```

### 完整停止

```bash
docker compose -f deploy/docker-compose.prod.yml down
```

### 单独重启某个服务

```bash
# 重启 API
docker compose -f deploy/docker-compose.prod.yml restart api

# 重启 Worker
docker compose -f deploy/docker-compose.prod.yml restart worker

# 重启 Redis
docker compose -f deploy/docker-compose.prod.yml restart redis

# 重启 PostgreSQL
docker compose -f deploy/docker-compose.prod.yml restart postgres
```

### 查看服务状态

```bash
docker compose -f deploy/docker-compose.prod.yml ps
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 api
```

---

## 2. 常见故障排查

### 2.1 API 返回 503 (Service Unavailable)

**症状**：`/health/ready` 返回非 200，或前端报 503。

**排查步骤**：

```bash
# 1. 检查哪个依赖挂了
curl http://localhost:8000/health/ready

# 2. 检查各服务状态
docker compose -f deploy/docker-compose.prod.yml ps

# 3. 检查 PostgreSQL
docker compose -f deploy/docker-compose.prod.yml exec postgres pg_isready -U postgres
docker compose -f deploy/docker-compose.prod.yml logs --tail=30 postgres

# 4. 检查 Redis
docker compose -f deploy/docker-compose.prod.yml exec redis redis-cli ping

# 5. 检查 API 日志
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 api
```

**修复方案**：
- PostgreSQL 故障：检查磁盘空间 `df -h`，检查连接数 `SELECT count(*) FROM pg_stat_activity;`
- Redis 故障：检查内存 `redis-cli info memory`，必要时 `docker compose restart redis`
- API OOM：增加内存限制或减少 worker 数量

**验证**：

```bash
curl http://localhost:8000/health/ready
# 应返回 {"status": "ok"}
```

---

### 2.2 AI 服务超时或熔断

**症状**：评估任务卡住，日志出现 `circuit_breaker_state_change to=OPEN`。

**排查步骤**：

```bash
# 1. 检查 AI provider 状态
# DeepSeek: https://status.deepseek.com
# 智谱: https://open.bigmodel.cn

# 2. 查看熔断器日志
docker compose -f deploy/docker-compose.prod.yml logs api | grep circuit_breaker

# 3. 查看 AI 指标
curl -s http://localhost:8000/metrics | grep ai_requests_total
```

**修复方案**：
- 等待 AI provider 恢复，熔断器会在 recovery_timeout(30s) 后自动探测
- 紧急降级：设置 `AI_PROVIDER=mock` 并重启 API（仅测试用，生产数据不准确）

**验证**：

```bash
# 检查熔断器是否恢复
docker compose -f deploy/docker-compose.prod.yml logs --tail=20 api | grep circuit_breaker
```

---

### 2.3 Celery 任务堆积

**症状**：评估提交后长时间不完成，metrics 显示任务失败率上升。

**排查步骤**：

```bash
# 1. 查看 Redis 队列深度
docker compose -f deploy/docker-compose.prod.yml exec redis redis-cli LLEN celery

# 2. 检查 worker 状态和日志
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 worker

# 3. 检查活跃任务数
docker compose -f deploy/docker-compose.prod.yml exec redis redis-cli LLEN evaluations

# 4. 查看 Celery 指标
curl -s http://localhost:8000/metrics | grep celery_tasks_total
```

**修复方案**：
- 扩容 worker：`docker compose -f deploy/docker-compose.prod.yml up -d --scale worker=3`
- 清理僵尸任务：watchdog 会自动处理（每 5 分钟扫描一次）
- 手动重启 worker：`docker compose -f deploy/docker-compose.prod.yml restart worker`

**验证**：

```bash
# 队列应逐渐清空
docker compose -f deploy/docker-compose.prod.yml exec redis redis-cli LLEN celery
```

---

### 2.4 数据库迁移失败

**排查步骤**：

```bash
# 1. 查看当前迁移版本
docker compose -f deploy/docker-compose.prod.yml exec api uv run alembic current

# 2. 查看迁移历史
docker compose -f deploy/docker-compose.prod.yml exec api uv run alembic history --verbose

# 3. 查看失败日志
docker compose -f deploy/docker-compose.prod.yml logs api | grep alembic
```

**回滚方案**：

```bash
# 回退一个版本
docker compose -f deploy/docker-compose.prod.yml exec api uv run alembic downgrade -1

# 确认回退成功
docker compose -f deploy/docker-compose.prod.yml exec api uv run alembic current

# 重启 API 确保兼容
docker compose -f deploy/docker-compose.prod.yml restart api
```

---

### 2.5 积分异常（扣费/退款）

**症状**：用户余额不正确，或评估失败后没有退款。

**排查步骤**：

```sql
-- 1. 查看用户余额
SELECT id, credit_balance FROM users WHERE id = <user_id>;

-- 2. 查看积分流水
SELECT * FROM credit_transactions
WHERE user_id = <user_id>
ORDER BY created_at DESC LIMIT 20;

-- 3. 查看评估状态和积分消耗
SELECT id, status, credit_cost, error_message
FROM evaluations
WHERE user_id = <user_id>
ORDER BY created_at DESC LIMIT 10;
```

**修复方案**：
- 如果评估 failed 但没有退款记录，检查 watchdog 是否正常运行
- 手动退款需直接操作数据库（谨慎）

---

## 3. 数据库备份与恢复

### 手动备份

```bash
bash scripts/backup_db.sh
```

### 从备份恢复

```bash
# 1. 停止 API 和 Worker
docker compose -f deploy/docker-compose.prod.yml stop api worker beat

# 2. 解压备份
gunzip duoduo_backup_YYYYMMDD_HHMMSS.sql.gz

# 3. 恢复
docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d duoduo < duoduo_backup_YYYYMMDD_HHMMSS.sql

# 4. 重启服务
docker compose -f deploy/docker-compose.prod.yml up -d api worker beat
```

### 验证恢复完整性

```bash
# 检查表是否存在
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  psql -U postgres -d duoduo -c "\dt"

# 检查数据行数
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  psql -U postgres -d duoduo -c "SELECT 'users', count(*) FROM users UNION ALL SELECT 'products', count(*) FROM products UNION ALL SELECT 'evaluations', count(*) FROM evaluations;"
```

---

## 4. 监控指标检查

```bash
# Prometheus 指标
curl -s http://localhost:8000/metrics | grep -E "^(http_requests|ai_requests|celery_tasks|db_pool|sse_streams)"

# 关键指标含义：
# http_requests_total        — HTTP 请求总数（按方法/路径/状态码）
# ai_requests_total          — AI 调用总数（按 provider/状态）
# celery_tasks_total         — Celery 任务总数（按名称/状态）
# db_pool_size               — 数据库连接池大小
# db_pool_checked_out        — 当前使用中的连接数
# sse_streams_total          — SSE 流式连接数（按完成/中断/错误）
```

---

## 5. 日常运维 Checklist

- [ ] 检查 `/health/ready` 状态
- [ ] 检查磁盘空间 > 20%
- [ ] 检查数据库备份是否正常执行
- [ ] 检查 Prometheus 告警是否有触发
- [ ] 检查 Redis 内存使用 < 80%
- [ ] 检查 Celery 队列无积压
