# 部署与代码同步流程（soul-unified）

本仓库 (`soul-unified`) 是 soul 项目收敛后的**唯一可信源码仓库**，包含：

- 后端服务（`app/`、`tests/`、`alembic/`、`scripts/`、`deploy/` 等）
- 微信小程序前端（`miniprogram/`）
- 文档与设计稿（`docs/`、`mockup/`）

生产服务器 `root@8.163.56.237:/www/soul/backend/backend` 是**线上运行的真相**。
本仓库的 `2026-06-12` baseline 提交即从该服务器快照而来，二者后端应保持一致。

---

## 1. 黄金规则（务必遵守）

1. **绝不用本地 git 历史强推覆盖服务器。** 服务器上的 `/www/soul/backend/backend`
   其 git 历史已被污染、不可信，不要在服务器上做 `git pull --force` / `git reset --hard`
   去“同步”本地历史，否则会破坏线上代码。更新源码请用下面的 rsync/clone 方式。
2. **服务器 `.env` 独立维护，永不进 git。** 生产密钥（`APP_SECRET_KEY`、`DEEPSEEK_API_KEY`、
   `ZHIPU_API_KEY`、`WECHAT_APP_SECRET`、`POSTGRES_PASSWORD`、微信支付私钥 `.pem` 等）
   只存在于服务器本地 `.env` / 受限文件中。仓库只保留 `.env.example`、`.env.production.example` 模板。
3. **任何密钥不入库。** 提交前确认 `.env`、`*.pem`、`*.key` 均被 `.gitignore` 排除，
   并 grep 暂存区无真实密钥值。
4. **支付相关代码（`app/services/pay_service.py`）依赖 `cryptography`**，
   修改依赖时不要误删 `pyproject.toml` 中的 `cryptography>=42.0.0`。

---

## 2. 日常开发流程

```
本地修改  →  本地提交  →  （配置远端后）push 到远端  →  服务器更新源码  →  重建并重启容器
```

### 2.1 本地提交

```bash
# 在 D:\workspace\soul-unified
git add <改动文件>
git commit -m "feat/fix: ..."
```

> 提交前自检：`git diff --cached | grep -iE 'API_KEY|SECRET|PASSWORD|PRIVATE KEY'`
> 应只看到模板占位符 / 环境变量引用，不能有真实值。

### 2.2 配置远端（首次，由你本人完成）

本仓库目前**没有配置任何 remote，也不会自动 push**。需要远端时自行添加：

```bash
git remote add origin <你的私有仓库地址>
git push -u origin master
```

凭证（SSH key / PAT）由你自行配置，不在本任务范围内。

---

## 3. 服务器更新源码（只更新代码，不碰 .env / 数据）

在**本地**用 rsync 推送源码到服务器（推荐，排除密钥与运行时数据）：

```bash
rsync -avz --delete \
  --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='.env' --exclude='*.pem' --exclude='*.key' \
  --exclude='uploads/' --exclude='*.log' --exclude='local_dev.db' \
  ./ root@8.163.56.237:/www/soul/backend/backend/
```

或者在服务器上从你的私有远端 `git clone` / `git pull`（前提：先把服务器那份污染历史移走）：

```bash
# 服务器上，一次性切换到干净仓库（示例）
mv /www/soul/backend/backend /www/soul/backend/backend.bak
git clone <你的私有仓库> /www/soul/backend/backend
cp /www/soul/backend/backend.bak/.env /www/soul/backend/backend/.env   # 保留线上密钥
```

> 无论哪种方式，**`.env` 始终保留服务器本地那份**，不要被仓库模板覆盖。

---

## 4. 重建镜像并重启容器

源码更新后，在服务器上：

```bash
cd /www/soul/backend/backend
docker compose build            # 重新构建镜像（依赖变化时尤其必要）
docker compose up -d            # 滚动重启容器
docker compose ps               # 确认服务健康
docker compose logs -f --tail=100 app   # 观察启动日志
```

数据库结构变更时，执行迁移：

```bash
docker compose exec app uv run alembic upgrade head
```

---

## 5. 回滚

- 镜像层面：保留上一个可用镜像 tag，`docker compose up -d` 指回旧 tag。
- 源码层面：rsync 前先 `cp -r` 备份目录；git 方式则 `git checkout <上一个 commit>` 后重建。
- **切勿**用强推或 `reset --hard` 去回滚服务器历史。

---

## 6. 密钥清单（仅存在于服务器 `.env`，不入库）

| 变量 | 用途 |
|------|------|
| `APP_SECRET_KEY` | 应用签名密钥（≥32 字符） |
| `POSTGRES_PASSWORD` | 数据库密码 |
| `DEEPSEEK_API_KEY` / `ZHIPU_API_KEY` / `ARK_API_KEY` | 各 AI 服务密钥 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信小程序凭证 |
| 微信支付商户私钥 `*.pem` | 支付签名（`pay_service.py` 运行时加载） |

新增密钥时：只改服务器 `.env`，并在 `.env.example` 里加一行**占位符**说明，绝不写真实值。
