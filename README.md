# ai-test-copilot

> 用大模型辅助测试工作的命令行 + Web 工具：从需求生成测试用例、从失败日志定位根因，
> 支持读取飞书文档/知识库/多维表格，一键导出 pytest 骨架。

[![CI](https://github.com/skcool233/ai-test-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/skcool233/ai-test-copilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

测试工程师的两个高频痛点——**写用例**和**查失败**——交给大模型打底，人来审。
调用层基于 **OpenAI 兼容接口**，可接入任意兼容服务（硅基流动 / DeepSeek / 通义千问 /
Kimi / 智谱 / OpenAI…）；返回结果用 **Pydantic 结构化校验**保证可落库。

## 功能

| 能力 | 说明 |
|------|------|
| 📝 生成用例 | 读需求/接口描述，产出分维度（功能 / 边界 / 异常 / 安全 / 性能）的测试计划 |
| 🔍 分析失败 | 读失败日志，给出失败归类（产品缺陷 / 用例问题 / 不稳定 / 环境）、根因、证据、修复建议 |
| 📄 飞书读取 | 粘贴飞书链接一键拉取正文：新版文档 `/docx/`、知识库 `/wiki/`、多维表格 `/base/`，支持多链接批量 |
| ⬇️ 导出 pytest | 把生成的测试计划一键转成 pytest 用例骨架（`@pytest.mark.skip` + 步骤/预期 docstring） |
| 🖥️ 双入口 | CLI 与 FastAPI Web 服务，逻辑共享 |

## 安装与配置

```bash
git clone https://github.com/skcool233/ai-test-copilot.git
cd ai-test-copilot
pip install -e .            # Web 版：pip install -e ".[web]"

# 模型服务（OpenAI 兼容），也可复制 .env.example 为 .env 填写
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=https://api.siliconflow.cn/v1
export LLM_MODEL=deepseek-ai/DeepSeek-V4-Pro
```

换模型只需改 `LLM_BASE_URL` / `LLM_MODEL`。

## CLI 用法

```bash
# 生成用例（表格输出）
ai-test-copilot generate examples/sample_spec.md

# 导出为 pytest 骨架
ai-test-copilot generate examples/sample_spec.md --to-pytest > test_coupon.py

# 导出 JSON 落库
ai-test-copilot generate examples/sample_spec.md --json > plan.json

# 分析失败日志（支持从 stdin 读）
ai-test-copilot analyze examples/sample_failure.log
cat examples/sample_failure.log | ai-test-copilot analyze -
```

## Web 服务

```bash
pip install -e ".[web]"
export APP_PASSWORD=your-pass     # 可选：访问密码，保护接口不被滥用
uvicorn ai_test_copilot.webapp:app --host 0.0.0.0 --port 8000
```

打开 `http://<IP>:8000`，粘贴需求/日志或飞书链接即可。接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/healthz` | 健康检查 + 飞书配置/授权状态 |
| POST | `/api/generate` | `{"text"}` → 测试计划 JSON |
| POST | `/api/analyze` | `{"text"}` → 失败分析 JSON |
| POST | `/api/to-pytest` | 测试计划 JSON → `{"code","filename"}` |
| POST | `/api/feishu/fetch` | `{"url"}`（可多链接）→ `{"text","count","errors"}` |
| GET  | `/feishu/login` · `/feishu/callback` | 飞书 OAuth 授权 |

设置 `APP_PASSWORD` 后，`/api/*` 需带请求头 `X-App-Password`。

### 飞书文档读取（用户授权 / OAuth）

工具用 **user_access_token 代表你本人**读文档，因此能读「你账号有阅读权限」的任意
文档（含别人知识库里分享给你的），**无需把应用加进每个知识库**。

1. 飞书自建应用开通（**用户身份**）：`docx:document:readonly`、`wiki:wiki:readonly`、
   `bitable:app:readonly`、`offline_access`，并发布。
2. 在「安全设置 → 重定向 URL」登记：`http://<你的IP>:8000/feishu/callback`
3. 配置环境变量并启动：

```bash
export FEISHU_APP_ID=cli_xxxx
export FEISHU_APP_SECRET=xxxx
export FEISHU_REDIRECT_URI=http://<你的IP>:8000/feishu/callback
export FEISHU_TOKEN_FILE=/etc/ai-test-copilot.feishu-token.json
```

4. 页面点「🔑 登录飞书」授权一次，令牌自动续期。

> 多维表格若开启了「高级权限」，API 读不到单元格内容——需关闭高级权限或换一张表。

## 部署（systemd + uv）

`deploy/` 提供 systemd 单元和幂等安装脚本，用 **uv** 管理独立 Python，
兼容 CentOS 7 等老旧系统：

```bash
# 代码放到 /opt/ai-test-copilot 后，在服务器上：
sudo tee /etc/ai-test-copilot.env >/dev/null <<'EOF'
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V4-Pro
APP_PASSWORD=your-pass
PORT=8000
EOF
sudo bash /opt/ai-test-copilot/deploy/server-setup.sh
```

脚本会建 venv、装依赖、装并启动服务（开机自启 + 崩溃重启）。记得在云厂商**安全组放行端口**。

## 设计要点

- **结构化输出**：`models.py` 用 Pydantic 定义 `TestPlan` / `FailureAnalysis`，
  以 JSON 模式 + Schema 提示约束模型，再本地校验，失败自动纠错重试一次。
- **provider 无关**：调用层只依赖 OpenAI 兼容协议（`client.py`）。
- **飞书 OAuth**：授权码流程 + user_access_token + refresh 自动续期（`feishu.py`）。
- **分层解耦**：CLI / Web ↔ 业务封装 ↔ 提示词 ↔ 数据模型，对外部依赖收敛在各自模块。
- **可测**：单测用打桩替换所有网络调用，CI（ruff + pytest，Python 3.10/3.12）离线即可跑。

```
src/ai_test_copilot/
├── cli.py          # 命令行入口
├── webapp.py       # FastAPI 接口 + 页面
├── client.py       # 模型调用（OpenAI 兼容）
├── feishu.py       # 飞书读取（OAuth）
├── pytest_export.py# 测试计划 → pytest 骨架
├── models.py       # Pydantic 数据模型
├── prompts.py      # 提示词
└── static/         # 前端页面
```

## 开发

```bash
pip install -e ".[dev,web]"
ruff check .
pytest -q
```

## 路线图

- [x] 飞书文档 / 知识库 / 多维表格读取（用户授权）
- [x] 一键导出 pytest 骨架
- [ ] 接入 OpenAPI / Swagger 直接生成接口用例
- [ ] 批量分析 CI 失败用例并汇总报告
- [ ] 域名 + HTTPS

## License

MIT
