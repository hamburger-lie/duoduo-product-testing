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
