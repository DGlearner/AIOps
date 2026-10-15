# 企业多源日志异常检测与智能运维 Agent 设计计划

## 1. 项目目标

本项目面向企业内部多源异构日志场景，将 Linux、MySQL、Docker、Nginx、应用服务等组件产生的日志统一接入，完成异常检测、告警分级、Incident 聚合、跨组件根因分析，并提供面向运维人员的对话式 Agent。

系统设计的核心边界是：

```text
规则系统负责：发现异常、统计计数、判断阈值、生成告警、初步分级。

LLM/Agent 负责：解释异常、关联多个告警、推理根因、调用工具补充上下文、生成运维报告、支持对话查询。
```

因此，本项目不让 LLM 直接读取海量原始日志，也不让 LLM 代替确定性的规则检测链路。LLM 只在中高危、跨组件、原因不明确、用户主动追问等场景中介入。

## 2. 推荐技术栈

当前计划使用：

```text
Python
FastAPI
Kafka
Redis
PostgreSQL
pgvector
LangChain
LangGraph
```

各技术的职责划分如下：

```text
Python:
- 日志解析 Worker
- 规则检测 Worker
- Incident 聚合 Worker
- Agent 任务 Worker

FastAPI:
- 告警查询接口
- Incident 查询接口
- 规则配置接口
- 运维对话接口
- Agent 分析入口

Kafka:
- raw_logs 原始日志流
- normalized_events 标准化事件流
- alerts 告警事件流
- incidents Incident 事件流
- agent_tasks Agent 分析任务流

Redis:
- 滑动窗口计数
- 告警去重
- 告警抑制
- Incident 临时聚合缓存
- 对话短期状态
- 任务状态缓存

PostgreSQL:
- 规则配置
- 标准化事件元数据
- 告警
- Incident
- 对话历史
- 工具调用记录
- 诊断报告
- 服务依赖关系
- Runbook

pgvector:
- 历史 Incident 摘要向量检索
- Runbook 向量检索
- 运维知识库检索
- 对话压缩摘要检索

Milvus:
- 大规模 Runbook / 历史故障 / 对话摘要向量检索
- 保存 embedding 与元数据引用，不作为事实数据源
- 返回 record_id 后回 PostgreSQL 查询完整内容
- 不用于 raw_logs / normalized_events 的高吞吐实时检测

LangChain:
- RAG 链路
- Tool 封装
- Prompt 管理
- LLM 调用适配

LangGraph:
- Agent 工作流编排
- 多步骤诊断状态机
- Tool calling 流程
- 多 Agent 协作扩展
```

## 3. 系统分层

系统采用 L0-L5 分层设计：

```text
L0 原始日志采集与存储
L1 日志解析与事件标准化
L2 异常规则检测与计数聚合
L3 告警生成、分级与 Incident 聚合
L4 LLM/Agent 跨源分析与根因推理
L5 运维对话 Agent 与长期记忆/RAG
```

其中：

```text
L0-L3 不依赖 LLM
L4-L5 引入 LLM/Agent
```

## 4. 总体架构

```text
          +------------------+
          | Log Sources       |
          | Linux/MySQL/App   |
          +---------+--------+
                    |
                    v
          +------------------+
          | Kafka: raw_logs   |
          +---------+--------+
                    |
                    v
          +------------------+
          | Parser Worker     |
          | Python regex/json |
          +---------+--------+
                    |
                    v
      +--------------------------+
      | Kafka: normalized_events |
      +------------+-------------+
                   |
                   v
          +------------------+
          | Detection Worker |
          | Rules + Redis    |
          +---------+--------+
                    |
                    v
          +----------------+
          | Kafka: alerts  |
          +--------+-------+
                   |
                   v
          +--------------------+
          | Incident Correlator |
          | Redis + PostgreSQL  |
          +---------+----------+
                    |
          +---------+----------+
          |                    |
          v                    v
+------------------+   +----------------------+
| Direct Alerting   |   | Kafka: agent_tasks   |
| low/medium/high   |   +----------+-----------+
+------------------+              |
                                  v
                         +------------------+
                         | LangGraph Agent  |
                         | Diagnosis Flow   |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         | FastAPI Chat/API |
                         +------------------+
```

## 5. L0 原始日志采集

L0 负责接入不同来源的日志，先不做复杂判断。

初期日志来源：

```text
Linux:
- auth.log
- syslog
- journalctl

MySQL:
- error log
- slow query log

Docker:
- container logs
- container event

Nginx:
- access log
- error log

应用服务:
- 登录日志
- 业务错误日志
- 数据库连接错误日志
```

日志可先通过文件模拟、HTTP API 或简单采集脚本进入系统；后续再接入 Filebeat、Vector、Fluent Bit 等采集组件。

## 6. L1 日志解析与标准化

L1 负责将原始日志解析为统一事件结构，不直接生成告警。

不同组件使用不同解析器：

```text
Linux 日志：regex_linux
MySQL 日志：regex_mysql
Docker 日志：regex_docker
Nginx 日志：regex_nginx
应用日志：json parser / regex_app
```

标准事件模型建议如下：

```json
{
  "event_id": "evt_xxx",
  "timestamp": "2026-06-03T14:03:12+08:00",
  "source_type": "linux",
  "source_name": "auth.log",
  "host": "app-prod-01",
  "service": "login-service",
  "component": "ssh",
  "event_type": "login_failed",
  "message": "Failed password for root from 1.2.3.4 port 52231 ssh2",
  "severity_hint": "low",
  "fields": {
    "src_ip": "1.2.3.4",
    "user": "root",
    "port": 52231
  },
  "tags": ["auth", "security", "ssh"]
}
```

核心字段：

```text
timestamp: 事件时间
source_type: 日志来源类型
host: 主机名
service: 所属服务
component: 组件
event_type: 标准事件类型
message: 原始日志文本
fields: 解析出的结构化字段
severity_hint: 单条事件初始严重性
tags: 标签
```

## 7. L2 异常检测与计数聚合

L2 使用确定性规则、滑动窗口计数和基线检测判断是否出现异常。

### 7.1 规则检测

适合直接规则识别的事件：

```text
login_failed
sudo_failed
mysql_connection_refused
mysql_too_many_connections
mysql_access_denied
container_exited
container_restart
oom_killed
http_500_spike
db_connection_error
upstream_timeout
```

### 7.2 计数阈值

示例规则：

```text
同一 src_ip 5 分钟内 SSH 登录失败 >= 10 次
同一用户 5 分钟内登录失败 >= 20 次
同一服务 1 分钟 HTTP 500 >= 100 次
MySQL connection refused 3 分钟内 >= 10 次
Docker container 10 分钟内 restart >= 3 次
同一服务 5 分钟内 DB connection error >= 30 次
```

### 7.3 Redis 滑动窗口

Redis 用于实时计数和去重：

```text
login_failed:{src_ip}:{host}
login_failed_user:{user}:{host}
mysql_error:{host}:{event_type}
http_5xx:{service}
container_restart:{container_id}
alert_dedup:{fingerprint}
incident_buffer:{service}
conversation_state:{session_id}
```

### 7.4 基线检测

后续可加入历史基线：

```text
过去 7 天同时间段平均 error 数量
过去 30 天 P95 / P99 日志量
当前值是否超过历史均值 + N 倍标准差
当前错误率是否超过服务历史正常波动范围
```

基线检测适合：

```text
服务 error rate 突增
接口 5xx 异常升高
数据库慢查询数量异常升高
某主机登录失败量异常升高
```

## 8. L3 告警生成、分级与 Incident 聚合

L3 负责生成告警、确定等级，并将多个相关告警聚合为 Incident。

### 8.1 告警等级

建议等级：

