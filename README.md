<h1 align="center">ReDate | 月读</h1>

<p align="center"><strong>数月之盈亏，读世之重闻</strong></p>

## 简介
### 作用
`ReDate` 是一个自动化新闻聚合与发布平台（目前只针对WeChat公众号）。它能够定期从多种数据源（如 [Viki 60s](https://github.com/vikiboss/60s)）抓取信息，利用 Google Gemini 等大语言模型进行内容的深度理解与摘要生成，并自动将整理好的内容推送到微信公众号等社交媒体平台。

其核心功能包括：
- **每日抓取与归档**：自动获取每日新闻，进行去重校验，并存储至 Cloudflare R2 / SeaweedFS 对象存储库 及 LanceDB 向量数据库。
- **周期性回顾**：基于过去一周或一年的累积数据，利用 AI 生成具有深度见解的周报或年终总结。
- **自动化发布**：全自动化的微信公众号草稿箱发布流程，支持封面图自动匹配与上传。
- **现代化架构**：采用六边形架构（Hexagonal Architecture），实现业务逻辑与基础设施的完全解耦，具备高度的可测试性和可扩展性。

### 名称含义
- 英文正式名称是 `Re:Date` ，取“与你相约，如期而至”之意，就像定期与你（`Re: You`）在邮件上交谈的笔友一样，只不过考虑项目名设置而去掉了 `:` 。另外，其在读音上类似 `Read it!` ，表征本项目的作用和倡议。
- 中文名称“月读”是每月推送的缩写，标志着较长的观察跨度，兼为“阅读”的谐音，另外，其还指日本所使用的“月读”（并非指日本神明），代表观测时间流逝，数着日子过生活。

## Dependency

本项目依赖以下现代化技术栈：

- **运行时/包管理**: [Pixi](https://pixi.prefix.dev/) (基于 Conda 生态和 uv-solver 的跨平台包管理器)
- **编程语言**: Python 3.11-3.14
- **AI 引擎**: [Google Gemini (google-genai)](https://googleapis.github.io/python-genai/) and [OpenRouter](https://openrouter.ai/docs/quickstart) / [SiliconFlow](https://www.siliconflow.com/) (OpenAI API)
- **存储**:
    - **对象存储**: [Cloudflare R2](https://developers.cloudflare.com/r2/get-started/) / [SeaweedFS](https://github.com/seaweedfs/seaweedfs) ([S3 Protocol Based](https://docs.aws.amazon.com/AmazonS3/latest/API/Type_API_Reference.html))
    - **向量数据库**: [LanceDB](https://lancedb.com/)
- **网络代理**: [Gost](https://github.com/ginuerzh/gost) (用于绕过WeChat API 的网络限制)
- **文档**: MkDocs (Material theme)

## Get Started!

### 1. Pixi 和 Dependency 安装

**CAUTION:**
- 参考 [Pixi 官方文档](https://pixi.prefix.dev/latest/#installation) 安装 `pixi`。
- DO NOT 硬编码或者将`.env`上传公开以免API Key泄露，建议使用**系统环境变量**。

```bash
# 1. (可选) 如果未安装 pixi，请先执行安装
# curl -fsSL https://pixi.sh/install.sh | bash

# 2. 克隆仓库
git clone https://github.com/BUCM-Community/ReDate.git

# 3. 进入项目目录
cd ReDate

# 4. 安装依赖 (基于 pixi.toml)
# 这将自动创建虚拟环境并安装 Python、PyArrow、LanceDB 等所有依赖
pixi install

# 5. 初始化配置文件
# 复制示例配置，后续请编辑 .env 填入 API Key
cp .env.example .env

# 6. 验证安装
# 运行帮助命令，确保环境正常
pixi run python -m redate.main --help
```

### 2. 运行预定义任务

```bash
# 运行每日任务
pixi run start-daily

# 运行每周总结
pixi run start-weekly

# 运行年度回顾
pixi run start-yearly
```

## Development
## TODO List
- 本项目仍在搭建脚手架，尚处于概念验证阶段，GitHub Actions暂时禁用。
- 建议查看`docs/index.md`，注意PR不能直接推送到main分支，具体的贡献指南请查看 **[CONTRIBUTING.md](./.github/CONTRIBUTING.md)**。

### 代码规范与质量保证
本项目执行严格的代码审查与类型检查：
```bash
pixi run lint      # 运行 Ruff 进行静态分析
pixi run format    # 格式化代码
pixi run typecheck # 运行 Mypy 类型检查
pixi run test      # 运行 Pytest 单元测试
```

### 架构约束
本项目使用 `import-linter` 强制执行分层架构约束，确保依赖方向始终从基础设施指向领域核心：
```bash
pixi run contract-check
```

### 文档预览
```bash
pixi run docs-serve
```

## License
Mozilla Public License Version 2.0 License. 详见 [LICENSE](LICENSE) 文件。
