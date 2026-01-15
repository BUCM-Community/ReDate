<h1 align="center">ReDate | 月读</h1>

<p align="center"><strong>数月之盈亏，读世之重闻</strong></p>

## 简介
### 作用
`ReDate` 是一个自动化新闻聚合与发布平台（目前只针对WeChat公众号）。它能够定期从多种数据源（如 Viki 60s）抓取信息，利用 Google Gemini 等大语言模型进行内容的深度理解与摘要生成，并自动将整理好的内容推送到微信公众号等社交媒体平台。

其核心功能包括：
- **每日抓取与归档**：自动获取每日新闻，进行去重校验，并存储至 Cloudflare R2 及 LanceDB 向量数据库。
- **周期性回顾**：基于过去一周或一年的累积数据，利用 AI 生成具有深度见解的周报或年终总结。
- **自动化发布**：全自动化的微信公众号草稿箱发布流程，支持封面图自动匹配与上传。
- **现代化架构**：采用六边形架构（Hexagonal Architecture），实现业务逻辑与基础设施的完全解耦，具备高度的可测试性和可扩展性。

### 名称含义
- 英文正式名称是 `Re:Date` ，取“与你相约，如期而至”之意，就像定期与你（`Re: You`）在邮件上交谈的笔友一样，只不过考虑项目名设置而去掉了 `:` 。另外，其在读音上类似 `Read it!` ，表征本项目的作用和倡议。
- 中文名称“月读”是每月推送的缩写，标志着较长的观察跨度，兼为“阅读”的谐音，另外，其还指日本所使用的“月读”（并非指日本神明），代表观测时间流逝，数着日子过生活。

## Dependency

本项目依赖以下现代化技术栈：

- **运行时/包管理**: [Pixi](https://pixi.prefix.dev/) (基于 Conda 的跨平台包管理器)
- **编程语言**: Python 3.12+ (强类型支持)
- **AI 引擎**: [Google Gemini (google-genai)](https://googleapis.github.io/python-genai/)
- **存储**:
    - **对象存储**: Cloudflare R2 (S3 兼容)
    - **向量数据库**: [LanceDB](https://lancedb.com/)
- **网络代理**: [Gost](https://github.com/ginuerzh/gost) (用于绕过部分 API 的网络限制)
- **文档**: MkDocs (Material theme)

## Get Started!

### 1. 安装 Pixi
参考 [Pixi 官方文档](https://pixi.prefix.dev/latest/#installation) 进行安装。

### 2. 配置环境
复制环境模板并填写必要的 API Key：
```bash
cp .env.example .env
# 编辑 .env 文件，填入 Gemini, R2, WeChat 等配置
```
请注意不要将`.env`上传公开以免API Key泄露，建议使用**系统环境变量**。

### 3. 运行项目
使用 Pixi 运行预定义的任务：
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
- 本项目目前仍在搭建脚手架，尚处于概念验证阶段，GitHub Actions暂时禁用。
- 待完成下面的任务后，将发布目前方案选型的第一版。
- 建议查看`docs/index.md`，注意PR不能直接推送到main分支。

[ ] 完成 `pixi.toml`中的正确环境配置，比如`build-variants`  
[ ] GitHub Actions的适配  
[ ] docker相关配置的适配  
[ ] 文档配置和文档的适配  
[ ] 业务逻辑验证和测试  
[ ] 其他琐碎的 DEBUG  

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