```text
info: 记录，不主动通知
low: 低危，聚合展示或分钟级摘要
medium: 中危，进入告警系统
high: 高危，需要快速关注，可触发 Agent 分析
critical: 严重故障或安全事件，需要立即响应
```

### 8.2 分级依据

告警分级不只看计数，还应综合：

```text
事件类型
发生频率
持续时间
影响范围
资产重要性
是否跨组件
是否命中安全风险
是否有历史相似故障
是否影响核心业务
```

示例：

```text
单次 SSH 登录失败
=> info / low

同 IP 5 分钟失败 10 次
=> medium

同 IP 5 分钟失败 100 次
=> high

多个 IP 同时爆破同一核心主机
=> high / critical

MySQL 单次连接失败
=> low

MySQL connection refused 持续 3 分钟
=> high

MySQL down + 多个应用 DB error + 用户登录失败
=> critical
```

### 8.3 Incident 聚合

Incident 聚合目标：

```text
把同一时间窗口、同一服务、同一主机、同一依赖链上的多个告警合并成一个可分析事件。
```

聚合维度：

```text
时间窗口：5-15 分钟
服务：login-service、payment-service
主机：app-prod-01、db-prod-01
组件：mysql、nginx、docker
依赖关系：login-service -> mysql
事件类型：login_failed、db_connection_error、http_500_spike
```

示例：

```text
告警 A: MySQL connection refused, db-prod-01, 14:03
告警 B: login-service DB error, app-prod-01, 14:04
告警 C: 用户登录失败暴增, login-service, 14:04
告警 D: Nginx 500 暴增, 14:05

聚合为:
Incident: login-service 登录异常，疑似 MySQL 不可用导致
```

## 9. LLM/Agent 触发边界

LLM 不参与 L0-L3 的常规检测，只在符合策略时触发。

### 9.1 不触发 LLM 的情况

```text
单条 low 告警
单条 medium 且规则解释明确
重复出现的已知告警
单组件、单原因、已有明确 runbook 的告警
只需要计数和通知的告警
```

示例：

```text
同 IP 5 分钟 SSH 失败 12 次
=> medium
=> 直接告警，不触发 LLM
```

```text
Docker container exited once
=> low
=> 记录或聚合，不触发 LLM
```

### 9.2 触发 LLM 的情况

```text
多个 medium/high 告警在同一时间窗口内出现
同一服务跨多个组件异常
同一主机多个组件异常
告警等级 high 或 critical，且根因不明确
短时间内告警数量暴增，需要归并
当前 Incident 与历史故障相似
安全事件疑似攻击链
用户主动询问某个告警
需要生成诊断报告或处置建议
```

建议触发条件：

```text
severity >= high AND root_cause_unclear = true

OR

5 分钟内同一 service 关联告警类型 >= 2

OR

5 分钟内跨组件 high/medium 告警数量 >= N

OR

Incident 影响核心服务

OR

用户主动请求分析
```

## 10. Agent 输入设计

Agent 不接收海量原始日志，而接收压缩后的 Incident Context。

示例：

```json
{
  "incident_id": "inc_20260603_001",
  "time_window": "2026-06-03 14:00-14:10",
  "severity": "high",
  "affected_services": ["login-service"],
  "affected_hosts": ["app-prod-01", "db-prod-01"],
  "alerts": [
    {
      "alert_type": "mysql_connection_refused",
      "source": "mysql",
      "count": 48,
      "severity": "high",
      "first_seen": "14:03:10",
      "last_seen": "14:08:42"
    },
    {
      "alert_type": "login_failed_spike",
      "source": "app",
      "count": 320,
      "severity": "medium",
      "first_seen": "14:04:02",
      "last_seen": "14:08:55"
    },
    {
      "alert_type": "http_500_spike",
      "source": "nginx",
      "count": 210,
      "severity": "medium",
      "first_seen": "14:04:30",
      "last_seen": "14:09:00"
    }
  ],
  "log_samples": [
    "mysql: Can't connect to local MySQL server",
    "login-service: DB connection refused",
    "nginx: upstream returned 500"
  ],
  "dependency_graph": {
    "login-service": ["mysql", "redis"]
  },
  "recent_changes": [
    {
      "type": "deployment",
      "service": "login-service",
      "time": "13:55"
    }
  ]
}
```

## 10.5 触发式 ReAct 诊断策略

Agent 不需要在一开始接收所有跨组件日志。更合理的方式是由 L0-L3 先发现异常并生成 Incident，Agent 只接收触发点和最小上下文，然后根据根因假设主动调用工具查询证据。

典型流程：

```text
规则系统发现高危/复杂异常
-> 生成 alert / incident
-> 触发 Agent
-> Agent 读取触发点、时间窗口、影响服务、原始日志样本
-> Agent 生成若干根因假设
-> Agent 调用 tool 查询相关证据
-> Agent 根据 observation 更新假设
-> 重复查询、验证、排除
-> 输出诊断报告或人工排查报告
```

例如：

```text
触发点:
login-service 1 分钟内多个 IP 登录失败，达到 high 告警。

Agent 初始假设:
1. 暴力破解或撞库攻击。
2. MySQL 不可用导致登录接口失败。
3. auth-service 故障。
4. 最近发布导致配置错误。

Agent 查询路径:
1. 查询 login-service 近 5 分钟是否有 DB connection error。
2. 如果有，再查询 MySQL 近 5 分钟是否有 connection refused / shutdown。
3. 如果没有，再查询 auth-service 是否有 5xx / timeout。
4. 再查询最近部署记录或历史相似故障。
```

这属于 Trigger-based ReAct Agent，而不是 Batch Log Summarization Agent。

边界原则：

```text
Agent 不负责发现异常。
Agent 不直接扫描海量原始日志。
Agent 负责在 Incident 发生后，基于假设调用工具调查原因。
Agent 优先查询结构化事件、告警、Incident、历史故障和服务依赖。
```

Agent 可调用的查询工具包括：

```text
query_normalized_events:
按 source_type、service、host、event_type、time_window 查询标准化事件。

query_alerts:
查询某时间窗口内的相关告警。

query_incidents:
查询同时间窗口、同服务或同主机的 Incident。

query_recent_raw_logs:
查询有限数量的原始日志样本。

query_service_dependencies:
查询服务依赖关系，例如 login-service -> mysql。

query_recent_deployments:
查询最近发布记录。

query_runbooks:
查询运维手册。

query_historical_incidents:
查询历史相似故障。

query_redis_counters:
查询短期窗口计数和当前异常规模。
```

为了支持 Agent 按条件查询近几分钟事件，后续需要增加：

```text
event_sink_worker:
Kafka normalized_events -> PostgreSQL / ClickHouse / OpenSearch
```

Kafka 适合流式传递，不适合作为 Agent 的历史查询库。Agent 查询历史日志和事件时，应优先访问 PostgreSQL、ClickHouse、OpenSearch 或其他可查询存储。

## 11. LangGraph Agent 工作流

本项目主 Agent 编排框架采用 LangGraph。LangGraph 主要负责 L4-L5 的状态化诊断、工具调用、RAG 检索、根因分析和运维对话，不参与 L0-L3 的高吞吐日志检测主链路。

也就是说：

```text
L0-L3:
使用 Python Worker、Kafka、Redis、PostgreSQL 完成确定性日志处理、规则检测、告警分级和 Incident 聚合。

L4-L5:
使用 LangGraph 编排 Agent 工作流，对复杂 Incident 做智能分析、工具调用、上下文保存和运维对话。
```

初期建议用一个 LangGraph 诊断工作流承载多个职责明确的 node，而不是一开始拆成复杂 multi-agent。这样既能体现 multi-agent workflow 的设计思想，也能避免过早引入多框架、多进程、多服务协作带来的复杂度。

诊断流程：

