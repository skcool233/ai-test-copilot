# ai-test-copilot

> 用大模型辅助测试工作的命令行工具：从需求生成测试用例、从失败日志定位根因。

[![CI](https://github.com/skcool233/ai-test-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/skcool233/ai-test-copilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

测试工程师的两个高频痛点——**写用例**和**查失败**——交给大模型打底，人来审。
调用层基于 **OpenAI 兼容接口**，可接入任意兼容服务（硅基流动 / DeepSeek / 通义千问 /
Kimi / 智谱 / OpenAI…），默认硅基流动 + DeepSeek。返回结果用 **Pydantic 结构化校验**
保证可落库。

## 功能

| 命令 | 作用 |
|------|------|
| `generate <spec>` | 读需求/接口描述，产出分维度（功能/边界/异常/安全/性能）的测试计划 |
| `analyze <log>` | 读失败日志，给出失败归类、根因、证据和具体修复建议 |

两个命令都支持 `--json`，方便落库或进一步转成 pytest 骨架。

## 安装

```bash
git clone https://github.com/skcool233/ai-test-copilot.git
cd ai-test-copilot
pip install -e .

# 配置模型服务（OpenAI 兼容）。也可复制 .env.example 为 .env 填写。
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=https://api.siliconflow.cn/v1
export LLM_MODEL=deepseek-ai/DeepSeek-V4-Pro
```

## 用法

```bash
# 从需求生成测试用例
ai-test-copilot generate examples/sample_spec.md

# 导出 JSON 落库
ai-test-copilot generate examples/sample_spec.md --json > plan.json

# 分析失败日志（也支持从 stdin 读）
ai-test-copilot analyze examples/sample_failure.log
cat examples/sample_failure.log | ai-test-copilot analyze -
```

`generate` 输出示例（节选）：

```
╭────────────────── 测试计划 ──────────────────╮
│ 优惠券核销接口                                │
│ 覆盖正常核销、券状态异常、金额门槛与并发场景  │
╰──────────────────────────────────────────────╯
┏━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 编号   ┃ 类型      ┃ 优先级 ┃ 标题                    ┃
┡━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ TC-001 │ functional│   P0   │ 有效券满足门槛核销成功  │
│ TC-002 │ negative  │   P0   │ 已使用券再次核销被拒    │
│ TC-003 │ boundary  │   P1   │ 订单金额恰好等于门槛    │
└────────┴───────────┴────────┴─────────────────────────┘
```

## Web 服务

除了 CLI，还提供一个 FastAPI 网页版（接口 + 浏览器页面）：

```bash
pip install -e ".[web]"
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=https://api.siliconflow.cn/v1
export LLM_MODEL=deepseek-ai/DeepSeek-V4-Pro
# 可选：设置访问密码，保护按量计费的 API key 不被滥用
export APP_PASSWORD=your-pass
uvicorn ai_test_copilot.webapp:app --host 0.0.0.0 --port 8000
```

打开 `http://<服务器IP>:8000`，粘贴需求或失败日志即可。接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/healthz` | 健康检查 |
| POST | `/api/generate` | `{"text": "..."}` → 测试计划 JSON |
| POST | `/api/analyze` | `{"text": "..."}` → 失败分析 JSON |

设置了 `APP_PASSWORD` 后，`/api/*` 需带请求头 `X-App-Password`。

## 部署（systemd）

`deploy/` 下提供了 systemd 单元和幂等安装脚本，适合部署到一台云服务器：

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

脚本会建 venv、装依赖、装并启动 `ai-test-copilot` systemd 服务（开机自启、崩溃重启）。
记得在云厂商**安全组放行对应端口**。

## 设计要点

- **结构化输出**：`models.py` 用 Pydantic 定义 `TestPlan` / `FailureAnalysis`，
  以 JSON 模式 + Schema 提示约束模型输出，再本地 Pydantic 校验，失败自动纠错重试一次。
- **provider 无关**：调用层只依赖 OpenAI 兼容协议，换模型只需改 `LLM_BASE_URL` / `LLM_MODEL`。
- **分层**：CLI（`cli.py`）↔ 业务封装（`client.py`）↔ 提示词（`prompts.py`）↔
  数据模型（`models.py`）解耦，对 SDK 的依赖只收敛在 `client.py`。
- **可测**：CLI 与模型层单测用打桩替换网络调用，CI 离线即可跑通。

## 开发

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## 路线图

- [ ] `generate --to-pytest`：把测试计划转成 pytest 用例骨架
- [ ] 接入 OpenAPI / Swagger 直接生成接口用例
- [ ] 批量分析 CI 失败用例并汇总报告

## License

MIT
