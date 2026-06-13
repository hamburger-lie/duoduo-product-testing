# PostgreSQL 备份与恢复

本文档说明如何使用 `scripts/backup_db.sh` 备份 PostgreSQL 数据库、配置定时任务，以及从备份文件恢复数据。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `PGHOST` | `localhost` | PostgreSQL 主机名或容器服务名 |
| `PGPORT` | `5432` | PostgreSQL 端口 |
| `PGUSER` | `postgres` | 连接数据库的用户名 |
| `PGDATABASE` | `duoduo` | 要备份的数据库名 |
| `PGPASSWORD` | 无 | 数据库密码，由调用方提供，脚本不会硬编码 |
| `BACKUP_DIR` | `/backups` | 备份文件输出目录 |
| `BACKUP_RETENTION_DAYS` | `7` | 自动保留最近多少天的备份 |

## 手动运行备份

在宿主机或带有 `pg_dump` 的运维容器中执行：

```bash
cd backend

export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGDATABASE=duoduo
export PGPASSWORD='replace-with-secure-password'
export BACKUP_DIR=/backups
export BACKUP_RETENTION_DAYS=7

bash scripts/backup_db.sh
```

在 Docker Compose 网络中运行时，`PGHOST` 通常使用服务名：

```bash
cd backend

export PGHOST=postgres
export PGPORT=5432
export PGUSER=postgres
export PGDATABASE=duoduo
export PGPASSWORD='replace-with-secure-password'
export BACKUP_DIR=/backups

bash scripts/backup_db.sh
```

脚本成功后会输出：

```text
Backup completed
File: /backups/duoduo_backup_YYYYMMDD_HHMMSS.sql.gz
Size: <bytes> bytes
SHA256: <checksum>
```

## 配置 crontab 定时备份

示例：每天凌晨 3 点执行一次备份。

```bash
crontab -e
```

加入以下内容，并替换密码和路径：

```cron
0 3 * * * PGHOST=localhost PGPORT=5432 PGUSER=postgres PGDATABASE=duoduo PGPASSWORD='replace-with-secure-password' BACKUP_DIR=/backups BACKUP_RETENTION_DAYS=7 /bin/bash /path/to/backend/scripts/backup_db.sh >> /var/log/duoduo-db-backup.log 2>&1
```

建议将 `PGPASSWORD` 放在受限权限的环境文件中，再由 cron 读取：

```bash
chmod 600 /etc/duoduo-db-backup.env
```

```cron
0 3 * * * . /etc/duoduo-db-backup.env && /bin/bash /path/to/backend/scripts/backup_db.sh >> /var/log/duoduo-db-backup.log 2>&1
```

## 从备份恢复

恢复前请确认目标数据库是预期环境，并已完成必要的停机或写入冻结。下面命令会把备份 SQL 导入目标数据库。

```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGDATABASE=duoduo
export PGPASSWORD='replace-with-secure-password'

gunzip -c /backups/duoduo_backup_YYYYMMDD_HHMMSS.sql.gz | \
  psql \
    --host="$PGHOST" \
    --port="$PGPORT" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --set=ON_ERROR_STOP=on
```

如果需要恢复到全新数据库，可先创建数据库：

```bash
createdb \
  --host="$PGHOST" \
  --port="$PGPORT" \
  --username="$PGUSER" \
  "$PGDATABASE"
```

## 验证恢复完整性

恢复后至少检查表数量、核心表行数和应用健康检查。

检查表数量：

```bash
psql \
  --host="$PGHOST" \
  --port="$PGPORT" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --tuples-only \
  --command="select count(*) from information_schema.tables where table_schema = 'public';"
```

检查核心表行数：

```bash
psql \
  --host="$PGHOST" \
  --port="$PGPORT" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --command="
    select 'users' as table_name, count(*) from users
    union all
    select 'products', count(*) from products
    union all
    select 'evaluations', count(*) from evaluations;
  "
```

检查应用 readiness：

```bash
curl --fail http://127.0.0.1:8000/health/ready
```

## 注意事项

- 不要把 `PGPASSWORD` 写进仓库。
- 每次恢复演练后记录备份文件名、SHA256、恢复耗时和验证结果。
- 生产环境建议把 `/backups` 挂载到独立磁盘或对象存储同步目录。
- 备份脚本使用 `find` 清理旧备份，只匹配 `duoduo_backup_*.sql.gz`。