```text
Start
  -> LoadIncidentContext
  -> RetrieveSimilarIncidents
  -> CheckServiceDependencies
  -> QueryRelatedLogs
  -> AnalyzeRootCause
  -> GenerateEvidenceChain
  -> GenerateRecommendation
  -> SaveDiagnosis
  -> End
```

更接近 ReAct 的诊断流程为：

```text
Start
  -> LoadIncidentContext
  -> GenerateHypotheses
  -> SelectNextTool
  -> ExecuteTool
  -> UpdateEvidence
  -> EvaluateConfidence
  -> ShouldStop?
       | confidence >= threshold -> GenerateDiagnosisReport
       | tool_calls >= max_tool_calls -> GenerateHumanReviewReport
       | otherwise -> SelectNextTool
  -> SaveDiagnosis
  -> End
```

其中 `ShouldStop` 是关键控制节点，用于防止 Agent 无限循环查询。

### 11.1 Node 职责划分

LangGraph 中的 node 可以按职责分为四类：

```text
确定性 Node:
- LoadIncidentContext
- CheckServiceDependencies
- SaveDiagnosis
- UpdateConversationState

Tool Node:
- QueryRelatedLogs
- RetrieveSimilarIncidents
- QueryRunbook
- QueryRecentDeployments
- QueryMetrics

LLM Reasoning Node:
- AnalyzeRootCause
- GenerateEvidenceChain
- GenerateRecommendation
- GenerateChatResponse

Control Node:
- ShouldTriggerAgent
- ShouldCallMoreTools
- ShouldAskHumanConfirmation
- RouteUserIntent
```

这种划分的目标是：让每个 node 的输入、输出和责任边界都清晰可测，而不是把所有逻辑都塞进一个大 prompt。

### 11.2 主要节点说明

```text
LoadIncidentContext:
加载 Incident、alerts、日志样本、服务信息。

RetrieveSimilarIncidents:
从 pgvector 检索历史相似故障和 runbook。

CheckServiceDependencies:
查询服务依赖关系，例如 login-service -> mysql。

QueryRelatedLogs:
调用日志查询工具，获取有限窗口内的相关日志样本。

AnalyzeRootCause:
生成根因假设和置信度。

GenerateEvidenceChain:
整理证据链，说明为什么支持该根因。

GenerateRecommendation:
生成下一步检查和处置建议。

SaveDiagnosis:
保存诊断报告和工具调用记录。
```

### 11.3 推荐的 LangGraph State

LangGraph 的 state 应保存一次诊断流程中需要持续传递和更新的信息。

示例：

```json
{
  "incident_id": "inc_20260603_001",
  "incident_context": {},
  "related_alerts": [],
  "log_samples": [],
  "service_dependencies": {},
  "similar_incidents": [],
  "runbooks": [],
  "tool_results": [],
  "root_cause_hypotheses": [],
  "evidence_chain": [],
  "ruled_out_hypotheses": [],
  "recommendations": [],
  "diagnosis_report": "",
  "diagnosis_status": "running",
  "confidence": 0.0,
  "tool_call_count": 0,
  "max_tool_calls": 5,
  "max_reasoning_steps": 5,
  "max_runtime_seconds": 60,
  "stop_reason": null,
  "conversation_id": "conv_001",
  "user_question": "",
  "chat_response": "",
  "requires_human_confirmation": false
}
```

### 11.4 为什么主用 LangGraph

LangGraph 适合本项目的原因：

```text
状态化:
Incident 分析不是单轮问答，需要在多个步骤中持续维护上下文。

可编排:
可以明确控制先加载 Incident，再查历史，再查日志，最后生成诊断。

可观测:
每个 node 的输入输出可记录，便于调试和复盘。

可扩展:
后续可以将某些 node 演进为独立 Agent 或独立服务。

适合 human-in-the-loop:
高危操作或不确定结论可以插入人工确认。

适合工具调用:
可以把日志查询、部署查询、Runbook 查询、历史故障检索作为工具节点。
```

### 11.5 与 OpenAI Agents SDK 和 CrewAI 的关系

本项目初期不建议同时引入多个 Agent 框架，避免框架堆叠和职责混乱。

建议策略：

```text
LangGraph:
作为主 Agent 编排框架，实际承担诊断工作流和对话状态管理。

OpenAI Agents SDK:
作为设计参考，借鉴 handoff、tool calling、guardrails、tracing、session 等思想。
初期不作为主工程依赖。

CrewAI:
只参考其角色分工表达方式，不作为主框架。
本项目更偏生产级 AIOps 事件流与诊断系统，不适合做成简单的 Agent + Task + Crew 展示型结构。
```

因此，项目中的 multi-agent 能力主要通过 LangGraph node 职责划分体现：

```text
Correlation Node / Agent-like role:
负责跨组件告警关联。

Retrieval Node / Agent-like role:
负责历史 Incident 和 Runbook 检索。

Tool Node / Agent-like role:
负责查询日志、部署、指标和服务依赖。

Diagnosis Node / Agent-like role:
负责根因推理和证据链生成。

Report Node / Agent-like role:
负责生成运维诊断报告。

Chat Node / Agent-like role:
负责面向运维人员的追问和上下文对话。
```

后续如果系统复杂度上升，可以再将这些 node 拆成多个独立 Agent 或子图，但 MVP 阶段保持一个 LangGraph 主工作流更稳妥。

### 11.6 Agent 兜底机制

Agent 必须有明确的停止条件，不能无限循环调用工具或反复推理。

建议默认限制：

```text
max_tool_calls = 5
max_reasoning_steps = 5
max_runtime_seconds = 60
min_confidence_to_conclude = 0.7
```

如果 Agent 达到限制后仍不能形成高置信度根因判断，应停止查询并生成 `needs_human_review` 报告。

诊断输出分为两类：

```text
confirmed_diagnosis:
已收敛，给出最可能根因、证据链、影响范围和处置建议。

needs_human_review:
未收敛，交给人工继续排查，同时提供已排查路径和剩余假设。
```

兜底报告必须包含：

```text
1. 异常触发点
   哪个 alert / incident 触发了 Agent。
   例如：login-service 1 分钟内多个 IP 登录失败 120 次。

2. 原始证据
   触发异常对应的原始日志样本、标准化 event、告警 summary、时间窗口。

3. 已排查内容
   Agent 调用了哪些 tool，每次查询了什么，观察到什么结果。

4. 已排除假设
   例如：未发现 MySQL connection refused，因此暂不支持 MySQL 不可用假设。

5. 未确认的剩余假设
   例如：疑似 auth-service 故障，但缺少指标证据。

6. 建议人工下一步
   例如：检查 MySQL 进程状态、查看 auth-service 指标、确认最近发布。

7. 置信度与停止原因
   例如：confidence=0.42, stop_reason=max_tool_calls_reached。
```

每次 tool 调用前，Agent 都应记录：

```text
要验证哪个假设？
为什么调用这个工具？
查询的时间窗口是什么？
预期看到什么证据？
```

这样即使 Agent 未能判断根因，也能为运维人员缩小排查范围。

### 11.7 当前 MVP 已实现的 LangGraph 诊断流

当前 MVP 已将 L4 诊断入口接入 LangGraph，诊断只在 Incident 之后触发，不参与 L0-L3 的日志解析、规则检测和告警聚合主链路。

已实现流程：

```text
Incident context
-> initialize
-> tool_step
   -> SelectNextTool
   -> ExecuteTool
   -> UpdateEvidence
   -> ShouldStop / MoveToNextHypothesis
-> finish
   -> GenerateRecommendations
-> DiagnosisReport
```

当前 LangGraph node 职责：

