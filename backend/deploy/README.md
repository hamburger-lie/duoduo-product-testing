# 生产部署指南

## 前置条件

1. Docker + Docker Compose v2
2. 域名已备案并完成 DNS 解析
3. TLS 证书（Let's Encrypt 或云厂商证书）
4. 微信小程序 AppID/Secret
5. DeepSeek API Key
6. （可选）Sentry DSN

## 部署步骤

### 1. 准备环境变量

```bash
cp backend/.env.production.example deploy/.env
# 编辑 deploy/.env，填写所有必填项
```

### 2. 准备 TLS 证书

```bash
mkdir -p deploy/nginx/ssl
cp /path/to/fullchain.pem deploy/nginx/ssl/
cp /path/to/privkey.pem  deploy/nginx/ssl/
chmod 600 deploy/nginx/ssl/*.pem
```

### 3. 启动服务

```bash
cd backend
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d
```

### 4. 初始化数据库

```bash
docker compose -f deploy/docker-compose.prod.yml exec api uv run alembic upgrade head
```

### 5. 验证

```bash
# 健康检查
curl https://your-domain.com/health/live

# 指标端点
curl https://your-domain.com/metrics

# Prometheus UI
open http://your-server:9090
```

## 服务架构

```
                    ┌─────────┐
                    │  Nginx  │ :80/:443
                    │  (TLS)  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │   API   │ :8000 (4 workers)
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         ┌────▼────┐ ┌───▼───┐ ┌───▼────┐
         │Postgres │ │ Redis │ │ Worker │
         └─────────┘ └───┬───┘ └────────┘
                         │
                    ┌────▼────┐
                    │  Beat   │ (定时任务)
                    └─────────┘
```

## 监控

- **Prometheus**: `http://your-server:9090`
  - 告警规则在 `deploy/prometheus/alerts.yml`
  - 覆盖：HTTP 错误率、延迟、AI 调用、Celery 任务、DB 连接池
- **Sentry**: 配置 `SENTRY_DSN` 环境变量后自动集成
  - 捕获：未处理异常、Celery 任务失败、慢事务追踪
- **应用指标**: `https://your-domain.com/metrics`

## 备份

```bash
# 手动执行
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > backup_$(date +%Y%m%d).sql.gz

# 定时备份（添加到 crontab）
0 3 * * * cd /path/to/backend && bash scripts/backup_db.sh >> /var/log/duoduo-backup.log 2>&1
```

## 常见问题

**Q: 启动报 ValueError**
A: `APP_ENV=production` 时会强制校验配置项。检查 `.env` 中：
- `CORS_ALLOWED_ORIGINS` 不能是 `*`
- `AI_PROVIDER` 不能是 `mock`
- `EVALUATION_RUN_MODE` 必须是 `celery`
- `WECHAT_APP_ID/SECRET` 不能为空
- `APP_SECRET_KEY` 至少 32 字符

**Q: Watchdog 没有生效**
A: 确认 `beat` 服务正在运行：`docker compose ps beat`
