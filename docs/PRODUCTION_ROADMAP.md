# 生产化路线图

> 目标：1000+ 用户，微信小程序入口，腾讯云部署，1 个月内上线
> 创建时间：2026-05-18

---

## 当前状态

后端代码基础扎实：分层清晰、294 个测试、CI 流水线完整、日志脱敏、限流机制已有。
但距离承载 1000+ 真实用户，还需要补齐以下工作。

---

## 第一周：代码层必修项（P0 Bug Fix）

这些是代码本身的缺陷，不修会直接出问题。

### 1.1 CORS 配置（0.5h）
- `app/main.py` 加 `CORSMiddleware`
- 允许小程序域名和本地开发域名
- 不做通配 `*`，白名单模式

### 1.2 数据库 session 事务安全（2h）
- service 层 commit 包裹 try/except
- 异常时 rollback + 记录日志
- 或统一用 transaction decorator

### 1.3 数据库 session lazy 初始化（1h）
- engine 和 session factory 移到 lifespan 或 lazy singleton
- 避免 import 时就创建连接池

### 1.4 连接池配置（0.5h）
- `create_async_engine` 加 `pool_size=10, max_overflow=20, pool_recycle=3600`
- 1000 用户并发量不大，默认 pool_size=5 可能不够但 10 足够

### 1.5 Mypy 错误修复（0.5h）
- pyproject.toml 加 celery/redis 的 ignore_missing_imports
- 或安装 types-redis

### 1.6 优雅关停（1h）
- lifespan shutdown 阶段 dispose engine、关闭 redis 连接
- Celery worker 通过 SIGTERM 优雅停止

---

## 第二周：腾讯云部署 + 微信登录

### 2.1 微信小程序真实登录（3h）
- 实现 `code2session` 调用微信接口
- 配置 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`
- 保留 mock login 仅在 `APP_ENV=development` 时可用

### 2.2 腾讯云 COS 对象存储（3h）
- 替换 `mock_upload.py` 为真实 COS SDK
- 实现预签名上传 URL
- 配置 bucket、region、密钥

### 2.3 Dockerfile 安全加固（1h）
- 添加非 root 用户 `USER app`
- 固定 uv 版本 `curl -LsSf https://astral.sh/uv/0.7.x/install.sh`
- multi-stage build 减小镜像体积

### 2.4 腾讯云部署方案（4h）
推荐架构（成本可控）：
```
腾讯云轻量应用服务器 / CVM (2核4G)
├── docker-compose
│   ├── api (uvicorn)
│   ├── worker (celery)
│   ├── nginx (反代 + HTTPS)
│   └── redis
└── 云数据库 PostgreSQL（腾讯云 TDSQL-C 或自建）
```

- 1000 用户不需要 K8s，一台 2核4G 足够
- PostgreSQL 建议用云数据库（自动备份、主从切换）
- Redis 可以容器内自建（数据不关键，限流和 Celery broker 用）

### 2.5 HTTPS + 域名（1h）
- 小程序要求后端必须 HTTPS
- 腾讯云免费 SSL 证书 + nginx 配置
- 域名备案（如果还没备案，这个要提前，需要 5-10 个工作日）

### 2.6 生产环境变量管理（1h）
- 创建 `.env.production` 模板
- `APP_SECRET_KEY` 用 `openssl rand -hex 32` 生成
- AI API Key 通过腾讯云密钥管理配置
- docker-compose.prod.yml 引用 `.env` 而不是硬编码

---

## 第三周：稳定性 + 可观测性

### 3.1 请求日志中间件（1h）
- 记录 method、path、status_code、耗时
- 配合 request_id 可追踪完整请求链路

### 3.2 接入腾讯云日志服务 CLS（2h）
- 容器 stdout → CLS
- 设置告警规则：500 错误率 > 5%、响应时间 > 10s

### 3.3 AI 成本追踪（2h）
- Answer 表已有 token_input/token_output/cost_yuan 字段
- 在 structured_generation adapter 中填入真实 token 消耗
- 加管理端 API 查询总成本

### 3.4 AI 调用熔断（2h）
- DeepSeek 连续失败 N 次后自动降级到 mock 或返回友好错误
- 避免用户一直等待超时

### 3.5 用户级使用限制（1h）
- 每个用户每天最多创建 N 个评测（防止滥用烧 AI 额度）
- 现有的 rate_limit 是请求频率限制，这里是业务量限制

### 3.6 内容审核基础版（2h）
- 产品描述关键词过滤（敏感词库）
- AI 输出基础检查（禁止政治、暴力等内容）
- 不需要一开始就接 GLM 图片审核，文本审核先上

---

## 第四周：联调测试 + 上线

### 4.1 小程序联调（3h）
- 确认所有 API 端点小程序能正常调用
- SSE 流式对话在小程序环境的兼容性测试
- 登录流程端到端验证

### 4.2 压力测试（2h）
- 用 locust 或 k6 模拟 50 并发用户
- 重点测试：评测运行（AI 调用）、对话流式响应
- 确认 2核4G 能扛住

### 4.3 数据库备份（1h）
- 如果用腾讯云数据库：自带自动备份
- 如果自建 PostgreSQL：cron + pg_dump 每日备份到 COS

### 4.4 上线检查清单
- [ ] HTTPS 证书有效
- [ ] 域名备案完成
- [ ] 微信登录可用
- [ ] 图片上传可用
- [ ] AI 评测完整流程跑通
- [ ] 日志可在 CLS 查看
- [ ] 数据库备份配置好
- [ ] `.env` 的 SECRET_KEY 已更换
- [ ] `APP_ENV=production`
- [ ] mock login 在生产环境禁用

---

## 上线后第一个月：观察 + 补充

| 事项 | 触发条件 |
|------|---------|
| 支付/充值 | 确定商业模式后再接入 |
| AI 供应商降级 | DeepSeek 出过故障再考虑备用供应商 |
| K8s 迁移 | 用户超过 5000 或需要弹性伸缩时 |
| Sentry 错误追踪 | CLS 日志不够用时 |
| API 版本前缀 `/api/v1` | 有 breaking change 需求时 |
| 用户数据导出/删除 | 合规审查要求时 |

---

## 成本估算（月）

| 资源 | 规格 | 腾讯云参考价 |
|------|------|-------------|
| CVM/轻量服务器 | 2核4G | ~60-100 元 |
| 云数据库 PostgreSQL | 1核2G | ~100-150 元 |
| COS 对象存储 | 10GB | ~5 元 |
| 域名 + SSL | - | ~50 元/年 |
| DeepSeek API | 1000 用户估算 | ~200-500 元（取决于使用频率） |
| **合计** | | **~400-800 元/月** |

---

## 关键时间风险

1. **域名备案**：如果还没备案，现在就要开始，需要 5-10 个工作日
2. **微信小程序审核**：首次提交审核 1-3 天
3. **DeepSeek API 额度**：确认充值和限额