```text
initialize:
根据 Incident 的 event_types、affected_hosts、affected_services 生成根因假设。

tool_step:
选择一个查询工具，调用 PostgreSQL / Redis 查询相关 events、alerts、incidents，并更新证据链、置信度、已排除假设和工具调用摘要。

route_after_tool:
只读取状态决定继续查询还是结束，不在路由函数中修改状态。

finish:
根据 root_cause 和 stop_reason 生成处置建议。
```

当前可调用工具：

```text
query_events_tool:
查询 PostgreSQL 中的 normalized_events。

query_alerts_tool:
查询 PostgreSQL 中的 alerts。

query_incidents_tool:
查询 PostgreSQL 中的 incidents。

query_redis_counters_tool:
查询 Redis 中的短期窗口计数。

query_service_dependencies_tool:
查询 PostgreSQL 中的 service_dependencies，用于确认某个服务依赖哪些数据库、缓存、下游服务或外部系统。

query_recent_deployments_tool:
查询 PostgreSQL 中的 recent_deployments，用于确认 Incident 时间窗口附近是否存在发布、配置变更或回滚。

query_runbooks_tool:
查询 PostgreSQL 中的 runbooks，用于查找当前服务、组件、问题类型对应的处置手册。

query_historical_incidents_tool:
查询 PostgreSQL 中的 historical_incidents，用于查找当前服务或症状相似的历史故障。
```

当前停止策略：

```text
confidence >= 0.7:
输出 confirmed_diagnosis。

tool_call_count >= max_tool_calls:
输出 needs_human_review。

没有更多 hypothesis:
输出 needs_human_review。
```

当前 API / Worker：

```text
POST /incidents/{incident_id}/diagnose:
手动触发某个 Incident 的 LangGraph 诊断。

GET /incidents/{incident_id}/diagnosis/latest:
查询最新诊断结果。

diagnosis_worker:
消费 Kafka incidents topic，自动运行 LangGraph 诊断并保存 incident_diagnoses。

GET /ops/service-dependencies:
查询服务依赖关系，供运维人员或 Agent tool 验证依赖链。

GET /ops/recent-deployments:
查询近期部署记录，供运维人员或 Agent tool 验证发布变更。

GET /ops/runbooks:
查询 Runbook 知识库。

GET /ops/historical-incidents:
查询历史故障知识库。

GET /ops/tool-calls:
查询 Agent 工具调用审计记录，可按 incident_id、diagnosis_id、tool_name 和时间窗口过滤。

GET /incidents/{incident_id}/tool-calls:
查询某个 Incident 的完整工具调用轨迹。
```

当前实现仍是“规则辅助推理 + 工具查询”的确定性 MVP。代码层面已将推理部分抽象为 `DiagnosisReasoning`，默认实现为 `RuleBasedDiagnosisReasoning`。

当前 Reasoning Provider 职责：

```text
generate_hypotheses:
根据 Incident event_types / aggregate_key 生成候选根因假设。

update_evidence:
根据工具查询结果更新 evidence_chain、confidence、root_cause 和 ruled_out_hypotheses。

generate_recommendations:
根据 root_cause / stop_reason 生成处置建议或人工排查建议。
```

当前 MVP 已实现混合式 `HybridDiagnosisReasoning`，用于增强 L4 LangGraph 诊断推理。默认仍使用 `RuleBasedDiagnosisReasoning`；只有同时开启 `LLM_ENABLED=true` 和 `DIAGNOSIS_LLM_ENABLED=true` 时，L4 诊断才会调用 LangChain ChatModel 进行结构化根因推理。

L4 Hybrid LLM 诊断边界：

```text
1. LLM 不参与 L0-L3 的日志解析、规则计数、告警生成和 Incident 聚合。
2. LangGraph 仍负责诊断流程和工具调用次数上限，LLM 不直接执行工具。
3. LLM 只接收 Incident、候选假设、已有 evidence_chain、工具调用摘要和有限工具结果样本。
4. LLM 必须输出 JSON，字段为 root_cause、confidence、evidence_refs、evidence_chain、needs_human_review、recommendations、ruled_out_hypotheses。
5. 高置信诊断必须包含系统允许的 evidence_refs。
6. 如果 LLM 引用未授权证据，系统会移除引用、降低 confidence，并标记 needs_human_review=true。
7. root_cause 必须来自系统允许的 root_cause key 集合，包含候选假设、当前规则根因和已知根因 key；如果模型输出未知 root_cause，系统会移除该根因、降低 confidence，并标记 needs_human_review=true。
8. 如果 LLM 输出 needs_human_review=true，不覆盖规则诊断的 root_cause、confidence 和 recommendations。
9. 如果 LLM confidence 低于当前规则证据 confidence，不覆盖更强的规则结论。
10. 如果 LLM 配置失败、调用失败或输出格式错误，自动回退到规则诊断，并在 evidence_chain 中记录 fallback 原因。
```

这意味着 L4 已经具备“规则推理 + 受控 LLM 推理”的 Hybrid Agent 能力，但仍保持证据约束和人工兜底，不让模型直接扫描海量日志或凭空确认根因。

当前 MVP 还提供 `scripts.seed_context_data` 脚本，用于写入演示数据：

```text
login-service -> mysql 的服务依赖关系
login-service 在 prod 环境的一条近期部署记录
```

这组数据用于验证 Trigger-based ReAct 诊断链路：Agent 可以先排查 MySQL 事件，再查询服务依赖和近期部署，最终根据证据链输出根因或人工排查报告。

### 11.8 当前 MVP 的 Agent 审计能力

当前 MVP 已增加 `tool_calls` 表，用于保存 Agent 每一次工具调用的可审计轨迹。这样即使诊断结论错误，运维人员也可以复盘 Agent 查了什么、为什么查、查到了多少结果、每次调用花了多久。

审计字段包括：

```text
tool_call_id:
单次工具调用 ID。

incident_id:
关联的 Incident。

diagnosis_id:
关联的诊断报告。

tool_name:
调用的工具，例如 query_events、query_service_dependencies、query_recent_deployments。

reason:
调用工具前要验证的假设和原因。

kwargs:
工具查询参数，时间窗口会序列化为 ISO 字符串。

result_count:
工具返回的记录数量。

result_summary:
工具结果摘要，只保存有限样本，不保存海量原始日志。

started_at / finished_at / duration_ms:
调用开始、结束时间和耗时。
```

保存策略：

```text
persist=False:
只在 DiagnosisReport 内返回 tool_calls，不写数据库。

persist=True:
保存 incident_diagnoses 的同时，将 tool_calls 写入 PostgreSQL。
```

这一步为后续接入 LLM 做准备：LLM Reasoning Node 可以使用这些审计记录解释自己的判断，系统也能对每次推理过程进行回放和质量评估。

### 11.9 当前 MVP 的运维对话会话层

当前 MVP 已增加运维对话的会话与上下文保存能力，并已支持可选的 LangChain Chat LLM 接入。默认 `LLM_ENABLED=false`，未配置模型或模型调用失败时，会自动回退到规则式回复；这样会话、消息、Incident 上下文、诊断报告、工具调用审计和 RAG 上下文都能先稳定串起来。

已实现数据表：

```text
conversation_sessions:
保存一次运维排查会话，包含 user_id、team_id、current_incident_id、title、status、metadata。
当前 MVP 将 team_id 写入 metadata，后续接入正式鉴权和权限系统时可升级为独立索引列。

conversation_messages:
保存每轮用户和 assistant 消息，包含 role、content、incident_id、metadata。

conversation_summaries:
保存滑动窗口之外的历史压缩上下文，包含 known_facts、checked_tools、hypotheses、pending_actions、compressed_context、message_count。
```

已实现 API：

