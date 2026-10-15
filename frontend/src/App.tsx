import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  CheckCircle2,
  Clock,
  Database,
  GitBranch,
  MessageSquare,
  PlayCircle,
  Radar,
  RefreshCw,
  RotateCcw,
  Send,
  Server,
  Shield,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8888";
const OPS_USER = "ops-user";
const OPS_TEAM = "sre-team";

type AlertLifecycleSummary = {
  total?: number;
  by_status?: Record<string, number>;
  by_lifecycle_status?: Record<string, number>;
  by_severity?: Record<string, number>;
};

type Overview = {
  status: string;
  pipeline_counts: Record<string, number>;
  alert_lifecycle: AlertLifecycleSummary;
  next_actions?: string[];
};

type Incident = {
  incident_id: string;
  title?: string;
  summary: string;
  severity: string;
  status: string;
  aggregate_key?: string;
  alert_count?: number;
  affected_services?: string[];
  affected_hosts?: string[];
  event_types?: string[];
  created_at?: string;
  updated_at?: string;
};

type AlertLifecycle = {
  status?: string;
  owner?: string | null;
  updated_by?: string | null;
  note?: string | null;
  updated_at?: string | null;
  history?: Array<Record<string, unknown>>;
};

type Alert = {
  alert_id: string;
  alert_type: string;
  event_type: string;
  severity: string;
  source_type?: string;
  component?: string;
  host?: string | null;
  service?: string | null;
  message?: string;
  summary?: string;
  count?: number;
  window_seconds?: number;
  fingerprint?: string;
  fields?: Record<string, unknown>;
  tags?: string[];
  lifecycle?: AlertLifecycle;
  created_at?: string;
};

type Diagnosis = {
  diagnosis_id: string;
  incident_id: string;
  status: string;
  stop_reason?: string;
  confidence: number;
  root_cause?: string | null;
  trigger_summary?: string | null;
  evidence_chain?: string[];
  recommendations?: string[];
  tool_call_summary?: Record<string, unknown> | null;
  created_at?: string;
};

type EventRecord = {
  event_id: string;
  raw_log_id?: string;
  source_type: string;
  source_name?: string;
  component: string;
  event_type: string;
  severity_hint: string;
  host?: string | null;
  service?: string | null;
  timestamp?: string;
  message?: string;
  fields?: Record<string, unknown>;
  tags?: string[];
};

type ToolCall = {
  tool_call_id: string;
  incident_id?: string | null;
  diagnosis_id?: string | null;
  tool_name: string;
  reason: string;
  result_count: number;
  result_summary?: string;
  duration_ms: number;
};

