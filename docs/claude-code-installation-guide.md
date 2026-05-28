# Claude Code 安装与配置指南

## 目录

1. [环境要求](#环境要求)
2. [安装 Claude Code](#安装-claude-code)
3. [配置自定义 API](#配置自定义-api)
4. [跳过网络检查](#跳过网络检查解决连接问题)

---

## 环境要求

- **操作系统**: Windows 10/11, macOS, Linux
- **Node.js**: v18.0.0 或更高版本
- **npm**: v8.0.0 或更高版本
- **IDE**: VS Code 或 Windsurf（可选，用于 IDE 集成）

### 检查 Node.js 版本

```powershell
node --version
npm --version
```

如果未安装 Node.js，从 [nodejs.org](https://nodejs.org/) 下载安装。

---

## 安装 Claude Code

### 方法一：通过 npm 全局安装

```powershell
npm install -g @anthropic-ai/claude-code
```


### 验证安装

```powershell
claude --version
```

---

## 配置自定义 API

如果使用第三方 API 代理服务（如 mimo），需要配置自定义 API 端点。

### 配置文件位置

| 文件 | 路径 | 用途 |
|------|------|------|
| settings.json | `~/.claude/settings.json` | 主配置文件（环境变量、权限、主题等） |
| config.json | `~/.claude/config.json` | API Key 配置 |

> Windows 路径示例: `C:\Users\<用户名>\.claude\`

### 创建 settings.json

在 `~/.claude/` 目录下创建 `settings.json`：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://your-api-proxy.com/anthropic",
    "ANTHROPIC_API_KEY": "your-api-key-here",
    "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  },
  "permissions": {
    "allow": []
  },
  "model": "claude-3-5-sonnet-20241022"
}
```

#### 配置项说明

| 环境变量 | 说明 |
|----------|------|
| `ANTHROPIC_BASE_URL` | 自定义 API 端点 URL |
| `ANTHROPIC_API_KEY` | API 密钥 |
| `ANTHROPIC_MODEL` | 使用的模型名称 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 设为 `1` 禁用非必要网络请求 |

### 创建 config.json

在 `~/.claude/` 目录下创建 `config.json`：

```json
{
  "primaryApiKey": "anything is ok"
}
```

---

## 跳过网络检查（解决连接问题）

Claude Code 启动时会检查 `api.anthropic.com` 的连通性，即使配置了自定义 API 也会先验证官方 API。通过修改 `.claude.json` 文件可以跳过此检查。

### 解决方法

1. 在用户目录下找到 `.claude.json` 文件：
   - **Windows**: `C:\Users\<用户名>\.claude.json`
   - **macOS/Linux**: `~/.claude.json`

2. 编辑该文件：

```bash
# macOS/Linux
nano ~/.claude.json

# 或使用 VS Code
code ~/.claude.json

# Windows PowerShell
notepad $env:USERPROFILE\.claude.json
```

3. 在 JSON 中添加 `"hasCompletedOnboarding": true`：

**修改前**:
```json
{
  "firstStartTime": "2026-05-18T14:14:17.103Z",
  "opusProMigrationComplete": true,
  "sonnet1m45MigrationComplete": true,
  "seenNotifications": {},
  "migrationVersion": 13,
  "userID": "xxxxxxxx"
}
```

**修改后**:
```json
{
  "firstStartTime": "2026-05-18T14:14:17.103Z",
  "opusProMigrationComplete": true,
  "sonnet1m45MigrationComplete": true,
  "seenNotifications": {},
  "migrationVersion": 13,
  "userID": "xxxxxxxx",
  "hasCompletedOnboarding": true
}
```

> **注意**: 在上一个字段后添加英文逗号 `,`，确保符合 JSON 规范。

4. 保存文件后重新启动 Claude Code。

