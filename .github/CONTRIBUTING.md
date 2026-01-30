# 贡献指南 (Contributing to ReDate)

首先，感谢您考虑为 ReDate 做出贡献！正是像您这样的人使 ReDate 成为如此出色的工具。
我们非常高兴你能来参与。无论你是修复 Bug、编写文档还是通过 Issue 提出建议，我们都视你为社区的一份子。

## AI 代码生成策略 (AI Policy)

我们拥抱技术进步，允许使用 AI 辅助工具（如 GitHub Copilot, Cursor, ChatGPT 等）来提高开发效率，但必须遵守以下原则：

1.  **人类责任制 (Human Accountability)**：您必须为您提交的代码负全责。不要提交您未完全理解或未经过测试的 AI 生成代码。
2.  **版权合规**: 严禁直接复制 AI 生成的大段不明来源的代码，以避免潜在的许可证污染。
3.  **标识**: 如果您的 Pull Request 中包含超过 30% 的 AI 生成逻辑，建议在 PR 描述中简要说明，以便 Reviewer 进行针对性审查。

## 开发工作流 (Workflow)

我们遵循标准的 GitHub Flow：

1.  **同步分支**: 在开始工作前，请确保你的 `dev` 分支是最新的。
2.  **新建分支**:
    *   功能开发: `git checkout -b feat/<your-feature>`
    *   Bug 修复: `git checkout -b fix/<issue-number>`
    *   文档修改: `git checkout -b docs/<doc-to-update>-update`
3.  **提交代码 (Commits)**: 请参阅下方的[提交规范](#-提交规范-commit-convention)。
4.  **提交 PR (Pull Request)**: 将代码推送到你的 Fork 仓库，并在 GitHub 上发起 Pull Request。

## 提交规范 (Commit Convention)

我们严格遵循 **[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/#specification)** 规范，以便自动生成更新日志。
格式：`<类型>(<范围>): <描述>`

**常用类型 (Type):**
*   `feat`: 新增功能
*   `fix`: 修复 Bug
*   `docs`: 文档变更
*   `style`: 代码格式（不影响代码运行的变动）
*   `refactor`: 代码重构（既不是新增功能也不是修改 bug 的代码变动）
*   `chore`: 构建过程或辅助工具的变动

**示例:**
*   `feat(user): add login via wechat`
*   `fix(util_date): correct date calculation logic`

## 提交前检查 (Pre-submission Checks)

在提交 PR 之前，请确保：
*   [ ] 已开启了相应的ISSUSE或在他人的相应ISSUE中留言负责该问题。
*   [ ] 代码已通过 Lint 检查。
*   [ ] 新增功能已包含单元测试。
*   [ ] 没有包含敏感信息（如 API Keys）。