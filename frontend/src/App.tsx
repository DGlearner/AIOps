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
  Terminal,
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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
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
  role: "user" | "assistant" | "system";
  content: string;
  incident_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

type ChatSession = {
  session_id: string;
  current_incident_id?: string | null;
};

type ChatSendResponse = {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
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

type SectionId = "overview" | "incidents" | "alerts" | "agent" | "events" | "chat";
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
      summary: "login-service failures correlated with MySQL connection refused",
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
      summary: "SSH login failures exceeded threshold on edge host",
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
      summary: "api-worker container restarted repeatedly after deployment",
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
      summary: "MySQL refused connections for login-service dependency",
      message: "Can't connect to local MySQL server through socket",
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
      summary: "login-service reported database connection errors",
      message: "Database dependency unavailable while authenticating user",
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
      summary: "SSH login failures from repeated source IPs",
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
      trigger_summary: "login-service failure spike followed MySQL connection refused",
      evidence_chain: [
        "query_events:mysql_connection_refused returned 48 records",
        "query_events:app_db_connection_error returned 83 records",
        "query_alerts:login_failed returned 16 alerts in the same window",
      ],
      recommendations: [
        "Check MySQL process, socket, and port listener on db-prod-01.",
        "Keep login-service alert open until DB connectivity recovers.",
        "Review deployment history only after dependency health is restored.",
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
      message: "Can't connect to local MySQL server through socket",
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
      message: "Database dependency unavailable while authenticating user",
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
      message: "Failed password for root from 8.8.8.8",
    },
  ],
  toolCalls: [
    {
      tool_call_id: "tool-001",
      tool_name: "query_events",
      reason: "Check MySQL availability errors near incident window",
      result_count: 48,
      duration_ms: 31,
    },
    {
      tool_call_id: "tool-002",
      tool_name: "query_service_dependencies",
      reason: "Check login-service declared database dependencies",
      result_count: 1,
      duration_ms: 18,
    },
    {
      tool_call_id: "tool-003",
      tool_name: "query_runbooks",
      reason: "Find MySQL unavailable runbook",
      result_count: 1,
      duration_ms: 24,
    },
  ],
};

const navItems: Array<{ label: string; section: SectionId; icon: LucideIcon }> = [
  { label: "Overview", section: "overview", icon: Activity },
  { label: "Incidents", section: "incidents", icon: Radar },
  { label: "Alerts", section: "alerts", icon: AlertTriangle },
  { label: "Agent", section: "agent", icon: Brain },
  { label: "Events", section: "events", icon: Terminal },
  { label: "Chat", section: "chat", icon: MessageSquare },
];

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
    detail: payload.status === "ok" ? "FastAPI health check is online" : "FastAPI is degraded",
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
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function formatDate(value?: string | null) {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
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
  label = "Refresh",
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
  sectionId?: SectionId;
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
  if (!visible.length) return <span className="muted-text">none</span>;
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
      <strong>{value === undefined || value === null || value === "" ? "unknown" : value}</strong>
    </div>
  );
}