```text
POST /chat/sessions:
创建会话，可绑定 current_incident_id。

GET /chat/sessions:
查询会话列表，可按 user_id、team_id、incident_id、status 过滤。

POST /chat/sessions/{session_id}/messages:
写入用户消息，构建 memory_context 与 rag_context，并优先生成 LangChain LLM 回复；LLM 未启用、配置失败或调用失败时生成规则式 assistant 回复。

GET /chat/sessions/{session_id}/messages:
分页查询会话消息。默认返回最近 50 条，支持 before_created_at 游标向前加载更早消息。

GET /chat/sessions/{session_id}/context:
查询会话上下文，包含 session、summary、最近消息、memory_context、latest_diagnosis、tool_calls、rag_context。
```

当前登录/会话展示设计：

```text
登录系统:
认证用户后得到 user_id、team_id、role。

会话列表:
GET /chat/sessions?user_id=xxx 或 GET /chat/sessions?team_id=xxx。

消息展示:
进入会话后只加载最近 N 条消息，默认 50 条。
用户向上滚动时，用 before_created_at 加载更早消息。

LLM 上下文:
不全量读取历史消息，只使用 conversation_summary、chat_memory_window_size 控制的最近消息窗口、当前 Incident、诊断报告、tool_calls 和 RAG 检索结果。
```

当前回复链路：

```text
用户消息
-> classify_chat_intent 做确定性意图识别
-> LangGraph Chat Router 根据 detected_intent 生成 chat_route
-> 保存 conversation_messages
-> 加载 conversation_summary
-> 加载最近 chat_memory_query_limit 条消息
-> 构建 memory_context
-> 加载 latest_diagnosis / tool_calls
-> 如果 chat_route=investigate_with_tools，运行 LangGraph Chat Investigation，最多调用 5 次工具
   -> 默认使用确定性调查计划
   -> 如果 CHAT_INVESTIGATION_LLM_PLANNER_ENABLED=true，则让 LangChain planner 提议下一步只读工具
   -> 系统对 planner 输出做工具 allowlist、参数白名单、limit 上限和时间窗口裁剪
-> 将本轮 investigation_result 和 investigation tool_calls 合并到回复上下文
-> 构建 rag_context
-> 如果 LLM_ENABLED=true 且模型配置可用，携带 detected_intent、memory_context、rag_context、investigation_result 调用 LangChain ChatModel
-> 如果 LLM 未启用、配置失败、输出格式错误或调用失败，回退到规则式回复；规则回复会优先基于 investigation_result 输出调查结论或人工兜底报告
-> 保存 assistant message，并在 metadata 中记录 intent、detected_intent、chat_route、provider、证据引用、llm_fallback_reason 和 investigation 摘要
-> 重新加载会话消息，压缩滑动窗口之外的历史消息
-> 更新 conversation_summaries.compressed_context / message_count
```

当前 LangGraph Chat Router 映射：

```text
diagnosis_summary -> answer_with_context
tool_call_summary -> answer_with_tool_summary
recommendations -> answer_with_recommendations
incident_report -> generate_incident_report
knowledge_query -> answer_with_rag
investigation_request -> investigate_with_tools
general_question -> answer_with_context
```

当前 Chat Router 只负责路由决策。`investigation_request` 会标记 `requires_tool_investigation=true`，并在 `chat_route` 中返回 `investigate_with_tools`；随后 Chat API 会触发 `LangGraph Chat Investigation` 子图。默认执行确定性 MVP 版工具调查；配置开启后，可由 LangChain planner 提议下一步查询工具。

当前 Chat Investigation 子图：

```text
question + current incident + latest diagnosis
-> initialize
   -> build_investigation_plan
-> tool_step
   -> optional LangChain Planner proposes next read-only tool
   -> SanitizePlannerStep
   -> ExecuteTool
   -> EvaluateEvidence
   -> ShouldStop
-> finish
   -> fallback_report / recommendations
```

已实现能力：

```text
1. 根据用户问题、Incident event_types、affected_services、affected_hosts 生成有限调查计划。
2. 优先验证 MySQL 不可用、应用 DB connection error、登录失败告警、服务依赖、近期部署、runbook 和历史故障。
3. 每次最多执行 max_tool_calls，当前 Chat API 默认 5 次，避免无限循环。
4. 如果证据支持数据库依赖不可用或登录爆破，会输出 root_cause、confidence、evidence_chain 和 recommendations。
5. 如果证据不足或工具调用达到上限，会输出 needs_human_review，并生成 fallback_report。
6. 本轮调查产生的 investigation_result 和 tool_calls 会合并进 LLM / 规则回复上下文，并在 assistant message metadata 中保存 investigation 摘要。
7. 当 LLM 不可用时，规则回复会直接根据 investigation_result 输出 root_cause、confidence、evidence_chain、checked_tools、recommendations 或 fallback_report。
8. 可选 LangChain planner 只负责提议下一步只读工具，系统仍负责工具 allowlist、参数白名单、limit 上限、时间窗口裁剪、执行和停止条件。
9. assistant message metadata 会记录 investigation_planner_provider 和 investigation_planner_fallback_reason，便于区分本轮是 deterministic planner 还是 langchain planner。
```

当前边界：

```text
Chat Investigation 默认是确定性工具计划与规则证据评估。
当 CHAT_INVESTIGATION_LLM_PLANNER_ENABLED=true 且 LLM 配置可用时，LLM 只参与“下一步查什么”的提议，不直接执行工具。
无论 planner 输出什么，系统都会做工具 allowlist、参数白名单、limit 上限、时间窗口裁剪。
planner 输出非法、模型不可用或配置失败时，会自动回退到 deterministic plan。
EvaluateEvidence 仍是系统侧规则评估，避免模型凭空确认根因。
```

当前 LangChain LLM 输出要求：

```json
{
  "intent": "diagnosis_summary",
  "answer": "基于证据的回答",
  "evidence_refs": [
    "diagnosis:diag_xxx",
    "tool:query_events",
    "runbook:runbook-mysql-unavailable"
  ],
  "confidence": 0.78,
  "needs_human_review": false,
  "recommended_actions": ["检查 MySQL 进程状态"]
}
```

其中 `recommended_actions` 对外保持 `list[str]`，用于兼容现有接口。若模型返回更结构化的分阶段动作，例如：

```json
[
  {
    "phase": "立即验证",
    "actions": ["检查 MySQL 进程状态", "检查端口监听"]
  }
]
```

服务层会将其规范化为：

```text
recommended_actions:
- 立即验证: 检查 MySQL 进程状态
- 立即验证: 检查端口监听

action_plan:
保留原始分阶段结构，供后续前端分组展示或报告生成使用。
```

当前已实现的确定性聊天意图：

```text
diagnosis_summary:
解释告警触发、原因、根因。

tool_call_summary:
总结 Agent 查了什么、实际查了哪些东西、调用了哪些工具、这些结果支持或排除了什么假设。

recommendations:
给出下一步处理建议。

incident_report:
生成故障报告或复盘摘要。

knowledge_query:
查询历史故障、runbook、知识库。

investigation_request:
用户要求查询日志、告警、近几分钟情况。

general_question:
普通追问或无法明确归类的问题。
```

基础 guardrail：

```text
confidence 必须在 0-1。
高置信结论必须包含 evidence_refs。
缺少证据引用时自动降低 confidence，并标记 needs_human_review=true。
evidence_refs 只能引用系统提供的 diagnosis/tool_call/tool/runbook/historical_incident 等白名单 ID。
模型返回未授权 evidence_refs 时，系统会移除这些引用，降低 confidence，并标记 needs_human_review=true。
intent 由 classify_chat_intent 的系统识别结果约束；模型返回其他 intent 时会被覆盖为 detected_intent。
recommended_actions 支持字符串列表或分阶段对象列表，服务层统一规范化为 list[str]，并额外保留 action_plan。
LLM 只能基于 diagnosis、tool_calls、rag_context、memory_context、investigation_result 回答。
```

