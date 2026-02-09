# ReDate | 月读 项目文档

欢迎来到 **ReDate** (月读) 的开发者文档中心。

`ReDate` 是一个致力于将 “碎片化信息” 转化为 “结构化洞见” 的自动化内容平台。它采用企业级软件架构设计，结合 **Dagger** 的现代化编排能力与最前沿的 **LLM** 技术，为内容创作者提供了一套可复现、高韧性且易于扩展的解决方案。

## 核心支柱 (Core Pillars)

### 1. Dagger 驱动的统一编排 (Programmable CI/CD)
摒弃了传统脆弱的 YAML 配置文件，ReDate 采用 **[Dagger](https://dagger.io/) Python SDK** 作为核心流水线引擎。  

- **本地与 CI 一致性**: 无论是本地开发机还是 GitHub Actions Runner，业务逻辑均通过容器化的 `ci/main.py` 执行，彻底消除了 *"It works on my machine"* 的环境差异问题。  
- **全栈 Python**: 从业务代码到部署流水线，统一使用 Python 编写，享受完整的类型检查 (Type Hinting) 和 IDE 支持。  

### 2. 六边形架构 (Hexagonal Architecture)
项目严格遵循 **端口与适配器 (Ports and Adapters)** 模式设计，确保业务核心的纯净性：  

- **解耦设计**: `NewsService` 等核心业务逻辑不依赖具体的数据库或 API。  
- **灵活插拔**: 想要从 OpenAI 切换到 Google Gemini？或者从 R2 存储迁移到 SeaweedFS？只需替换相应的“适配器 (Adapter)”，无需修改核心代码。  

### 3. 环境与依赖的确定性 (Hermetic Environments)
利用 **[Pixi](https://prefix.dev/)** 进行包管理，配合 Dagger 的容器化封装：  

- 锁定了从操作系统库 (libc) 到 Python 依赖包 (PyPI) 的所有版本 (`pixi.lock`)。  
- 确保每次构建和运行都在“无尘室”般的隔离环境中进行，保障了系统长期的可维护性。  

### 4. 安全与网络韧性 (Security & Resilience)
- **零信任出口**: 结合 **[Gost](https://gost.run/)** 隧道代理技术，通过加密隧道将出口流量路由至拥有固定 IP 的 VPS，解决了微信等第三方 API 的 IP 白名单限制。  
- **敏感数据隔离**: 所有的 API 密钥和凭证仅在运行时注入容器内存，不落地存储，最大程度减少攻击面。  

### 5. 智能驱动 (AI-Powered RAG)
不仅仅是简单的 API 调用，系统内置了基于 **LanceDB** 的向量检索增强生成 (RAG) 流程：  

- **长时记忆**: 能够回顾并关联历史数据，生成具有时间深度的分析报告。  
- **多模态集成**: 支持从 OpenAI 到 Google Gemini 的无缝切换，处理文本总结、情感分析及配图生成。  

## 文档导航

建议按照以下逻辑路径深入了解项目：  

1.  **[项目架构与设计模式 (Architecture)](architecture.md)**
    *   *必读*。深入解析分层设计、目录结构含义以及 Dagger 流水线的工作原理。
2.  **[API 参考指南 (Reference)](reference/main.md)**
    *   查阅 `Domain Models`、`Ports` 定义以及各个 `Adapter` 的具体配置参数。

---

> **"数月之盈亏，读世之重闻"** —— ReDate，以工程化的严谨，重塑信息的价值。