function JsonBlock({ value }: { value?: unknown }) {
  if (value === undefined || value === null) return null;
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function App() {
  const [data, setData] = useState<ConsoleData>(demoData);
  const [health, setHealth] = useState<HealthState>({
    status: "checking",
    detail: "Checking FastAPI health",
  });
  const [loading, setLoading] = useState(true);
  const [panelLoading, setPanelLoading] = useState<Partial<Record<PanelKey, boolean>>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeNav, setActiveNav] = useState<SectionId>("overview");
  const [detailSelection, setDetailSelection] = useState<DetailSelection | null>(null);
  const [selectedDiagnosisId, setSelectedDiagnosisId] = useState<string | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      message_id: "local-welcome",
      role: "assistant",
      content: "Select an incident or alert, then ask for evidence, likely cause, or next checks.",
      created_at: new Date().toISOString(),
    },
  ]);
  const [alertBusy, setAlertBusy] = useState<Record<string, string>>({});
  const [diagnosisBusy, setDiagnosisBusy] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const sectionRefs = useRef<Partial<Record<SectionId, HTMLElement | null>>>({});

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

  function registerSection(section: SectionId) {
    return (node: HTMLElement | null) => {
      sectionRefs.current[section] = node;
    };
  }

  function scrollToSection(section: SectionId) {
    setActiveNav(section);
    sectionRefs.current[section]?.scrollIntoView({ behavior: "smooth", block: "start" });
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
            ? healthResult.reason.message
            : "FastAPI health check failed",
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
        dataResult.reason instanceof Error ? dataResult.reason.message : "API unavailable",
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
        detail: "FastAPI request completed",
        checkedAt: new Date().toISOString(),
      }));
      setError(null);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      const message = err instanceof Error ? err.message : "Panel refresh failed";
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
            ? "Reopened from ops console"
            : status === "acknowledged"
              ? "Acknowledged from ops console"
              : "Resolved from ops console",
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
      setNotice(`Alert ${updated.alert_id} moved to ${updated.lifecycle?.status ?? status}.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Alert update failed");
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
      setNotice(`Diagnosis ${diagnosis.diagnosis_id} completed for ${incidentId}.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Diagnosis request failed");
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
      setNotice(`Diagnosis ${diagnosis.diagnosis_id} completed from alert ${alertId}.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Alert diagnosis request failed");
    } finally {
      setDiagnosisBusy(null);
    }
  }

  async function ensureChatSession() {
    if (chatSessionId) return chatSessionId;
    const session = await postJson<ChatSession>("/chat/sessions", {
      user_id: OPS_USER,
      team_id: OPS_TEAM,
      current_incident_id: chatIncident?.incident_id ?? null,
      title: chatIncident
        ? `Ops chat: ${chatIncident.incident_id}`
        : "Ops console chat",
      metadata: {
        client: "ops-console",
      },
    });
    setChatSessionId(session.session_id);
    return session.session_id;
  }

  async function sendChatMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = chatInput.trim();
    if (!content || chatSending || !canChat) return;

    const tempMessage: ChatMessage = {
      message_id: `local-${Date.now()}`,
      role: "user",
      content,
      incident_id: chatIncident?.incident_id ?? null,
      created_at: new Date().toISOString(),
    };

    setChatMessages((current) => [...current, tempMessage]);
    setChatInput("");
    setChatSending(true);
    setNotice(null);

    try {
      const sessionId = await ensureChatSession();
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
      setChatMessages((current) => [
        ...current.filter((message) => message.message_id !== tempMessage.message_id),
        response.user_message,
        response.assistant_message,
      ]);
      setChatSessionId(response.session_id);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Chat message failed");
    } finally {
      setChatSending(false);
    }
  }

  useEffect(() => {
    void refresh();
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

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Zap size={20} />
          </div>
          <div>
            <strong>CrossST</strong>
            <span>Ops Console</span>
          </div>
        </div>
        <nav>
          {navItems.map(({ label, section, icon: Icon }) => (
            <button
              className={activeNav === section ? "active" : ""}
              key={section}
              onClick={() => scrollToSection(section)}
              type="button"
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </nav>
        <div className="runtime-card">
          <span>Runtime</span>
          <strong>{health.status === "online" ? "Live API reachable" : "Demo fallback"}</strong>
          <p>{error ? error : health.detail}</p>
          {lastUpdated ? <small>Updated {formatDate(lastUpdated)}</small> : null}
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">AIOps Incident Intelligence</p>
            <h1>Operations Control Plane</h1>
          </div>
          <div className="topbar-actions">
            <span className={`status-pill ${health.status}`}>
              <span />
              {health.status}
            </span>
            <span className={`status-pill ${pipelineHealth}`}>
              <span />
              {pipelineHealth}
            </span>
            <button onClick={refresh} disabled={loading} type="button">
              <RefreshCw className={loading ? "spin" : ""} size={15} />
              Refresh all
            </button>
          </div>
        </header>

        {notice ? <div className="notice">{notice}</div> : null}

        <section className="metrics-grid" id="overview" ref={registerSection("overview")}>
          <MetricCard
            icon={Terminal}
            label="Events"
            value={formatNumber(data.overview.pipeline_counts.events)}
            detail="normalized log stream"
          />
          <MetricCard
            icon={Shield}
            label="Alerts"
            value={formatNumber(data.overview.pipeline_counts.alerts)}
            detail={`${openCount} open`}
          />
          <MetricCard
            icon={GitBranch}
            label="Incidents"
            value={formatNumber(data.overview.pipeline_counts.incidents)}
            detail={`${criticalCount + highCount} high impact`}
          />
          <MetricCard
            icon={Bot}
            label="Agent Runs"
            value={formatNumber(data.overview.pipeline_counts.diagnoses)}
            detail={`${formatNumber(data.overview.pipeline_counts.tool_calls)} tool calls`}
          />
        </section>

        <section className="content-grid">
          <div className="main-column">
            <Panel
              title="Incident Timeline"
              icon={Radar}
              sectionId="incidents"
              panelRef={registerSection("incidents")}
              action={
                <>
                  <span>last 24h</span>
                  <RefreshButton
                    busy={panelLoading.incidents}
                    onClick={() => void refreshPanel("incidents")}
                  />
                </>
              }
            >
              <div className="incident-list">
                {data.incidents.slice(0, 5).map((incident) => (
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
                          {incident.severity}
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

            <Panel
              title="Agent Diagnosis"
              icon={Brain}
              sectionId="agent"
              panelRef={registerSection("agent")}
              action={
                <>
                  <span>{activeDiagnosis.status}</span>
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
                      <span>Run</span>
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
                  <span>confidence</span>
                </div>
                <div className="diagnosis-body">
                  <p className="eyebrow">Root Cause</p>
                  <h3>{activeDiagnosis.root_cause ?? "needs_human_review"}</h3>
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
                {data.diagnoses.slice(0, 4).map((diagnosis) => (
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
                    <strong>{diagnosis.root_cause ?? diagnosis.status}</strong>
                    <span>{diagnosis.incident_id}</span>
                    <em>{confidenceLabel(diagnosis.confidence)}</em>
                  </button>
                ))}
              </div>
            </Panel>

            <Panel
              title="Normalized Event Stream"
              icon={Terminal}
              sectionId="events"
              panelRef={registerSection("events")}
              action={
                <>
                  <span>sample</span>
                  <RefreshButton
                    busy={panelLoading.events}
                    onClick={() => void refreshPanel("events")}
                  />
                </>
              }
            >
              <div className="event-table">
                {data.events.slice(0, 7).map((event) => (
                  <button
                    className={`event-row list-action ${
                      detailSelection?.type === "event" && detailSelection.id === event.event_id
                        ? "selected"
                        : ""
                    }`}
                    key={event.event_id}
                    onClick={() => setDetailSelection({ type: "event", id: event.event_id })}
                    type="button"
                  >
                    <span>{event.source_type}</span>
                    <strong>{event.event_type}</strong>
                    <em>{event.host ?? event.service ?? "unknown"}</em>
                    <small>{event.severity_hint}</small>
                  </button>
                ))}
              </div>
            </Panel>
          </div>

          <aside className="side-column">
            <Panel
              title="Alert Lifecycle"
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
                    <span>{status}</span>
                    <strong>{count}</strong>
                    <meter value={count} max={data.overview.alert_lifecycle.total ?? 1} />
                  </div>
                ))}
              </div>
            </Panel>

            <Panel
              title="Active Alerts"
              icon={Shield}
              sectionId="alerts"
              panelRef={registerSection("alerts")}
              action={
                <RefreshButton
                  busy={panelLoading.alerts}
                  onClick={() => void refreshPanel("alerts")}
                />
              }
            >
              <div className="compact-list">
                {data.alerts.slice(0, 5).map((alert) => (
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
                      <span>{alert.host ?? alert.service ?? "unknown"}</span>
                    </div>
                    <span className={severityClass(alert.severity)}>{alert.severity}</span>
                    <span className={lifecycleClass(alert.lifecycle?.status)}>
                      {alert.lifecycle?.status ?? "open"}
                    </span>
                  </button>
                ))}
              </div>
            </Panel>

            <Panel title="Selection Details" icon={Activity}>
              <div className="detail-panel">
                {detailSelection?.type === "incident" && selectedIncident ? (
                  <>
                    <div className="detail-title">
                      <span className={severityClass(selectedIncident.severity)}>
                        {selectedIncident.severity}
                      </span>
                      <h3>{selectedIncident.title ?? selectedIncident.summary}</h3>
                    </div>
                    <p>{selectedIncident.summary}</p>
                    <div className="detail-grid">
                      <DetailField label="Incident" value={selectedIncident.incident_id} />
                      <DetailField label="Status" value={selectedIncident.status} />
                      <DetailField label="Aggregate" value={selectedIncident.aggregate_key} />
                      <DetailField label="Alerts" value={selectedIncident.alert_count ?? 0} />
                      <DetailField label="Created" value={formatDate(selectedIncident.created_at)} />
                    </div>
                    <p className="detail-label">Services</p>
                    <TagList items={selectedIncident.affected_services} />
                    <p className="detail-label">Hosts</p>
                    <TagList items={selectedIncident.affected_hosts} />
                    <p className="detail-label">Event types</p>
                    <TagList items={selectedIncident.event_types} />
                    {canMutateLive ? (
                      <button
                        className="full-action"
                        disabled={
                          diagnosisBusy === `incident:${selectedIncident.incident_id}`
                        }
                        onClick={() => void runDiagnosisForIncident(selectedIncident.incident_id)}
                        type="button"
                      >
                        <PlayCircle size={15} />
                        Run agent diagnosis
                      </button>
                    ) : (
                      <p className="readonly-note">Agent actions require a live API incident.</p>
                    )}
                  </>
                ) : null}

                {detailSelection?.type === "alert" && selectedAlert ? (
                  <>
                    <div className="detail-title">
                      <span className={severityClass(selectedAlert.severity)}>
                        {selectedAlert.severity}
                      </span>
                      <h3>{selectedAlert.alert_type}</h3>
                    </div>
                    <p>{selectedAlert.summary ?? selectedAlert.message}</p>
                    <div className="detail-grid">
                      <DetailField label="Alert" value={selectedAlert.alert_id} />
                      <DetailField label="Event" value={selectedAlert.event_type} />
                      <DetailField label="Status" value={selectedAlert.lifecycle?.status ?? "open"} />
                      <DetailField label="Owner" value={selectedAlert.lifecycle?.owner ?? "unowned"} />
                      <DetailField label="Count" value={selectedAlert.count ?? 0} />
                      <DetailField label="Host" value={selectedAlert.host ?? selectedAlert.service} />
                    </div>
                    <div className="button-row">
                      <button
                        disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                        onClick={() => void updateAlertLifecycle(selectedAlert, "acknowledged")}
                        type="button"
                      >
                        <CheckCircle2 size={14} />
                        Acknowledge
                      </button>
                      <button
                        disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                        onClick={() => void updateAlertLifecycle(selectedAlert, "resolved")}
                        type="button"
                      >
                        <CheckCircle2 size={14} />
                        Resolve
                      </button>
                      <button
                        disabled={!canMutateLive || Boolean(alertBusy[selectedAlert.alert_id])}
                        onClick={() => void updateAlertLifecycle(selectedAlert, "open")}
                        type="button"
                      >
                        <RotateCcw size={14} />
                        Reopen
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
                        Diagnose from alert
                      </button>
                    ) : (
                      <p className="readonly-note">
                        {canMutateLive
                          ? "Diagnosis entry is shown for high and critical alerts."
                          : "Alert actions require live API data."}
                      </p>
                    )}
                    <JsonBlock value={selectedAlert.fields} />
                  </>
                ) : null}

                {detailSelection?.type === "diagnosis" && activeDiagnosis ? (
                  <>
                    <div className="detail-title">
                      <span className="lifecycle acknowledged">{activeDiagnosis.status}</span>
                      <h3>{activeDiagnosis.root_cause ?? "needs_human_review"}</h3>
                    </div>
                    <div className="detail-grid">
                      <DetailField label="Diagnosis" value={activeDiagnosis.diagnosis_id} />
                      <DetailField label="Incident" value={activeDiagnosis.incident_id} />
                      <DetailField label="Confidence" value={confidenceLabel(activeDiagnosis.confidence)} />
                      <DetailField label="Stop reason" value={activeDiagnosis.stop_reason} />
                      <DetailField label="Created" value={formatDate(activeDiagnosis.created_at)} />
                    </div>
                    <p className="detail-label">Evidence</p>
                    <div className="stack-list">
                      {(activeDiagnosis.evidence_chain ?? []).map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                    <p className="detail-label">Recommendations</p>
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
                        {selectedEvent.severity_hint}
                      </span>
                      <h3>{selectedEvent.event_type}</h3>
                    </div>
                    <p>{selectedEvent.message}</p>
                    <div className="detail-grid">
                      <DetailField label="Event" value={selectedEvent.event_id} />
                      <DetailField label="Source" value={selectedEvent.source_type} />
                      <DetailField label="Component" value={selectedEvent.component} />
                      <DetailField label="Host" value={selectedEvent.host ?? selectedEvent.service} />
                      <DetailField label="Timestamp" value={formatDate(selectedEvent.timestamp)} />
                    </div>
                    <JsonBlock value={selectedEvent.fields} />
                  </>
                ) : null}
              </div>
            </Panel>

            <Panel
              title="Tool Audit"
              icon={Database}
              action={
                <RefreshButton
                  busy={panelLoading.tools}
                  onClick={() => void refreshPanel("tools")}
                />
              }
            >
              <div className="tool-list">
                {data.toolCalls.slice(0, 4).map((tool) => (
                  <article key={tool.tool_call_id}>
                    <div>
                      <Server size={14} />
                      <strong>{tool.tool_name}</strong>
                    </div>
                    <p>{tool.reason}</p>
                    <span>
                      {tool.result_count} result(s) · {tool.duration_ms}ms
                    </span>
                  </article>
                ))}
              </div>
            </Panel>

            <section className="chat-panel" id="chat" ref={registerSection("chat")}>
              <header>
                <div>
                  <MessageSquare size={16} />
                  <strong>Ops Chat</strong>
                </div>
                <span>{chatSessionId ? chatSessionId.slice(0, 8) : "new session"}</span>
              </header>
              <div className="chat-thread">
                {chatMessages.map((message) => (
                  <p className={message.role === "user" ? "user" : "agent"} key={message.message_id}>
                    {message.content}
                  </p>
                ))}
              </div>
              <form className="chat-input" onSubmit={sendChatMessage}>
                <Clock size={14} />
                <input
                  disabled={!canChat || chatSending}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder={
                    canChat
                      ? chatIncident
                        ? `Ask about ${chatIncident.incident_id}`
                        : "Ask an ops question"
                      : "FastAPI is offline"
                  }
                  value={chatInput}
                />
                <button disabled={!canChat || chatSending || !chatInput.trim()} type="submit">
                  <Send size={15} />
                </button>
              </form>
            </section>
          </aside>
        </section>
      </section>
    </main>
  );
}

export default App;