当前规则式兜底回复能力：

```text
用户问“为什么 / 根因 / 触发”:
返回最新诊断报告摘要、root_cause、confidence 和 evidence_chain。

用户问“查了什么 / 调用了什么工具”:
返回 tool_calls 审计摘要。

用户问“下一步 / 建议 / 怎么处理”:
返回诊断报告 recommendations。

其他问题:
如果存在 rag_context，返回可用上下文引用；否则提示当前没有足够上下文。
```

当前 LLM 接入作用于 L5 运维聊天 Agent，并已支持按开关进入 L4 LangGraph 诊断推理。L0-L3 仍完全不使用 LLM，日志解析、规则计数、告警生成和 Incident 聚合都保持确定性链路。L4/L5 复用 evidence_refs / confidence / needs_human_review 约束，避免模型在缺少证据时给出高置信结论。

LLM 环境变量示例：

```text
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_api_key
LLM_BASE_URL=
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1200
LLM_TIMEOUT_SECONDS=30
DIAGNOSIS_LLM_ENABLED=false
CHAT_INVESTIGATION_LLM_PLANNER_ENABLED=false
```

L4 真实模型冒烟测试：

```text
python -m scripts.llm_diagnosis_smoke_test --pretty
```

该脚本会构造一个 login-service 登录失败 + app DB connection error + MySQL connection refused 的跨组件诊断状态，验证模型是否能按 L4 JSON schema 输出结构化 root_cause、confidence、evidence_refs、evidence_chain 和 recommendations。

### 11.10 当前 MVP 的 Runbook 与历史故障检索层

当前 MVP 已增加 Runbook 和历史故障检索层，用于在接入 LLM 之前先准备可控知识来源。当前实现先使用 PostgreSQL 字段过滤和文本匹配，不依赖 pgvector / Milvus；后续可以在不改变工具接口和聊天接口的情况下，将查询逻辑替换为 embedding + pgvector 或 Milvus 相似度检索。

已实现数据表：

```text
runbooks:
保存运维手册，包含 title、service、component、problem_types、content、steps、tags、metadata。

historical_incidents:
保存历史故障摘要，包含 title、service、component、root_cause、summary、resolution、evidence_chain、tags、metadata。
```

已实现工具：

```text
query_runbooks_tool:
按 query、service、component、problem_type、tag 查询 Runbook。

query_historical_incidents_tool:
按 query、service、component、root_cause、tag 查询历史故障。
```

已实现 API：

```text
GET /ops/runbooks
GET /ops/historical-incidents
GET /chat/sessions/{session_id}/rag-context
```

当前聊天 RAG 上下文构建：

```text
conversation summary
+ current incident
+ latest diagnosis
+ tool_calls audit
+ runbooks
+ historical_incidents
-> chat rag_context
```

当前实现新增 `services.rag` 层：

```text
RAGDocument:
统一表示 diagnosis、tool_call、runbook、historical_incident 等可检索文档。

VectorStore:
定义 upsert_documents / search_similar 协议，后续 pgvector 或 Milvus 都实现这个接口。

build_chat_rag_context_payload:
把当前会话和知识库命中结果整理成 LLM 可消费的上下文与 references。
```

聊天接口中的使用方式：

```text
POST /chat/sessions/{session_id}/messages:
保存用户消息后，构建 rag_context，并把可用 references 写入 assistant 回复 metadata。

GET /chat/sessions/{session_id}/context:
返回完整会话上下文，同时包含 rag_context。

GET /chat/sessions/{session_id}/rag-context:
单独查看当前会话可用于 RAG 的上下文，便于后续调试 pgvector / Milvus 检索效果。
```

当前诊断链路中的使用方式：

```text
historical_similar_incident:
查询历史相似故障，但单独命中不会直接确认根因，避免历史相似造成误判。

runbook_available:
查询处置手册，用于增强证据链和后续建议，但单独命中不会直接确认根因。
```

当前 MVP 还提供 `scripts.seed_knowledge_data` 脚本，用于写入演示数据：

```text
runbook-mysql-unavailable:
login-service / mysql 不可用处置手册。

hist-login-mysql-outage:
MySQL outage 导致 login-service 登录异常的历史故障记录。
```

### 11.11 Milvus 在本项目中的定位

Milvus 可以用于聊天 Agent 的 RAG，但不适合放在日志检测主链路里。它应该属于 L5 长期知识与对话记忆检索层，服务对象是低频、高价值、可摘要的文本，而不是 Kafka 中的海量实时日志。

适合写入 Milvus 的内容：

```text
Runbook 分块
历史 Incident 摘要
故障复盘报告
服务架构说明
对话压缩摘要
Agent 诊断报告摘要
```

不建议写入 Milvus 的内容：

```text
raw_logs 全量原始日志
normalized_events 高频事件流
alerts 高频短期计数
Redis 滑动窗口计数
```

推荐数据流：

```text
PostgreSQL:
保存 runbooks、historical_incidents、conversation_summaries、incident_diagnoses 的完整事实数据。

Embedding Worker:
读取 PostgreSQL 中需要入库的文本，切分并生成 embedding。

Milvus:
保存 vector、doc_type、record_id、chunk_id、service、component、tags、updated_at 等检索元数据。

Chat / Agent:
用 question + incident context 生成检索 query，Milvus 返回相似 chunk 的 record_id，再回 PostgreSQL 读取完整记录。
```

MVP 阶段建议先保持 PostgreSQL 文本检索，因为当前数据量小、调试简单。等聊天 Agent 需要跨大量 runbook、历史故障和对话摘要检索时，再接入 Milvus；届时只需要新增 `MilvusVectorStore` 实现，不需要改变聊天接口结构。

## 12. Agent Tool 设计

Agent 可调用的工具应受到权限控制和审计。

初期建议工具：

```text
query_logs:
查询某服务、主机、组件在指定时间窗口内的日志。

query_alerts:
查询相关告警。

query_incident:
查询 Incident 详情。

query_service_dependency:
查询服务依赖关系。

query_recent_deployments:
查询最近发布记录。

query_similar_incidents:
查询历史相似故障。

query_runbook:
查询相关 runbook。

save_diagnosis:
保存 Agent 诊断报告。
```

初期不建议让 Agent 直接执行危险操作，例如：

```text
重启服务
kill 进程
修改配置
删除数据
扩容缩容
```

如果后续需要自动处置，应加入人工确认和严格审计。

## 13. 运维对话 Agent

运维人员可以通过对话查询：

```text
这个告警为什么触发？
当前影响哪些服务？
最近 10 分钟 login-service 有什么异常？
这个问题以前出现过吗？
MySQL 崩溃和用户登录失败有没有关系？
下一步应该查什么？
帮我生成一份故障报告。
```

对话 Agent 需要访问：

```text
当前 Incident
历史告警
日志查询工具
指标查询工具
服务依赖图
部署记录
Runbook
用户上下文
对话历史摘要
```

## 14. 上下文保存与压缩

对话上下文不应只依赖 LLM 当前窗口，需要持久化。

建议保存三类上下文：

```text
1. 会话上下文
   当前用户正在排查哪个 Incident、已经问过什么、查过什么。

2. Incident 上下文
   告警、证据、工具调用结果、根因假设、处理状态。

3. 长期知识上下文
   历史故障、Runbook、服务说明、架构依赖、运维经验。
```

上下文压缩策略：

```text
原始消息 -> 回合摘要 -> 当前状态 -> 可检索 memory
```

展示与推理边界：

```text
PostgreSQL:
保存完整 conversation_messages，不丢历史。

前端:
默认只展示最近 30-50 条消息，滚动时分页加载更早消息。

Chat API:
使用 limit + before_created_at 做游标分页。

LLM:
不读取完整历史消息，只读取压缩摘要、最近若干轮、当前 Incident 上下文和 RAG 检索结果。

Milvus / pgvector:
用于检索长期摘要、历史故障、Runbook 和沉淀的运维经验，不用于保存完整聊天原文。
```