type ChatMessage = {
  message_id: string;
  session_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  incident_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

type ChatSession = {
  session_id: string;
  title?: string;
  status?: string;
  current_incident_id?: string | null;
  created_at?: string;
  updated_at?: string;
};

type ChatSendResponse = {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
};

type ChatSessionsResponse = {
  count: number;
  sessions: ChatSession[];
};

type ChatMessagesResponse = {
  session_id: string;
  messages: ChatMessage[];
};

type HealthState = {
  status: "checking" | "online" | "offline";
  detail: string;
  service?: string;
  env?: string;
  checkedAt?: string;
};

type ConsoleData = {
  source: "live" | "demo";
  overview: Overview;
  incidents: Incident[];
  alerts: Alert[];
  diagnoses: Diagnosis[];
  events: EventRecord[];
  toolCalls: ToolCall[];
};

type PageId = "alerts" | "chat";
type PanelKey = "overview" | "incidents" | "alerts" | "diagnoses" | "events" | "tools";
type DetailSelection =
  | { type: "incident"; id: string }
  | { type: "alert"; id: string }
  | { type: "diagnosis"; id: string }
  | { type: "event"; id: string };

const demoData: ConsoleData = {
  source: "demo",
  overview: {
    status: "demo",
    pipeline_counts: {
      events: 12842,
      alerts: 37,
      incidents: 6,
      diagnoses: 4,
      tool_calls: 19,
    },
    alert_lifecycle: {
      total: 37,
      by_status: {
        open: 9,
        investigating: 5,
        acknowledged: 11,
        resolved: 12,
      },
      by_lifecycle_status: {
        open: 9,
        investigating: 5,
        acknowledged: 11,
        resolved: 12,
      },
      by_severity: {
        low: 16,
        medium: 12,
        high: 7,
        critical: 2,
      },
    },
  },
  incidents: [
    {
      incident_id: "inc-login-mysql-001",
      summary: "login-service 故障与 MySQL 连接拒绝同时出现",
      severity: "critical",
      status: "open",
      aggregate_key: "service:login-service",
      alert_count: 2,
      affected_services: ["login-service", "mysql"],
      affected_hosts: ["app-prod-01", "db-prod-01"],
      event_types: ["login_failed", "app_db_connection_error", "mysql_connection_refused"],
      created_at: "2026-06-06T12:24:00Z",
    },
    {
      incident_id: "inc-ssh-attack-044",
      summary: "边缘主机 SSH 登录失败次数超过阈值",
      severity: "high",
      status: "investigating",
      aggregate_key: "host:edge-prod-02",
      alert_count: 1,
      affected_services: ["ssh"],
      affected_hosts: ["edge-prod-02"],
      event_types: ["login_failed"],
      created_at: "2026-06-06T11:52:00Z",
    },
    {
      incident_id: "inc-docker-restart-019",
      summary: "api-worker 容器在部署后反复重启",
      severity: "medium",
      status: "acknowledged",
      aggregate_key: "service:api-worker",
      alert_count: 1,
      affected_services: ["api-worker"],
      affected_hosts: ["app-prod-03"],
      event_types: ["container_restart"],
      created_at: "2026-06-06T10:38:00Z",
    },
  ],
  alerts: [
    {
      alert_id: "alt-001",
      alert_type: "mysql_connection_refused_threshold",
      event_type: "mysql_connection_refused",
      severity: "critical",
      source_type: "mysql",
      component: "mysql",
      host: "db-prod-01",
      service: "mysql",
      count: 48,
      summary: "login-service 依赖的 MySQL 持续拒绝连接",
      message: "无法通过 socket 连接本地 MySQL 服务",
      lifecycle: { status: "open", owner: "sre-db" },
      created_at: "2026-06-06T12:24:00Z",
    },
    {
      alert_id: "alt-002",
      alert_type: "app_db_connection_error_threshold",
      event_type: "app_db_connection_error",
      severity: "high",
      source_type: "app",
      component: "auth",
      host: "app-prod-01",
      service: "login-service",
      count: 83,
      summary: "login-service 上报数据库连接错误",
      message: "用户认证期间数据库依赖不可用",
      lifecycle: { status: "acknowledged", owner: "sre-app" },
      created_at: "2026-06-06T12:23:00Z",
    },
    {
      alert_id: "alt-003",
      alert_type: "ssh_login_failed_threshold",
      event_type: "login_failed",
      severity: "medium",
      source_type: "linux",
      component: "ssh",
      host: "edge-prod-02",
      service: "ssh",
      count: 31,
      summary: "多个重复来源 IP 触发 SSH 登录失败",
      lifecycle: { status: "resolved", owner: "security" },
      created_at: "2026-06-06T12:14:00Z",
    },
  ],
  diagnoses: [
    {
      diagnosis_id: "diag-001",
      incident_id: "inc-login-mysql-001",
      status: "confirmed_diagnosis",
      stop_reason: "confidence_threshold_reached",
      confidence: 0.86,
      root_cause: "database_dependency_unavailable",
      trigger_summary: "MySQL 连接拒绝后 login-service 故障量明显上升",
      evidence_chain: [
        "query_events:mysql_connection_refused 返回 48 条记录",
        "query_events:app_db_connection_error 返回 83 条记录",
        "query_alerts:login_failed 在同一窗口返回 16 条告警",
      ],
      recommendations: [
        "检查 db-prod-01 上的 MySQL 进程、socket 和端口监听。",
        "在数据库连接恢复前保持 login-service 告警未解决。",
        "依赖健康恢复后再回看部署历史。",
      ],
      created_at: "2026-06-06T12:26:00Z",
    },
  ],
  events: [
    {
      event_id: "evt-001",
      source_type: "mysql",
      component: "mysql",
      event_type: "mysql_connection_refused",
      severity_hint: "high",
      host: "db-prod-01",
      service: "mysql",
      timestamp: "2026-06-06T12:23:48Z",
      message: "无法通过 socket 连接本地 MySQL 服务",
    },
    {
      event_id: "evt-002",
      source_type: "app",
      component: "auth",
      event_type: "app_db_connection_error",
      severity_hint: "medium",
      host: "app-prod-01",
      service: "login-service",
      timestamp: "2026-06-06T12:24:03Z",
      message: "用户认证期间数据库依赖不可用",
    },
    {
      event_id: "evt-003",
      source_type: "linux",
      component: "ssh",
      event_type: "login_failed",
      severity_hint: "low",
      host: "edge-prod-02",
      service: "ssh",
      timestamp: "2026-06-06T12:24:17Z",
      message: "来自 8.8.8.8 的 root 密码认证失败",
    },
  ],
  toolCalls: [
    {
      tool_call_id: "tool-001",
      tool_name: "query_events",
      reason: "检查故障窗口附近的 MySQL 可用性错误",
      result_count: 48,
      duration_ms: 31,
    },
    {
      tool_call_id: "tool-002",
      tool_name: "query_service_dependencies",
      reason: "检查 login-service 声明的数据库依赖",
      result_count: 1,
      duration_ms: 18,
    },
    {
      tool_call_id: "tool-003",
      tool_name: "query_runbooks",
      reason: "查找 MySQL 不可用处理手册",
      result_count: 1,
      duration_ms: 24,
    },
  ],
};

const pageItems: Array<{ label: string; page: PageId; path: string; icon: LucideIcon }> = [
  { label: "对话页面", page: "chat", path: "/chat", icon: MessageSquare },
  { label: "告警页面", page: "alerts", path: "/alerts", icon: AlertTriangle },
];

const pageMeta: Record<PageId, { eyebrow: string; title: string; description: string }> = {
  alerts: {
    eyebrow: "告警处理",
    title: "告警页面",
    description: "查看告警态势、处置生命周期、关联故障和智能诊断结果。",
  },
  chat: {
    eyebrow: "运维助手",
    title: "对话页面",
    description: "基于当前故障或诊断上下文进行运维问答。",
  },
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    let detail = `${path} returned ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep the HTTP status message when the body is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function getJson<T>(path: string): Promise<T> {
  return requestJson<T>(path);
}

function postJson<T>(path: string, payload?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
}

function patchJson<T>(path: string, payload: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function checkApiHealth(): Promise<HealthState> {
  const payload = await getJson<{ status: string; service?: string; env?: string }>("/health");
  return {
    status: payload.status === "ok" ? "online" : "offline",
    detail: payload.status === "ok" ? "FastAPI 健康检查正常" : "FastAPI 状态异常",
    service: payload.service,
    env: payload.env,
    checkedAt: new Date().toISOString(),
  };
}

async function loadConsoleData(): Promise<ConsoleData> {
  const [overview, incidents, alerts, diagnoses, events, toolCalls] = await Promise.all([
    getJson<Overview>("/ops/overview?minutes=1440"),
    getJson<{ incidents: Incident[] }>("/ops/incidents?limit=12"),
    getJson<{ alerts: Alert[] }>("/ops/alerts?limit=12"),
    getJson<{ diagnoses: Diagnosis[] }>("/ops/diagnoses?limit=8"),
    getJson<{ events: EventRecord[] }>("/ops/events?limit=20"),
    getJson<{ tool_calls: ToolCall[] }>("/ops/tool-calls?limit=12"),
  ]);

  return {
    source: "live",
    overview,
    incidents: incidents.incidents ?? [],
    alerts: alerts.alerts ?? [],
    diagnoses: diagnoses.diagnoses ?? [],
    events: events.events ?? [],
    toolCalls: toolCalls.tool_calls ?? [],
  };
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat("zh-CN").format(value ?? 0);
}

function formatDate(value?: string | null) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function severityClass(severity?: string) {
  const key = (severity ?? "low").toLowerCase();
  if (key === "critical") return "severity critical";
  if (key === "high") return "severity high";
  if (key === "medium") return "severity medium";
  return "severity low";
}

function lifecycleClass(status?: string) {
  const key = (status ?? "open").toLowerCase();
  if (key === "resolved") return "lifecycle resolved";
  if (key === "acknowledged") return "lifecycle acknowledged";
  if (key === "silenced" || key === "false_positive") return "lifecycle muted";
  return "lifecycle open";
}

function confidenceLabel(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function confidencePercent(value?: number) {
  return Math.max(0, Math.min(100, Math.round((value ?? 0) * 100)));
}

function displaySeverity(severity?: string) {
  const labels: Record<string, string> = {
    critical: "严重",
    high: "高",
    medium: "中",
    low: "低",
  };
  const key = (severity ?? "low").toLowerCase();
  return labels[key] ?? severity ?? "未知";
}

function displayLifecycleStatus(status?: string | null) {
  const labels: Record<string, string> = {
    open: "未处理",
    investigating: "调查中",
    acknowledged: "已确认",
    resolved: "已解决",
    silenced: "已静默",
    false_positive: "误报",
  };
  const key = (status ?? "open").toLowerCase();
  return labels[key] ?? status ?? "未知";
}

function displayDiagnosisStatus(status?: string | null) {
  const labels: Record<string, string> = {
    completed: "已完成",
    confirmed_diagnosis: "诊断已确认",
    needs_human_review: "需要人工复核",
    running: "运行中",
    failed: "失败",
  };
  const key = (status ?? "").toLowerCase();
  return labels[key] ?? status ?? "未知";
}

function displayRootCause(rootCause?: string | null) {
  const labels: Record<string, string> = {
    database_dependency_unavailable: "数据库依赖不可用",
    mysql_connection_refused: "MySQL 连接被拒绝",
    service_dependency_failure: "服务依赖故障",
    repeated_login_failure: "重复登录失败",
    container_restart_loop: "容器重启循环",
    needs_human_review: "需要人工复核",
  };
  const key = (rootCause ?? "").toLowerCase();
  return labels[key] ?? rootCause ?? "需要人工复核";
}

function displayStopReason(reason?: string | null) {
  const labels: Record<string, string> = {
    confidence_threshold_reached: "达到置信度阈值",
    max_steps_reached: "达到最大步骤数",
    no_relevant_evidence: "缺少相关证据",
    tool_error: "工具调用异常",
    user_requested_stop: "用户停止",
  };
  const key = (reason ?? "").toLowerCase();
  return labels[key] ?? reason ?? "未知";
}

function displayHealthStatus(status: HealthState["status"]) {
  if (status === "online") return "在线";
  if (status === "offline") return "离线";
  return "检查中";
}

function displayPipelineHealth(status: string) {
  const labels: Record<string, string> = {
    diagnosing: "诊断中",
    watching: "监控中",
    quiet: "平稳",
  };
  return labels[status] ?? status;
}

function displayErrorMessage(message?: string | null) {
  const text = message?.trim();
  if (!text) return "未知错误";
  const labels: Record<string, string> = {
    "Failed to fetch": "后端请求失败：无法连接 API",
    "NetworkError when attempting to fetch resource.": "后端请求失败：无法连接 API",
    "Load failed": "后端请求失败：无法连接 API",
    "API unavailable": "API 不可用",
    "Panel refresh failed": "面板刷新失败",
    "Alert update failed": "告警更新失败",
    "Diagnosis request failed": "诊断请求失败",
    "Alert diagnosis request failed": "告警诊断请求失败",
    "Chat message failed": "聊天消息发送失败",
  };
  if (labels[text]) return labels[text];

  const returnedMatch = text.match(/^(.+) returned (\d+)$/);
  if (returnedMatch) {
    return `接口 ${returnedMatch[1]} 返回 HTTP ${returnedMatch[2]}`;
  }

  return /[\u4e00-\u9fff]/.test(text) ? text : `后端返回错误：${text}`;
}

function lifecycleCounts(overview: Overview) {
  return (
    overview.alert_lifecycle.by_status ??
    overview.alert_lifecycle.by_lifecycle_status ??
    {}
  );
}

function isHighRisk(alert: Alert) {
  return ["critical", "high"].includes((alert.severity ?? "").toLowerCase());
}

function normalizeDiagnosis(payload: Partial<Diagnosis> & Record<string, unknown>): Diagnosis {
  return {
    diagnosis_id: String(payload.diagnosis_id ?? `diagnosis-${Date.now()}`),
    incident_id: String(payload.incident_id ?? ""),
    status: String(payload.status ?? "completed"),
    stop_reason: payload.stop_reason ? String(payload.stop_reason) : undefined,
    confidence: Number(payload.confidence ?? 0),
    root_cause:
      payload.root_cause === undefined || payload.root_cause === null
        ? null
        : String(payload.root_cause),
    trigger_summary:
      payload.trigger_summary === undefined || payload.trigger_summary === null
        ? null
        : String(payload.trigger_summary),
    evidence_chain: Array.isArray(payload.evidence_chain)
      ? payload.evidence_chain.map(String)
      : [],
    recommendations: Array.isArray(payload.recommendations)
      ? payload.recommendations.map(String)
      : [],
    tool_call_summary:
      payload.tool_call_summary && typeof payload.tool_call_summary === "object"
        ? (payload.tool_call_summary as Record<string, unknown>)
        : null,
    created_at:
      typeof payload.created_at === "string" ? payload.created_at : new Date().toISOString(),
  };
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <section className="metric-card">
      <div className="metric-icon">
        <Icon size={18} />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </section>
  );
}

function RefreshButton({
  busy,
  onClick,
  label = "刷新",
}: {
  busy?: boolean;
  onClick: () => void;
  label?: string;
}) {
  return (
    <button className="icon-button" disabled={busy} onClick={onClick} title={label} type="button">
      <RefreshCw className={busy ? "spin" : ""} size={14} />
      <span>{label}</span>
    </button>
  );
}

function Panel({
  title,
  icon: Icon,
  action,
  children,
  sectionId,
  panelRef,
}: {
  title: string;
  icon: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  sectionId?: string;
  panelRef?: (node: HTMLElement | null) => void;
}) {
  return (
    <section className="panel" id={sectionId} ref={panelRef}>
      <header className="panel-header">
        <div>
          <Icon size={16} />
          <h2>{title}</h2>
        </div>
        {action ? <div className="panel-actions">{action}</div> : null}
      </header>
      {children}
    </section>
  );
}

function TagList({ items }: { items?: Array<string | undefined | null> }) {
  const visible = (items ?? []).filter(Boolean).slice(0, 5) as string[];
  if (!visible.length) return <span className="muted-text">无</span>;
  return (
    <div className="tag-row">
      {visible.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </div>
  );
}

function DetailField({
  label,
  value,
}: {
  label: string;
  value?: string | number | null;
}) {
  return (
    <div className="detail-field">
      <span>{label}</span>
      <strong>{value === undefined || value === null || value === "" ? "未知" : value}</strong>
    </div>
  );
}

function JsonBlock({ value }: { value?: unknown }) {
  if (value === undefined || value === null) return null;
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function pageFromPath(pathname: string): PageId {
  return pathname === "/alerts" ? "alerts" : "chat";
}

function pagePath(page: PageId) {
  return page === "alerts" ? "/alerts" : "/chat";
}

function createWelcomeMessage(): ChatMessage {
  return {
    message_id: `local-welcome-${Date.now()}`,
    role: "assistant",
    content: "新建会话后可以直接输入运维问题，也可以先到告警页面选择故障或告警作为上下文。",
    created_at: new Date().toISOString(),
  };
}

function App() {
  const [data, setData] = useState<ConsoleData>(demoData);
  const [health, setHealth] = useState<HealthState>({
    status: "checking",
    detail: "正在检查 FastAPI 健康状态",
  });
  const [loading, setLoading] = useState(true);
  const [panelLoading, setPanelLoading] = useState<Partial<Record<PanelKey, boolean>>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<PageId>(() => pageFromPath(window.location.pathname));
  const [detailSelection, setDetailSelection] = useState<DetailSelection | null>(null);
  const [selectedDiagnosisId, setSelectedDiagnosisId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [sendingSessionIds, setSendingSessionIds] = useState<string[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatTitleDraft, setChatTitleDraft] = useState("");
  const [chatTitleSaving, setChatTitleSaving] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => [createWelcomeMessage()]);
  const activeChatSessionRef = useRef<string | null>(null);
  const [alertBusy, setAlertBusy] = useState<Record<string, string>>({});
  const [diagnosisBusy, setDiagnosisBusy] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const canMutateLive = data.source === "live" && health.status === "online";
  const canChat = health.status === "online";
  const statusCounts = lifecycleCounts(data.overview);
  const criticalCount = data.overview.alert_lifecycle.by_severity?.critical ?? 0;
  const highCount = data.overview.alert_lifecycle.by_severity?.high ?? 0;
  const openCount = statusCounts.open ?? 0;

  const selectedIncident = useMemo(() => {
    if (detailSelection?.type === "incident") {
      return data.incidents.find((incident) => incident.incident_id === detailSelection.id);
    }
    return data.incidents[0];
  }, [data.incidents, detailSelection]);

  const selectedAlert = useMemo(() => {
    if (detailSelection?.type === "alert") {
      return data.alerts.find((alert) => alert.alert_id === detailSelection.id);
    }
    return data.alerts[0];
  }, [data.alerts, detailSelection]);

  const activeDiagnosis = useMemo(() => {
    const selected = selectedDiagnosisId
      ? data.diagnoses.find((diagnosis) => diagnosis.diagnosis_id === selectedDiagnosisId)
      : undefined;
    return selected ?? data.diagnoses[0] ?? demoData.diagnoses[0];
  }, [data.diagnoses, selectedDiagnosisId]);

  const activeChatSession = useMemo(
    () => chatSessions.find((session) => session.session_id === chatSessionId),
    [chatSessionId, chatSessions],
  );
  const currentSessionSending = Boolean(
    chatSessionId && sendingSessionIds.includes(chatSessionId),
  );

  const chatIncident = useMemo(() => {
    if (detailSelection?.type === "incident") {
      return selectedIncident;
    }
    if (detailSelection?.type === "diagnosis") {
      return data.incidents.find(
        (incident) => incident.incident_id === activeDiagnosis.incident_id,
      );
    }
    return null;
  }, [activeDiagnosis.incident_id, data.incidents, detailSelection, selectedIncident]);

  const selectedEvent = useMemo(() => {
    if (detailSelection?.type === "event") {
      return data.events.find((event) => event.event_id === detailSelection.id);
    }
    return data.events[0];
  }, [data.events, detailSelection]);

  const pipelineHealth = useMemo(() => {
    const counts = data.overview.pipeline_counts;
    if ((counts.incidents ?? 0) > 0 && (counts.diagnoses ?? 0) > 0) return "diagnosing";
    if ((counts.alerts ?? 0) > 0) return "watching";
    return "quiet";
  }, [data.overview.pipeline_counts]);

  function navigateToPage(page: PageId) {
    const nextPath = pagePath(page);
    if (window.location.pathname !== nextPath) {
      window.history.pushState({ page }, "", nextPath);
    }
    setActivePage(page);
  }

  function selectChatSession(sessionId: string | null) {
    activeChatSessionRef.current = sessionId;
    setChatSessionId(sessionId);
  }

  async function refresh() {
    setLoading(true);
    setNotice(null);
    const [dataResult, healthResult] = await Promise.allSettled([
      loadConsoleData(),
      checkApiHealth(),
    ]);

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      setHealth({
        status: "offline",
        detail:
          healthResult.reason instanceof Error
            ? displayErrorMessage(healthResult.reason.message)
            : "FastAPI 健康检查失败",
        checkedAt: new Date().toISOString(),
      });
    }

    if (dataResult.status === "fulfilled") {
      setData(dataResult.value);
      setError(null);
      setLastUpdated(new Date().toISOString());
    } else {
      setData(demoData);
      setError(
        dataResult.reason instanceof Error
          ? displayErrorMessage(dataResult.reason.message)
          : "API 不可用",
      );
    }
    setLoading(false);
  }

  async function refreshPanel(panel: PanelKey) {
    setPanelLoading((current) => ({ ...current, [panel]: true }));
    setNotice(null);
    try {
      if (panel === "overview") {
        const overview = await getJson<Overview>("/ops/overview?minutes=1440");
        setData((current) => ({ ...current, source: "live", overview }));
      }
      if (panel === "incidents") {
        const payload = await getJson<{ incidents: Incident[] }>("/ops/incidents?limit=12");
        setData((current) => ({ ...current, source: "live", incidents: payload.incidents ?? [] }));
      }
      if (panel === "alerts") {
        const payload = await getJson<{ alerts: Alert[] }>("/ops/alerts?limit=12");
        setData((current) => ({ ...current, source: "live", alerts: payload.alerts ?? [] }));
        void refreshPanel("overview");
      }
      if (panel === "diagnoses") {
        const payload = await getJson<{ diagnoses: Diagnosis[] }>("/ops/diagnoses?limit=8");
        setData((current) => ({
          ...current,
          source: "live",
          diagnoses: payload.diagnoses ?? [],
        }));
      }
      if (panel === "events") {
        const payload = await getJson<{ events: EventRecord[] }>("/ops/events?limit=20");
        setData((current) => ({ ...current, source: "live", events: payload.events ?? [] }));
      }
      if (panel === "tools") {
        const payload = await getJson<{ tool_calls: ToolCall[] }>("/ops/tool-calls?limit=12");
        setData((current) => ({
          ...current,
          source: "live",
          toolCalls: payload.tool_calls ?? [],
        }));
      }
      setHealth((current) => ({
        ...current,
        status: "online",
        detail: "FastAPI 请求完成",
        checkedAt: new Date().toISOString(),
      }));
      setError(null);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      const message =
        err instanceof Error ? displayErrorMessage(err.message) : "面板刷新失败";
      setError(message);
      setNotice(message);
    } finally {
      setPanelLoading((current) => ({ ...current, [panel]: false }));
    }
  }

  async function updateAlertLifecycle(alert: Alert, status: "open" | "acknowledged" | "resolved") {
    setAlertBusy((current) => ({ ...current, [alert.alert_id]: status }));
    setNotice(null);
    try {
      const updated = await patchJson<Alert>(`/ops/alerts/${alert.alert_id}/lifecycle`, {
        status,
        owner: alert.lifecycle?.owner ?? OPS_TEAM,
        updated_by: OPS_USER,
        note:
          status === "open"
            ? "从运维控制台重开"
            : status === "acknowledged"
              ? "从运维控制台确认"
              : "从运维控制台解决",
      });
      setData((current) => ({
        ...current,
        source: "live",
        alerts: current.alerts.map((item) =>
          item.alert_id === updated.alert_id ? updated : item,
        ),
      }));
      setDetailSelection({ type: "alert", id: updated.alert_id });
      await refreshPanel("overview");
      setNotice(
        `告警 ${updated.alert_id} 已更新为 ${displayLifecycleStatus(
          updated.lifecycle?.status ?? status,
        )}。`,
      );
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "告警更新失败");
    } finally {
      setAlertBusy((current) => {
        const next = { ...current };
        delete next[alert.alert_id];
        return next;
      });
    }
  }

  function mergeDiagnosis(diagnosis: Diagnosis) {
    setData((current) => {
      const withoutDuplicate = current.diagnoses.filter(
        (item) => item.diagnosis_id !== diagnosis.diagnosis_id,
      );
      return {
        ...current,
        source: "live",
        diagnoses: [diagnosis, ...withoutDuplicate].slice(0, 8),
      };
    });
    setSelectedDiagnosisId(diagnosis.diagnosis_id);
    setDetailSelection({ type: "diagnosis", id: diagnosis.diagnosis_id });
  }

  async function runDiagnosisForIncident(incidentId: string) {
    setDiagnosisBusy(`incident:${incidentId}`);
    setNotice(null);
    try {
      const payload = await postJson<Record<string, unknown>>(`/incidents/${incidentId}/diagnose`);
      const diagnosis = normalizeDiagnosis({ ...payload, incident_id: incidentId });
      mergeDiagnosis(diagnosis);
      await refreshPanel("tools");
      setNotice(`诊断 ${diagnosis.diagnosis_id} 已完成，关联故障 ${incidentId}。`);
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "诊断请求失败");
    } finally {
      setDiagnosisBusy(null);
    }
  }

  async function runDiagnosisForAlert(alertId: string) {
    setDiagnosisBusy(`alert:${alertId}`);
    setNotice(null);
    try {
      const payload = await postJson<Record<string, unknown>>(`/ops/alerts/${alertId}/diagnose`);
      const diagnosis = normalizeDiagnosis(payload);
      mergeDiagnosis(diagnosis);
      await refreshPanel("tools");
      setNotice(`诊断 ${diagnosis.diagnosis_id} 已完成，来源告警 ${alertId}。`);
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "告警诊断请求失败");
    } finally {
      setDiagnosisBusy(null);
    }
  }

  async function loadChatSessions(selectFirst = false) {
    if (!canChat) return;
    setChatLoading(true);
    try {
      const payload = await getJson<ChatSessionsResponse>(
        `/chat/sessions?user_id=${OPS_USER}&team_id=${OPS_TEAM}&limit=20`,
      );
      const sessions = payload.sessions ?? [];
      setChatSessions(sessions);
      if (selectFirst && !chatSessionId && sessions[0]) {
        await loadChatMessages(sessions[0].session_id);
      }
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "会话列表加载失败");
    } finally {
      setChatLoading(false);
    }
  }

  async function loadChatMessages(sessionId: string) {
    selectChatSession(sessionId);
    setChatLoading(true);
    setNotice(null);
    try {
      const payload = await getJson<ChatMessagesResponse>(
        `/chat/sessions/${sessionId}/messages?user_id=${OPS_USER}&team_id=${OPS_TEAM}&limit=80&newest_first=false`,
      );
      if (activeChatSessionRef.current !== sessionId) return;
      const session = chatSessions.find((item) => item.session_id === sessionId);
      setChatTitleDraft(session?.title ?? "");
      setChatMessages(
        payload.messages.length ? payload.messages : [createWelcomeMessage()],
      );
    } catch (err) {
      if (activeChatSessionRef.current === sessionId) {
        setChatMessages([createWelcomeMessage()]);
        setNotice(err instanceof Error ? displayErrorMessage(err.message) : "会话消息加载失败");
      }
    } finally {
      if (activeChatSessionRef.current === sessionId) {
        setChatLoading(false);
      }
    }
  }

  async function createChatSession() {
    if (!canChat || chatLoading) return null;
    setChatLoading(true);
    setNotice(null);
    try {
      const session = await postJson<ChatSession>("/chat/sessions", {
        user_id: OPS_USER,
        team_id: OPS_TEAM,
        current_incident_id: chatIncident?.incident_id ?? null,
        title: chatIncident
          ? `运维问答：${chatIncident.incident_id}`
          : `运维问答 ${formatDate(new Date().toISOString())}`,
        metadata: {
          client: "ops-console",
        },
      });
      selectChatSession(session.session_id);
      setChatTitleDraft(session.title ?? "");
      setChatMessages([createWelcomeMessage()]);
      setChatSessions((current) => [
        session,
        ...current.filter((item) => item.session_id !== session.session_id),
      ]);
      return session.session_id;
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "会话创建失败");
      return null;
    } finally {
      setChatLoading(false);
    }
  }

  async function ensureChatSession() {
    if (chatSessionId) return chatSessionId;
    const sessionId = await createChatSession();
    if (!sessionId) throw new Error("无法创建会话");
    return sessionId;
  }

  async function saveChatSessionTitle() {
    const title = chatTitleDraft.trim();
    if (!chatSessionId || !title || chatTitleSaving) return;

    setChatTitleSaving(true);
    setNotice(null);
    try {
      const updated = await patchJson<ChatSession>(
        `/chat/sessions/${chatSessionId}?user_id=${OPS_USER}&team_id=${OPS_TEAM}`,
        { title },
      );
      setChatSessions((current) =>
        current.map((session) =>
          session.session_id === updated.session_id ? updated : session,
        ),
      );
      setChatTitleDraft(updated.title ?? title);
      setNotice("会话名称已保存。");
    } catch (err) {
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "会话名称保存失败");
    } finally {
      setChatTitleSaving(false);
    }
  }

  async function sendChatMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = chatInput.trim();
    if (!content || currentSessionSending || !canChat) return;
    let pendingSessionId: string | null = null;
    let pendingMessageId: string | null = null;

    try {
      const sessionId = await ensureChatSession();
      pendingSessionId = sessionId;
      pendingMessageId = `local-${Date.now()}`;
      const tempMessage: ChatMessage = {
        message_id: pendingMessageId,
        session_id: sessionId,
        role: "user",
        content,
        incident_id: chatIncident?.incident_id ?? null,
        created_at: new Date().toISOString(),
      };

      setChatMessages((current) => [...current, tempMessage]);
      setChatInput("");
      setSendingSessionIds((current) =>
        current.includes(sessionId) ? current : [...current, sessionId],
      );
      setNotice(null);

      const response = await postJson<ChatSendResponse>(
        `/chat/sessions/${sessionId}/messages?user_id=${OPS_USER}&team_id=${OPS_TEAM}`,
        {
          role: "user",
          content,
          incident_id: chatIncident?.incident_id ?? null,
          metadata: {
            client: "ops-console",
            selected_detail_type: detailSelection?.type ?? null,
          },
        },
      );
      if (activeChatSessionRef.current === sessionId) {
        setChatMessages((current) => [
          ...current.filter((message) => message.message_id !== tempMessage.message_id),
          response.user_message,
          response.assistant_message,
        ]);
        selectChatSession(response.session_id);
      }
    } catch (err) {
      if (pendingSessionId && pendingMessageId && activeChatSessionRef.current === pendingSessionId) {
        setChatMessages((current) =>
          current.filter((message) => message.message_id !== pendingMessageId),
        );
      }
      setNotice(err instanceof Error ? displayErrorMessage(err.message) : "聊天消息发送失败");
    } finally {
      if (pendingSessionId) {
        setSendingSessionIds((current) =>
          current.filter((sessionId) => sessionId !== pendingSessionId),
        );
      }
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (window.location.pathname !== "/alerts" && window.location.pathname !== "/chat") {
      window.history.replaceState({ page: "chat" }, "", "/chat");
    }

    function handlePopState() {
      setActivePage(pageFromPath(window.location.pathname));
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!detailSelection && data.incidents[0]) {
      setDetailSelection({ type: "incident", id: data.incidents[0].incident_id });
    }
  }, [data.incidents, detailSelection]);

  useEffect(() => {
    if (!selectedDiagnosisId && data.diagnoses[0]) {
      setSelectedDiagnosisId(data.diagnoses[0].diagnosis_id);
    }
  }, [data.diagnoses, selectedDiagnosisId]);

  useEffect(() => {
    if (activePage === "alerts" && data.alerts[0]) {
      setDetailSelection((current) =>
        current?.type === "alert" ? current : { type: "alert", id: data.alerts[0].alert_id },
      );
    }
    if (activePage === "chat" && activeDiagnosis) {
      setDetailSelection((current) =>
        current?.type === "incident" || current?.type === "diagnosis"
          ? current
          : { type: "diagnosis", id: activeDiagnosis.diagnosis_id },
      );
    }
  }, [activeDiagnosis, activePage, data.alerts]);

  useEffect(() => {
    if (activePage === "chat" && canChat) {
      void loadChatSessions(true);
    }
  }, [activePage, canChat]);

  useEffect(() => {
    setChatTitleDraft(activeChatSession?.title ?? "");
  }, [activeChatSession?.title]);

  function renderMetrics() {
    return (
      <section className="metrics-grid">
        <MetricCard
          icon={Activity}
          label="事件"
          value={formatNumber(data.overview.pipeline_counts.events)}
          detail="标准化日志流"
        />
        <MetricCard
          icon={Shield}
          label="告警"
          value={formatNumber(data.overview.pipeline_counts.alerts)}
          detail={`${openCount} 个未处理`}
        />
        <MetricCard
          icon={GitBranch}
          label="故障"
          value={formatNumber(data.overview.pipeline_counts.incidents)}
          detail={`${criticalCount + highCount} 个高影响`}
        />
        <MetricCard
          icon={Bot}
          label="诊断运行"
          value={formatNumber(data.overview.pipeline_counts.diagnoses)}
          detail={`${formatNumber(data.overview.pipeline_counts.tool_calls)} 次工具调用`}
        />
      </section>
    );
  }

  function renderIncidentPanel(limit = 8) {
    return (
      <Panel
        title="故障时间线"
        icon={Radar}
        action={
          <>
            <span>最近 24 小时</span>
            <RefreshButton
              busy={panelLoading.incidents}
              onClick={() => void refreshPanel("incidents")}
            />
          </>
        }
      >
        <div className="incident-list">
          {data.incidents.slice(0, limit).map((incident) => (
            <button
              className={`incident-row list-action ${
                detailSelection?.type === "incident" &&
                detailSelection.id === incident.incident_id
                  ? "selected"
                  : ""
              }`}
              key={incident.incident_id}
              onClick={() => setDetailSelection({ type: "incident", id: incident.incident_id })}
              type="button"
            >
              <div className="timeline-node" />
              <div>
                <div className="row-head">
                  <strong>{incident.summary}</strong>
                  <span className={severityClass(incident.severity)}>
                    {displaySeverity(incident.severity)}
                  </span>
                </div>
                <p>{incident.incident_id}</p>
                <TagList
                  items={[
                    ...(incident.affected_services ?? []),
                    ...(incident.event_types ?? []),
                  ]}
                />
              </div>
            </button>
          ))}
        </div>
      </Panel>
    );
  }

  function renderDiagnosisPanel() {
    return (
      <Panel
        title="智能诊断"
        icon={Brain}
        action={
          <>
            <span>{displayDiagnosisStatus(activeDiagnosis.status)}</span>
            <RefreshButton
              busy={panelLoading.diagnoses}
              onClick={() => void refreshPanel("diagnoses")}
            />
            {selectedIncident && canMutateLive ? (
              <button
                className="icon-button primary"
                disabled={diagnosisBusy === `incident:${selectedIncident.incident_id}`}
                onClick={() => void runDiagnosisForIncident(selectedIncident.incident_id)}
                type="button"
              >
                <PlayCircle size={14} />
                <span>运行</span>
              </button>
            ) : null}
          </>
        }
      >
        <div className="diagnosis-card">
          <div
            className="confidence-ring"
            style={{
              background: `radial-gradient(circle at center, rgba(141, 255, 122, 0.08), transparent 60%), conic-gradient(var(--green) 0 ${confidencePercent(
                activeDiagnosis.confidence,
              )}%, rgba(141, 255, 122, 0.1) ${confidencePercent(
                activeDiagnosis.confidence,
              )}% 100%)`,
            }}
          >
            <strong>{confidenceLabel(activeDiagnosis.confidence)}</strong>
            <span>置信度</span>
          </div>
          <div className="diagnosis-body">
            <p className="eyebrow">根因</p>
            <h3>{displayRootCause(activeDiagnosis.root_cause)}</h3>
            <p>{activeDiagnosis.trigger_summary}</p>
            <div className="evidence-grid">
              {(activeDiagnosis.evidence_chain ?? []).slice(0, 3).map((item) => (
                <button
                  className="evidence list-action"
                  key={item}
                  onClick={() => {
                    setSelectedDiagnosisId(activeDiagnosis.diagnosis_id);
                    setDetailSelection({
                      type: "diagnosis",
                      id: activeDiagnosis.diagnosis_id,
                    });
                  }}
                  type="button"
                >
                  <CheckCircle2 size={14} />
                  <span>{item}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="diagnosis-list">
          {data.diagnoses.slice(0, 8).map((diagnosis) => (
            <button
              className={`diagnosis-row list-action ${
                activeDiagnosis.diagnosis_id === diagnosis.diagnosis_id ? "selected" : ""
              }`}
              key={diagnosis.diagnosis_id}
              onClick={() => {
                setSelectedDiagnosisId(diagnosis.diagnosis_id);
                setDetailSelection({ type: "diagnosis", id: diagnosis.diagnosis_id });
              }}
              type="button"
            >
              <strong>
                {diagnosis.root_cause
                  ? displayRootCause(diagnosis.root_cause)
                  : displayDiagnosisStatus(diagnosis.status)}
              </strong>
              <span>{diagnosis.incident_id}</span>
              <em>{confidenceLabel(diagnosis.confidence)}</em>
            </button>
          ))}
        </div>
      </Panel>
    );
  }

  function renderLifecyclePanel() {
    return (
      <Panel
        title="告警生命周期"
        icon={AlertTriangle}
        action={
          <RefreshButton
            busy={panelLoading.overview}
            onClick={() => void refreshPanel("overview")}
          />
        }
      >
        <div className="lifecycle-list">
          {Object.entries(statusCounts).map(([status, count]) => (
            <div key={status}>
              <span>{displayLifecycleStatus(status)}</span>
              <strong>{count}</strong>
              <meter value={count} max={data.overview.alert_lifecycle.total ?? 1} />
            </div>
          ))}
        </div>
      </Panel>
    );
  }

  function renderAlertsPanel(limit = 12) {
    return (
      <Panel
        title="活跃告警"
        icon={Shield}
        action={
          <RefreshButton
            busy={panelLoading.alerts}
            onClick={() => void refreshPanel("alerts")}
          />
        }
      >
        <div className="compact-list">
          {data.alerts.slice(0, limit).map((alert) => (
            <button
              className={`compact-row list-action ${
                detailSelection?.type === "alert" && detailSelection.id === alert.alert_id
                  ? "selected"
                  : ""
              }`}
              key={alert.alert_id}
              onClick={() => setDetailSelection({ type: "alert", id: alert.alert_id })}
              type="button"
            >
              <div>
                <strong>{alert.alert_type}</strong>
                <span>{alert.host ?? alert.service ?? "未知"}</span>
              </div>
              <span className={severityClass(alert.severity)}>{displaySeverity(alert.severity)}</span>
              <span className={lifecycleClass(alert.lifecycle?.status)}>
                {displayLifecycleStatus(alert.lifecycle?.status)}
              </span>
            </button>
          ))}
        </div>
      </Panel>
    );
  }

  function renderDetailPanel() {
    return (
      <Panel title="详情" icon={Activity}>
        <div className="detail-panel">
          {detailSelection?.type === "incident" && selectedIncident ? (
            <>
              <div className="detail-title">
                <span className={severityClass(selectedIncident.severity)}>
                  {displaySeverity(selectedIncident.severity)}
                </span>
                <h3>{selectedIncident.title ?? selectedIncident.summary}</h3>
              </div>
              <p>{selectedIncident.summary}</p>
              <div className="detail-grid">
                <DetailField label="故障" value={selectedIncident.incident_id} />
                <DetailField label="状态" value={displayLifecycleStatus(selectedIncident.status)} />
                <DetailField label="聚合键" value={selectedIncident.aggregate_key} />
                <DetailField label="告警数" value={selectedIncident.alert_count ?? 0} />
                <DetailField label="创建时间" value={formatDate(selectedIncident.created_at)} />
              </div>
              <p className="detail-label">服务</p>
              <TagList items={selectedIncident.affected_services} />
              <p className="detail-label">主机</p>
              <TagList items={selectedIncident.affected_hosts} />
              <p className="detail-label">事件类型</p>
              <TagList items={selectedIncident.event_types} />
              {canMutateLive ? (
                <button
                  className="full-action"
                  disabled={diagnosisBusy === `incident:${selectedIncident.incident_id}`}
                  onClick={() => void runDiagnosisForIncident(selectedIncident.incident_id)}
                  type="button"
                >
                  <PlayCircle size={15} />
                  运行智能诊断
                </button>
              ) : (
                <p className="readonly-note">Agent 操作需要在线 API 中的故障数据。</p>
              )}
            </>
          ) : null}

          {detailSelection?.type === "alert" && selectedAlert ? (
            <>
              <div className="detail-title">
                <span className={severityClass(selectedAlert.severity)}>
                  {displaySeverity(selectedAlert.severity)}
                </span>
                <h3>{selectedAlert.alert_type}</h3>
              </div>
              <p>{selectedAlert.summary ?? selectedAlert.message}</p>
              <div className="detail-grid">
                <DetailField label="告警" value={selectedAlert.alert_id} />
                <DetailField label="事件" value={selectedAlert.event_type} />
                <DetailField label="状态" value={displayLifecycleStatus(selectedAlert.lifecycle?.status)} />
                <DetailField label="负责人" value={selectedAlert.lifecycle?.owner ?? "未分配"} />
                <DetailField label="次数" value={selectedAlert.count ?? 0} />
                <DetailField label="主机" value={selectedAlert.host ?? selectedAlert.service} />
              </div>
              <div className="button-row">
                <button
                  disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                  onClick={() => void updateAlertLifecycle(selectedAlert, "acknowledged")}
                  type="button"
                >
                  <CheckCircle2 size={14} />
                  确认
                </button>
                <button
                  disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                  onClick={() => void updateAlertLifecycle(selectedAlert, "resolved")}
                  type="button"
                >
                  <CheckCircle2 size={14} />
                  解决
                </button>
                <button
                  disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                  onClick={() => void updateAlertLifecycle(selectedAlert, "open")}
                  type="button"
                >
                  <RotateCcw size={14} />
                  重开
                </button>
              </div>
              {isHighRisk(selectedAlert) && canMutateLive ? (
                <button
                  className="full-action"
                  disabled={diagnosisBusy === `alert:${selectedAlert.alert_id}`}
                  onClick={() => void runDiagnosisForAlert(selectedAlert.alert_id)}
                  type="button"
                >
                  <PlayCircle size={15} />
                  基于告警诊断
                </button>
              ) : (
                <p className="readonly-note">
                  {canMutateLive
                    ? "只有高危和严重告警会显示诊断入口。"
                    : "告警操作需要在线 API 数据。"}
                </p>
              )}
              <JsonBlock value={selectedAlert.fields} />
            </>
          ) : null}

          {detailSelection?.type === "diagnosis" && activeDiagnosis ? (
            <>
              <div className="detail-title">
                <span className="lifecycle acknowledged">{displayDiagnosisStatus(activeDiagnosis.status)}</span>
                <h3>{displayRootCause(activeDiagnosis.root_cause)}</h3>
              </div>
              <div className="detail-grid">
                <DetailField label="诊断" value={activeDiagnosis.diagnosis_id} />
                <DetailField label="故障" value={activeDiagnosis.incident_id} />
                <DetailField label="置信度" value={confidenceLabel(activeDiagnosis.confidence)} />
                <DetailField label="停止原因" value={displayStopReason(activeDiagnosis.stop_reason)} />
                <DetailField label="创建时间" value={formatDate(activeDiagnosis.created_at)} />
              </div>
              <p className="detail-label">证据</p>
              <div className="stack-list">
                {(activeDiagnosis.evidence_chain ?? []).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              <p className="detail-label">建议</p>
              <div className="stack-list">
                {(activeDiagnosis.recommendations ?? []).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </>
          ) : null}

          {detailSelection?.type === "event" && selectedEvent ? (
            <>
              <div className="detail-title">
                <span className={severityClass(selectedEvent.severity_hint)}>
                  {displaySeverity(selectedEvent.severity_hint)}
                </span>
                <h3>{selectedEvent.event_type}</h3>
              </div>
              <p>{selectedEvent.message}</p>
              <div className="detail-grid">
                <DetailField label="事件" value={selectedEvent.event_id} />
                <DetailField label="来源" value={selectedEvent.source_type} />
                <DetailField label="组件" value={selectedEvent.component} />
                <DetailField label="主机" value={selectedEvent.host ?? selectedEvent.service} />
                <DetailField label="时间" value={formatDate(selectedEvent.timestamp)} />
              </div>
              <JsonBlock value={selectedEvent.fields} />
            </>
          ) : null}
        </div>
      </Panel>
    );
  }

  function renderToolPanel(limit = 12) {
    return (
      <Panel
        title="工具审计"
        icon={Database}
        action={
          <RefreshButton
            busy={panelLoading.tools}
            onClick={() => void refreshPanel("tools")}
          />
        }
      >
        <div className="tool-list">
          {data.toolCalls.slice(0, limit).map((tool) => (
            <article key={tool.tool_call_id}>
              <div>
                <Server size={14} />
                <strong>{tool.tool_name}</strong>
              </div>
              <p>{tool.reason}</p>
              <span>
                {tool.result_count} 条结果 · {tool.duration_ms}ms
              </span>
            </article>
          ))}
        </div>
      </Panel>
    );
  }

  function renderChatPanel() {
    return (
      <section className="chat-panel chat-page-panel">
        <header>
          <div>
            <MessageSquare size={16} />
            <label className="session-title-editor">
              <span>会话名称</span>
              <input
                disabled={!chatSessionId || chatTitleSaving}
                onChange={(event) => setChatTitleDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void saveChatSessionTitle();
                  }
                }}
                placeholder="先新建会话，再输入名称"
                value={chatTitleDraft}
              />
            </label>
          </div>
          <div className="chat-header-actions">
            <span>{chatSessionId ? chatSessionId.slice(0, 8) : "未创建会话"}</span>
            <button
              disabled={!chatSessionId || !chatTitleDraft.trim() || chatTitleSaving}
              onClick={() => void saveChatSessionTitle()}
              type="button"
            >
              保存名称
            </button>
            <button
              disabled={!canChat || chatLoading}
              onClick={() => void createChatSession()}
              type="button"
            >
              新建会话
            </button>
          </div>
        </header>
        <div className="chat-thread">
          {chatLoading ? (
            <p className="agent">正在加载会话...</p>
          ) : (
            <>
              {chatMessages.map((message) => (
                <p className={message.role === "user" ? "user" : "agent"} key={message.message_id}>
                  {message.content}
                </p>
              ))}
              {currentSessionSending ? (
                <p className="agent thinking">
                  <span>正在思考...</span>
                  <span className="thinking-spinner" aria-hidden="true" />
                </p>
              ) : null}
            </>
          )}
        </div>
        <form className="chat-input" onSubmit={sendChatMessage}>
          <Clock size={14} />
          <input
            disabled={!canChat || currentSessionSending || chatLoading}
            onChange={(event) => setChatInput(event.target.value)}
            placeholder={
              canChat
                ? chatSessionId
                  ? "输入运维问题"
                  : "输入后会自动创建新会话"
                : "FastAPI 未在线"
            }
            value={chatInput}
          />
          <button disabled={!canChat || currentSessionSending || chatLoading || !chatInput.trim()} type="submit">
            <Send size={15} />
          </button>
        </form>
      </section>
    );
  }

  function renderChatSessionsPanel() {
    return (
      <Panel
        title="会话列表"
        icon={MessageSquare}
        action={
          <RefreshButton
            busy={chatLoading}
            onClick={() => void loadChatSessions(false)}
          />
        }
      >
        <div className="session-list">
          <button
            className="session-row new-session"
            disabled={!canChat || chatLoading}
            onClick={() => void createChatSession()}
            type="button"
          >
            <strong>新建会话</strong>
            <span>创建一个独立上下文</span>
          </button>
          {chatSessions.map((session) => {
            const isSessionSending = sendingSessionIds.includes(session.session_id);
            return (
              <button
                className={`session-row ${
                  chatSessionId === session.session_id ? "selected" : ""
                }`}
                key={session.session_id}
                onClick={() => void loadChatMessages(session.session_id)}
                type="button"
              >
                <strong>
                  {session.title ?? `会话 ${session.session_id.slice(0, 8)}`}
                  {isSessionSending ? (
                    <span className="session-sending" aria-label="Agent 正在回复">
                      <span className="thinking-spinner" aria-hidden="true" />
                    </span>
                  ) : null}
                </strong>
                <span>
                  {session.current_incident_id ?? "通用问答"} · {formatDate(session.updated_at)}
                </span>
              </button>
            );
          })}
          {!chatSessions.length && !chatLoading ? (
            <p className="readonly-note">还没有历史会话。</p>
          ) : null}
        </div>
      </Panel>
    );
  }

  function renderActiveView() {
    if (activePage === "alerts") {
      return (
        <>
          {renderMetrics()}
          <section className="page-grid alerts-page-grid">
            <div className="main-column">
              {renderLifecyclePanel()}
              {renderAlertsPanel()}
              {renderIncidentPanel(6)}
            </div>
            <aside className="side-column">
              {renderDetailPanel()}
              {renderDiagnosisPanel()}
              {renderToolPanel(5)}
            </aside>
          </section>
        </>
      );
    }

    return (
      <section className="page-grid chat-grid">
        <aside className="side-column">{renderChatSessionsPanel()}</aside>
        <div className="main-column">{renderChatPanel()}</div>
      </section>
    );
  }

  const currentView = pageMeta[activePage];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Zap size={20} />
          </div>
          <div>
            <strong>CrossST</strong>
            <span>运维控制台</span>
          </div>
        </div>
        <div className="runtime-card">
          <span>运行状态</span>
          <strong>{health.status === "online" ? "后端 API 在线" : "演示数据兜底"}</strong>
          <p>{error ? error : health.detail}</p>
          {lastUpdated ? <small>更新于 {formatDate(lastUpdated)}</small> : null}
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{currentView.eyebrow}</p>
            <h1>{currentView.title}</h1>
            <p className="view-summary">{currentView.description}</p>
          </div>
          <div className="topbar-actions">
            <div className="page-switch" aria-label="页面切换">
              {pageItems.map(({ label, page, icon: Icon }) => (
                <button
                  className={activePage === page ? "active" : ""}
                  key={page}
                  onClick={() => navigateToPage(page)}
                  type="button"
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>
            <span className={`status-pill ${health.status}`}>
              <span />
              {displayHealthStatus(health.status)}
            </span>
            <span className={`status-pill ${pipelineHealth}`}>
              <span />
              {displayPipelineHealth(pipelineHealth)}
            </span>
            <button onClick={refresh} disabled={loading} type="button">
              <RefreshCw className={loading ? "spin" : ""} size={15} />
              全部刷新
            </button>
          </div>
        </header>

        {notice ? <div className="notice">{notice}</div> : null}

        {renderActiveView()}

      </section>
    </main>
  );
}

export default App;
