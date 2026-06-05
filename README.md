# Soul

Soul 是一个包含微信小程序前端、FastAPI 后端、文档、静态报告与本地运行资产的一体化项目仓库。

## 项目结构

```text
.
├── backend/                      # 后端工程与接口文档
│   └── backend/                  # FastAPI 应用、数据库迁移、测试、静态资源
├── miniprogram/                  # 微信小程序端代码
├── docs/                         # 项目文档
├── mockup/                       # 原型与设计稿相关文件
├── tmp_pdf_compare/              # PDF 对比临时资料
├── node_modules/                 # 根目录 Node 依赖
├── miniprogram.zip               # 小程序代码压缩包
├── package.json                  # 根目录工具依赖
└── frontend_backend_interface_gaps.md
```

更完整的前后端分类、端口、接口边界和上传注意事项见
[`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)。

## 技术栈

- 微信小程序：TypeScript、WXML、WXSS
- 后端服务：Python 3.11、FastAPI、SQLAlchemy、Alembic、Celery、Redis
- 本地工具：Node.js、Sharp、uv、pytest、ruff、mypy

## 快速启动

### 后端

```powershell
cd backend\backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

也可以使用后端目录中的脚本：

```powershell
cd backend
.\start_dev.bat
```

### 小程序

1. 使用微信开发者工具打开 `miniprogram` 目录。
2. 按需检查 `miniprogram/project.config.json` 与 `miniprogram/project.private.config.json`。
3. 后端本地服务默认可按项目配置连接到本机接口地址。

## 测试与检查

```powershell
cd backend\backend
uv run pytest
uv run ruff check .
uv run mypy app
```

## 配置说明

仓库中包含本地开发配置、示例配置、静态报告、缓存文件、虚拟环境和依赖目录。本次上传按完整工作区归档处理，因此会保留 `.env`、`.venv`、`node_modules`、日志、缓存和生成文件等本地资产。

如果后续要作为团队协作仓库长期维护，建议再单独整理：

- 将真实密钥迁移到 GitHub Secrets 或部署平台环境变量。
- 将 `.venv`、`node_modules`、缓存和日志改为本地生成。
- 为静态报告或大体积生成文件建立独立存储策略。

## 备注

该仓库按私有仓库保存，适合作为当前 `D:\soul` 工作目录的完整备份与交接快照。