示例：

```json
{
  "conversation_id": "conv_001",
  "current_incident_id": "inc_20260603_001",
  "user_intent": "排查 login-service 登录失败",
  "known_facts": [
    "MySQL connection refused 从 14:03 开始",
    "login-service DB error 从 14:04 开始",
    "用户登录失败数量在 14:04 后升高"
  ],
  "hypotheses": [
    "MySQL 不可用导致登录失败",
    "login-service 发布导致数据库连接异常"
  ],
  "checked_tools": [
    "mysql_logs",
    "nginx_error_logs",
    "deployment_history"
  ],
  "pending_actions": [
    "检查 MySQL 进程状态",
    "确认 13:55 发布是否修改数据库配置"
  ]
}
```

## 15. 数据库设计草案

核心表：

```text
detection_rules
normalized_events
alerts
incidents
incident_alerts
incident_diagnoses
conversation_sessions
conversation_messages
conversation_summaries
tool_calls
runbooks
historical_incidents
service_dependencies
```

说明：

```text
detection_rules:
保存规则类型、阈值、窗口、适用组件、默认等级。

normalized_events:
保存标准化事件元数据。原始大日志可只保存引用。

alerts:
保存告警实例。

incidents:
保存聚合后的故障事件。

incident_alerts:
保存 Incident 与 alerts 的关联。

incident_diagnoses:
保存 Agent 诊断结果。

conversation_sessions:
保存用户会话。

conversation_messages:
保存原始对话消息。

conversation_summaries:
保存压缩后的会话摘要。

tool_calls:
保存 Agent 工具调用记录。

runbooks:
保存运维手册，可接 pgvector。

historical_incidents:
保存历史故障摘要，可接 pgvector。

service_dependencies:
保存服务依赖拓扑。
```

如果日志量较大，原始日志和全量事件不建议长期放 PostgreSQL。可考虑：

```text
OpenSearch / Elasticsearch
ClickHouse
Loki
对象存储
```

PostgreSQL 主要保存结构化元数据、告警、Incident、对话和配置。

## 16. 推荐项目结构

```text
app/
  api/
    alerts.py
    incidents.py
    chat.py
    rules.py

  workers/
    parser_worker.py
    detection_worker.py
    correlation_worker.py
    agent_worker.py

  parsers/
    linux.py
    mysql.py
    docker.py
    nginx.py
    app.py

  rules/
    engine.py
    thresholds.py
    severity.py

  incidents/
    correlator.py
    aggregator.py

  agents/
    graph.py
    nodes.py
    tools.py
    prompts.py
    memory.py

  models/
    event.py
    alert.py
    incident.py
    conversation.py

  storage/
    postgres.py
    redis.py
    kafka.py
    vector.py

  schemas/
    event_schema.py
    alert_schema.py
    incident_schema.py
```

## 17. MVP 路线

### 阶段 1：规则检测系统

目标：

```text
完成日志解析、事件标准化、阈值规则、告警分级。
```

建议先支持：

```text
Linux auth log
MySQL error log
应用登录日志
```

初期检测规则：

```text
SSH 登录失败计数
MySQL connection refused
MySQL too many connections
应用 login failed spike
应用 DB connection error
```

### 阶段 2：Incident 聚合

目标：

```text
把多个告警按时间、服务、主机、依赖关系聚合。
```

初期聚合策略：

```text
5-10 分钟时间窗口
按 service 聚合
按 host 聚合
按 component 聚合
按 service_dependency 聚合
```

### 阶段 3：Kafka 化

目标：

```text
将日志处理链路改造成事件流。
```

Topic：

```text
raw_logs
normalized_events
alerts
incidents
agent_tasks
```

### 阶段 4：LangGraph 诊断 Agent

目标：

```text
只对 high、critical 或跨组件 Incident 触发 Agent。
```

输出：

```text
Incident 摘要
根因假设
证据链
影响范围
下一步建议
```

### 阶段 5：RAG 与历史记忆

目标：

```text
加入 pgvector，支持历史相似故障和 Runbook 检索。
```

检索对象：

```text
历史 Incident 摘要
故障报告
Runbook
组件文档
对话压缩摘要
```

### 阶段 6：运维对话 Agent

目标：

```text
支持用户围绕 Incident 追问、查询日志、查询历史、生成报告。
```

需要实现：

```text
conversation_sessions
conversation_messages
conversation_summaries
conversation_state
```

### 阶段 7：Multi-Agent 化

目标：

```text
当单个 LangGraph 工作流稳定后，再拆分为多个 Agent 或多个子图。
```

候选角色：

```text
Detection Agent / Module:
负责规则检测、阈值判断、事件聚合。

Correlation Agent:
负责跨服务、跨组件、跨时间窗口关联告警。

Diagnosis Agent:
负责根因分析、证据链整理、处置建议。

Tool Agent:
负责调用日志查询、指标查询、服务状态查询、部署查询等工具。

Memory/RAG Agent:
负责检索历史 Incident、Runbook、知识库和对话记忆。

Ops Chat Agent:
面向运维人员，负责对话交互、上下文管理和结果解释。
```

## 18. 关键风险

```text
误报过多:
需要告警聚合、降噪、去重、阈值调优。

LLM 幻觉:
Agent 输出必须基于证据链，不能凭空判断。

日志格式混乱:
需要稳定 parser 和统一 event schema。

上下文过大:
必须先聚合、摘要、采样，再交给 LLM。

权限问题:
Agent 调工具必须做权限控制和审计。

自动处置风险:
初期只提供处置建议，不直接执行重启、kill、改配置等动作。

多 Agent 复杂度:
初期先模块化，不要一开始拆成复杂协作链。
```

## 19. 当前推荐结论

该项目适合采用：

```text
规则检测 + Incident 聚合 + LangGraph Agent 分析 + 运维对话 RAG
```

技术边界为：

```text
FastAPI / Python / Kafka / Redis / PostgreSQL:
负责确定性日志系统和告警主链路。

LangChain / LangGraph:
负责 Incident 之后的智能分析、RAG、工具调用和运维对话。
```

落地上建议优先实现 L0-L3，先让日志到告警的确定性链路跑通；再接入 L4-L5 的 Agent 分析和运维对话能力。

## 20. 当前 MVP 已完成的工程闭环

当前 MVP 已经形成一条可运行、可验证、可审计的最小闭环：

```text
log-ingest-service HTTP/WebSocket ingest
-> Kafka raw_logs
-> parser_worker
-> Kafka normalized_events
-> event_sink_worker
-> detection_worker
-> alerts
-> correlation_worker
-> incidents
-> diagnosis_worker / 手动诊断入口
-> LangGraph 诊断报告
-> Ops API / Chat API 查询与追问
```

### 20.1 运维总览与告警生命周期

已实现运维总览入口：

```text
GET /ops/overview
```

返回最近时间窗口内的核心计数：

```text
events
alerts
incidents
diagnoses
tool_calls
```

并返回告警生命周期摘要，便于运维人员优先处理 open / acknowledged / investigating 等状态的告警。

已实现告警生命周期更新入口：

```text
PATCH /ops/alerts/{alert_id}/lifecycle
```

当前为了保持 MVP 简洁，不新增数据库迁移，生命周期信息先写入：

```text
alerts.fields["_lifecycle"]
```

包含：

```text
status
owner
updated_by
updated_at
note
history
```

后续如果需要更严格的权限、审计查询或状态流转约束，可以再升级为独立 `alert_lifecycle_events` 表。

### 20.2 端到端冒烟与模拟数据评估

已实现端到端 smoke 脚本：

