<div align="center">

# DBA · OPS · AGENT

### 只读型数据库智能哨兵 · 让数据库自己说清哪里病了，让 DBA 少熬一半的夜。

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-22B546)](#)
[![Status](https://img.shields.io/badge/Status-v0.1%20Production%20Ready-3df0ff)](#)
[![Tests](https://img.shields.io/badge/Tests-25%20passed-22B546)](#)

**🛡️ 只读采集 · 🧠 LLM 根因综合 · 📋 带预案的处置手册 · ⚠️ 绝不自动动手**

<p>
  <a href="https://renshengne.github.io/dba-ops-agent/">🌐 宣传主页</a> ·
  <a href="#-能力矩阵">能力矩阵</a> ·
  <a href="#-架构流水线">架构</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-安全边界">安全边界</a>
</p>

</div>

---

## 🎯 它解决了什么

夜半三点告警炸响，DBA 揉着眼睛连进数据库：`SHOW PROCESSLIST`、查锁、查等待事件、翻慢 SQL、翻执行计划、判断根因、想处置方案……这套动作资深 DBA 要 20 分钟，新人要 2 小时，而且人在慌乱中容易手抖误删。

**DBA OPS AGENT 把这套肌肉记忆装进了 Agent。**

它 7×24 只读盯着你的库，告警或提问触发后，30 秒内递给你一份带根因、带证据、带回滚预案的处置手册——**把判断的活儿留给 DBA，把跑腿的活儿交给 Agent。**

---

## 🔧 能力矩阵

| 能力 | 它干什么 | 产出 |
|------|---------|------|
| **🧭 智能巡检** | cron 定时跑十几套只读 SQL，采集连接数/慢 SQL/锁/容量/复制延迟/缓冲池命中率，按阈值生成正常·警告·严重三态报告 | Markdown + JSON 双产物 |
| **🩺 异常诊断** | 告警触发后串联多指标定位根因，输出"现象→证据→根因→建议"完整链路，不再在视图间反复横跳 | 根因链路 + 等待事件分类 |
| **⚡ 性能诊断** | 拉起慢 SQL 执行计划、TOP SQL 热点、等待事件 TOP N，LLM 结合上下文给瓶颈定位 + 索引/改写建议 | LLM 综合报告 + 待人工验证标注 |
| **🛟 快速恢复** | 诊断结论直接产出可执行脚本 + 影响评估 + 回滚预案（kill 会话/主备切换/参数回滚/容量处置） | 带回滚的处置手册 |

**三方言覆盖**：MySQL · MariaDB · GaussDB/PostgreSQL · Oracle

---

## 🏗️ 架构流水线

一条事件流，从意图到带预案的报告，全程可流式回放：

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│  PLAN   │ -> │ COLLECT  │ -> │ DIAGNOSE │ -> │ ADVISE  │ -> │  DONE   │
│ 解析意图 │    │ 只读采集 │    │ 规则诊断 │    │ LLM综合 │    │ 报告+预案│
│ 绑定实例 │    │ 单点容错 │    │ 根因推断 │    │ 恢复建议 │    │          │
└─────────┘    └──────────┘    └──────────┘    └─────────┘    └──────────┘
```

- **plan**：解析意图，绑定实例与巡检模板，规划采集指标集
- **collect**：并发线程池跑只读采集，单指标失败不中断整体
- **diagnose**：规则引擎阈值比对 + 根因推断 + 等待事件按 CPU/IO/锁/网络归类
- **advise**：LLM 综合根因报告，恢复建议器产出带预案的处置手册
- **done**：报告 + 恢复预案落盘，全链路事件流可回放

---

## 🛡️ 安全边界

> **它很能干，但有一条不敢越的红线：只动嘴，不动手。**

Agent 从设计上被三重只读约束焊死：

1. **账号只读** — 启动即校验账号权限，发现 `INSERT/UPDATE/DROP/ALTER` 等写权限直接拒绝启动（除非显式 `allow_write_account`）
2. **SQL 只读** — 每条采集 SQL 经 `is_read_only_query` 拦截，写语句根本进不了连接
3. **输出只读** — 恢复建议输出为纯文本脚本，代码中无任何 `execute/commit/落库` 调用，每个动作 `requires_human=true`

| 红线 | 数值 |
|------|------|
| 自动写操作 | **0** 次 |
| 账号只读校验 | **100%** |
| 恢复预案类型 | 5 类（kill/切换/回滚/扩容/参数） |
| 数据库方言 | 3 套 |

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/renshengne/dba-ops-agent.git
cd dba-ops-agent
pip install -e .
```

### 配置

复制示例配置，填入你的只读账号和 LLM：

```bash
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml 填入真实连接信息与 API Key
```

### 使用

```bash
# 智能巡检（最常用，跑完自动生成报告）
dba --config config/config.yaml patrol --db prod-mysql

# 异常诊断（指定主题）
dba --config config/config.yaml diagnose --db prod-mysql --topic "大量锁等待"

# 性能诊断（自动采集 slow_queries/top_sql/connection_usage）
dba --config config/config.yaml perf --db prod-mysql

# 快速恢复建议（需先跑过巡检，用报告里的 finding-id）
dba --config config/config.yaml recovery --db prod-mysql --finding-id lock_waits-严重-0

# 对话问诊（向 LLM 提问，带巡检上下文）
dba --config config/config.yaml chat --db prod-mysql --question "为什么缓冲池命中率低"

# Web 控制台（浏览器可视化，实时看事件流）
dba --config config/config.yaml web
# 浏览器打开 http://127.0.0.1:8088/

# 定时巡检（按 config 里 cron 每6小时跑一次）
dba --config config/config.yaml schedule
```

---

## 🧠 LLM 集成

兼容 OpenAI API 协议，支持任何 OpenAI 兼容的 LLM 服务（阿里云 DashScope、智谱、本地 vLLM 等）。LLM 不可用时自动降级到规则结论，不影响核心功能。

```yaml
llm:
  enabled: true
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "${LLM_API_KEY}"
  model: "glm-5.2"
  timeout: 30
```

---

## 🏛️ 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.10+ |
| CLI | Click |
| Web | FastAPI + Uvicorn（SSE 事件流） |
| 采集 | PyMySQL / psycopg2 / oracledb |
| LLM | OpenAI 兼容客户端 |
| 调度 | APScheduler（cron 表达式） |
| 配置 | YAML + 环境变量占位符 |
| 测试 | pytest（25 用例全过） · ruff · mypy |

---

## 📊 工程骨架

- **41** 个文件提交，**3731** 行代码
- **25** 个单元/集成测试，覆盖诊断规则、方言采集、恢复建议、Runner 安全边界
- **3** 套数据库方言实现
- **3** 种交付形态：CLI 对话 / Web 控制台 / 定时巡检

---

## 🌐 宣传主页

**在线预览**：https://renshengne.github.io/dba-ops-agent/

深空蓝科技风宣传页，介绍系统定位、能力矩阵、安全边界。纯 HTML，双击 `docs/index.html` 也能离线查看。

---

## ⚠️ 设计哲学

> 这个 Agent 不追求"全自动无人值守"。它追求的是：**在 DBA 需要做判断的关键时刻，把所有该跑的 SQL 跑完、该串联的证据摆好、该给的预案写清，然后递到 DBA 面前——把"动"的权力永远留给人类。**

能自动化的叫监控，需要判断的才叫运维。这个 Agent 守住后者。

---

<div align="center">

**Made with 🛡️ by DBA, for DBA.**

*MySQL / GaussDB·PostgreSQL / Oracle · OpenAI 兼容 · 只读优先 · 人工兜底*

</div>