```text
python -m scripts.e2e_smoke --pretty
```

该脚本会：

```text
1. 读取当前 Kafka offset 和 PostgreSQL 计数。
2. 将 datasets/simulated/mixed_incident.jsonl 发送到 log-ingest-service /ingest/logs。
3. 等待 worker 消费。
4. 再次读取 Kafka / PostgreSQL 计数。
5. 输出 raw_logs、normalized_events、alerts、incidents 等链路是否推进。
```

已实现离线模拟数据集评估脚本：

```text
python -m scripts.evaluate_simulated_dataset datasets/simulated/mixed_incident.jsonl --pretty
```

该脚本不依赖 Kafka、Redis、PostgreSQL，直接验证模拟日志能否被 parser 解析出预期事件，并能否理论上触发预期规则告警。它适合用来快速回归 parser / rules 的变化。

已增强 pipeline count 脚本：

```text
python -m scripts.check_pipeline_counts --pretty
```

当前会统计：

```text
Kafka:
- raw_logs
- normalized_events
- alerts
- incidents

PostgreSQL:
- events
- alerts
- incidents
- diagnoses
- tool_calls
```

### 20.3 运维对话会话访问保护

当前 Chat API 已增加轻量级 `user_id/team_id` 访问保护。对于以下 session 详情接口，可以通过 query 参数限制只能读取匹配用户或团队的会话：

```text
GET /chat/sessions/{session_id}/messages
POST /chat/sessions/{session_id}/messages
GET /chat/sessions/{session_id}/context
GET /chat/sessions/{session_id}/rag-context
```

示例：

```text
GET /chat/sessions/{session_id}/messages?user_id=ops-user
GET /chat/sessions/{session_id}/context?team_id=sre-team
```

如果传入的 `user_id` 或 `team_id` 与会话记录不匹配，接口返回 `403`。如果不传这两个参数，则保持 MVP 阶段的兼容行为。

注意：这只是轻量隔离，不等同于正式鉴权。生产化时应接入登录态、JWT / Session、RBAC，并由服务端从认证上下文推导 `user_id/team_id`，而不是完全相信客户端 query 参数。

### 20.4 当前验证命令

当前主要回归命令：

```text
python -m pytest -q
```

重点模块定向验证：

```text
python -m pytest tests/test_chat_routes.py tests/test_ops_routes.py tests/test_alert_lifecycle.py tests/test_e2e_and_dataset_scripts.py -q
```

如果本地服务和 worker 已启动，再运行：

```text
python -m scripts.e2e_smoke --pretty
```

如果只想验证模拟数据质量：

```text
python -m scripts.evaluate_simulated_dataset datasets/simulated/mixed_incident.jsonl --pretty
```

### 20.5 WebSocket 流式日志接入

当前 L0 接入层已经从 Agent 后端拆分为独立服务：

```text
services/log_ingest
```

该服务只负责接收原始日志并写入 Kafka `raw_logs`，不负责日志解析、规则检测、Incident 聚合或 Agent 诊断。Agent 后端不再暴露 `/ingest/logs` 和 `/ws/ingest/logs`。

本地端口：

```text
log-ingest-service: http://localhost:8100
CrossST Agent backend: http://localhost:8888
```

启动方式：

```text
cd services/log_ingest
python -m log_ingest.main
```

当前 log-ingest-service 同时支持 HTTP 批量发送和 WebSocket 持续发送。

HTTP 入口：

```text
POST http://localhost:8100/ingest/logs
```

适合手动测试、一次性发送数据集、脚本批量导入。

WebSocket 入口：

```text
WS ws://localhost:8100/ws/ingest/logs
```

适合模拟真实环境中的多个日志源持续在线，例如 linux-auth、linux-syslog、mysql-error、mysql-slow-query、login-service、payment-service、order-service 分别作为一个客户端连接到 log-ingest-service，每个连接可以持续发送单条日志，也可以每次发送多条日志组成的 batch。

WebSocket 消息格式与 HTTP ingest 保持一致：

```json
{
  "source_type": "linux",
  "source_name": "auth.log",
  "host": "app-prod-01",
  "logs": [
    "Jun  3 14:03:12 app-prod-01 sshd[2311]: Failed password for root from 8.8.8.8 port 52231 ssh2"
  ]
}
```

服务端会把每条日志写入 Kafka `raw_logs`，并返回 ack：

```json
{
  "status": "accepted",
  "topic": "raw_logs",
  "accepted": 1,
  "log_ids": ["..."]
}
```

当前已提供七源持续推送模拟配置，每个来源一个 `.log` 文件：

```text
services/log_ingest/datasets/stream/stream_sources.example.json
services/log_ingest/datasets/stream/linux_auth.log
services/log_ingest/datasets/stream/linux_syslog.log
services/log_ingest/datasets/stream/mysql_error.log
services/log_ingest/datasets/stream/mysql_slow_query.log
services/log_ingest/datasets/stream/app_login_service.log
services/log_ingest/datasets/stream/app_payment_service.log
services/log_ingest/datasets/stream/app_order_service.log
```

当前默认生成规模：

```text
7 个来源
每个来源 200 条
总计 1400 条流式模拟日志
```

如果需要扩大流式数据集：

```text
cd services/log_ingest
python -m scripts.generate_stream_dataset --output-dir datasets/stream --lines-per-source 1000 --pretty
```

运行方式：

```text
cd services/log_ingest
python -m scripts.simulate_log_clients datasets/stream/stream_sources.example.json --duration-seconds 30 --pretty
```

如果希望循环发送，模拟长期在线日志源：

```text
cd services/log_ingest
python -m scripts.simulate_log_clients datasets/stream/stream_sources.example.json --loop --duration-seconds 120 --pretty
```

推荐联动验证流程：

```text
1. docker compose up -d
2. python scripts/run_dev_stack.py --simulate
3. cd backend && python -m scripts.check_pipeline_counts --pretty
```

`run_dev_stack.py` 启动后会等待以下健康检查可用：

```text
http://localhost:8100/health
http://localhost:8888/health
```

如果加上 `--simulate`，脚本会在健康检查通过后自动启动一个 `stream_simulator` 进程，通过 WebSocket 读取七个来源的 `.log` 文件并写入 `raw_logs`。默认模拟 30 秒，日志输出同样写入 `runtime_logs/`。

如果希望模拟源持续循环发送：

```text
python scripts/run_dev_stack.py --simulate --simulation-loop --simulation-duration-seconds 120
```

`run_dev_stack.py` 默认会在启动前检查 `8100` 和 `8888` 是否已经被占用。如果端口上已经有旧的 log-ingest-service 或 backend，脚本会提前失败，避免健康检查误判为本次新进程启动成功。

如果你明确知道端口上已经有兼容服务，并希望只启动其余进程：

```text
python scripts/run_dev_stack.py --no-port-preflight
```

如果只想启动进程，不等待健康检查：

```text
python scripts/run_dev_stack.py --no-health-check
```

如果需要把 diagnosis_worker 也纳入本地一键启动：

```text
python scripts/run_dev_stack.py --with-diagnosis-worker
```

默认不启动 diagnosis_worker，避免开发环境启动时立刻触发 LLM 相关链路。`run_dev_stack.py` 会分别启动：

```text
log_ingest
backend_api
parser_worker
event_sink_worker
detection_worker
correlation_worker
```

每个进程的 stdout/stderr 会写入：

```text
runtime_logs/
```

预期联动效果：

```text
WebSocket client
-> log-ingest-service /ws/ingest/logs
-> Kafka raw_logs
-> parser_worker
-> Kafka normalized_events
-> event_sink_worker 写 PostgreSQL normalized_events
-> detection_worker 使用 Redis 计数并生成 alerts
-> correlation_worker 写 PostgreSQL incidents
```
