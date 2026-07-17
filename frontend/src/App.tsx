import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AppShell,
  fetchCurrentIdentityUser,
  fetchServiceRegistry,
  Icon,
  serviceLinksFromRegistry,
  type ServiceRegistryItem,
} from "@turkuaz/ui";
import {
  clearToken,
  createSource,
  exportReport,
  fetchAdminReport,
  fetchExecutions,
  fetchMe,
  fetchReports,
  fetchSources,
  getToken,
  login,
  previewReport,
  saveReport,
  testSource,
} from "./api";
import type {
  CurrentUser,
  DataSource,
  Execution,
  ParameterType,
  Preview,
  ReportParameter,
  ReportSummary,
  ReportWrite,
} from "./types";

type View = "catalog" | "reports" | "sources" | "audit";
type LoadState = { loading: boolean; error: string | null; notice: string | null };
const LOCAL_AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "true";
const MOBILE_SHELL = typeof window !== "undefined" && window.matchMedia("(max-width: 1040px)").matches;
const SHELL_STORAGE_KEY = MOBILE_SHELL ? "report-builder-shell-mobile" : "report-builder-shell";
const REPORT_READ_PERMISSION = "report_builder.reports.read";
const IDENTITY_OPTIONS = {
  identityApiBaseUrl: "/identity-api",
  tokenStorageKeys: ["identity_access_token", "access_token"],
};
if (MOBILE_SHELL && localStorage.getItem(`${SHELL_STORAGE_KEY}:sidebar`) === null) {
  localStorage.setItem(`${SHELL_STORAGE_KEY}:sidebar`, "collapsed");
}

const emptyState: LoadState = { loading: false, error: null, notice: null };
const emptyReport = (sourceId = 0): ReportWrite => ({
  slug: "",
  name: "",
  description: "",
  data_source_id: sourceId,
  query_template: "",
  parameters: [
    {
      name: "date_from",
      label: "Дата с",
      type: "date",
      required: true,
      default: null,
      placeholder: null,
    },
  ],
  default_row_limit: 1000,
  max_row_limit: 10000,
  is_published: false,
});

function queryTemplateForEngine(engine: DataSource["engine"] = "mssql") {
  return "";
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()) || LOCAL_AUTH_DISABLED);
  const [view, setView] = useState<View>("catalog");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [services, setServices] = useState<ServiceRegistryItem[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [search, setSearch] = useState("");
  const [loginNotice, setLoginNotice] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>({ ...emptyState, loading: true });

  async function loadApp() {
    if (!getToken() && !LOCAL_AUTH_DISABLED) {
      setAuthenticated(false);
      setState(emptyState);
      return;
    }
    setState({ loading: true, error: null, notice: null });
    try {
      const [currentUser, identityUser, serviceRows] = await Promise.all([
        fetchMe(),
        fetchCurrentIdentityUser(IDENTITY_OPTIONS).catch(() => null),
        fetchServiceRegistry(IDENTITY_OPTIONS).catch(() => [] as ServiceRegistryItem[]),
      ]);
      setUser(currentUser);
      setServices(serviceRows);
      setAuthenticated(true);

      const tokenHasReadAccess = currentUser.permissions.includes(REPORT_READ_PERMISSION);
      const identityHasReadAccess = identityUser?.permissions.includes(REPORT_READ_PERMISSION);
      if (identityHasReadAccess !== undefined && tokenHasReadAccess !== identityHasReadAccess) {
        clearToken();
        setAuthenticated(false);
        setUser(null);
        setReports([]);
        setLoginNotice("Права учетной записи изменились. Войдите ещё раз, чтобы получить новый токен.");
        setState(emptyState);
        return;
      }
      if (!tokenHasReadAccess) {
        setReports([]);
        setState({
          loading: false,
          error: `Для ${currentUser.email} не назначено право ${REPORT_READ_PERMISSION}. Назначьте роль report_builder_user в Identity.`,
          notice: null,
        });
        return;
      }

      setReports(await fetchReports(search));
      setState(emptyState);
    } catch (error) {
      if (!getToken()) setAuthenticated(false);
      setState({ loading: false, error: errorMessage(error), notice: null });
    }
  }

  useEffect(() => {
    void loadApp();
  }, []);

  useEffect(() => {
    if (!authenticated || !user?.permissions.includes(REPORT_READ_PERMISSION)) return;
    const timer = window.setTimeout(() => {
      fetchReports(search).then(setReports).catch((error) => setState({ ...emptyState, error: errorMessage(error) }));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search, authenticated, user]);

  if (!authenticated) {
    return (
      <LoginScreen
        notice={loginNotice}
        onAuthenticated={() => {
          setLoginNotice(null);
          setAuthenticated(true);
          void loadApp();
        }}
      />
    );
  }

  const sections = [
    { key: "catalog" as View, label: "Отчеты", icon: "file" as const, permissions: ["report_builder.reports.read"] },
    { key: "reports" as View, label: "Конструктор", icon: "sliders" as const, permissions: ["report_builder.reports.manage"] },
    { key: "sources" as View, label: "Источники", icon: "database" as const, permissions: ["report_builder.sources.manage"] },
    { key: "audit" as View, label: "Журнал", icon: "activity" as const, permissions: ["report_builder.audit.read"] },
  ];
  const pageMeta: Record<View, [string, string]> = {
    catalog: ["Готовые отчеты", "Запуск опубликованных отчетов и выгрузка результата"],
    reports: ["Конструктор отчетов", "SQL-шаблоны, параметры и публикация"],
    sources: ["Источники данных", "Read-only подключения и разрешенные схемы"],
    audit: ["Журнал запусков", "Результаты выполнения и ошибки"],
  };
  const [pageTitle, pageDescription] = pageMeta[view];

  function logout() {
    clearToken();
    setLoginNotice(null);
    setAuthenticated(false);
    setUser(null);
    setReports([]);
  }

  function changeView(nextView: View) {
    if (MOBILE_SHELL) localStorage.setItem(`${SHELL_STORAGE_KEY}:sidebar`, "collapsed");
    setView(nextView);
  }

  return (
    <AppShell
      key={view}
      storageKey={SHELL_STORAGE_KEY}
      brand={{ href: "/", mark: "R", title: "TURKUAZ", subtitle: "Report Builder" }}
      serviceName="Report Builder"
      pageTitle={pageTitle}
      pageDescription={pageDescription}
      breadcrumbs={[{ label: "Отчеты" }, { label: pageTitle }]}
      navItems={sections.map((section) => ({
        ...section,
        active: view === section.key,
        onClick: () => changeView(section.key),
      }))}
      sideLinks={[
        ...serviceLinksFromRegistry(services, { currentServiceCode: "report_builder" }),
        { href: "/docs", label: "Swagger", icon: "file", permissions: ["report_builder.reports.manage"] },
      ]}
      accessClaims={user}
      tokenStorageKeys={["identity_access_token", "access_token"]}
      search={view === "catalog" ? { value: search, placeholder: "Поиск отчета", onChange: setSearch } : undefined}
      headerActions={[
        { key: "refresh", label: "Обновить", icon: "refresh", onClick: () => void loadApp() },
        { key: "logout", label: "Выйти", icon: "logout", onClick: logout },
      ]}
      user={user ? {
        name: user.full_name || user.email,
        email: user.email,
        role: user.roles[0],
      } : undefined}
      environment={import.meta.env.MODE}
      version="v0.1.0"
      apiStatus={state.error ? "degraded" : "online"}
      footerLinks={[{ href: "/docs", label: "Swagger" }]}
    >
      {state.error && <Notice tone="error" text={state.error} onClose={() => setState(emptyState)} />}
      {state.loading && reports.length === 0 ? <Loading /> : null}
      {view === "catalog" && !state.loading ? <ReportCatalog reports={reports} canManage={Boolean(user?.can_manage_reports)} /> : null}
      {view === "reports" && user?.can_manage_reports ? <ReportAdminPage reports={reports} onChanged={loadApp} /> : null}
      {view === "sources" && user?.can_manage_sources ? <SourcesPage /> : null}
      {view === "audit" && user?.can_read_audit ? <AuditPage /> : null}
    </AppShell>
  );
}

function LoginScreen({ notice, onAuthenticated }: { notice: string | null; onAuthenticated: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoadState>(emptyState);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState({ loading: true, error: null, notice: null });
    try {
      await login(email.trim(), password);
      onAuthenticated();
    } catch (error) {
      setState({ loading: false, error: errorMessage(error), notice: null });
    }
  }

  return (
    <main className="login-page">
      <form className="login-form" onSubmit={submit}>
        <div className="login-brand"><span>R</span><div><strong>TURKUAZ</strong><small>Report Builder</small></div></div>
        <div className="login-heading"><h1>Вход</h1><p>Корпоративная учетная запись TURKUAZ</p></div>
        {notice && <div className="inline-notice">{notice}</div>}
        {state.error && <div className="inline-error">{state.error}</div>}
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Пароль<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <button className="button primary full" type="submit" disabled={state.loading}>{state.loading ? "Вход..." : "Войти"}</button>
      </form>
    </main>
  );
}

function ReportCatalog({ reports, canManage }: { reports: ReportSummary[]; canManage: boolean }) {
  const visible = useMemo(() => canManage ? reports : reports.filter((report) => report.is_published), [reports, canManage]);
  const [selectedId, setSelectedId] = useState<number | null>(visible[0]?.id ?? null);
  const selected = visible.find((report) => report.id === selectedId) ?? visible[0] ?? null;
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [rowLimit, setRowLimit] = useState(1000);
  const [format, setFormat] = useState<"xlsx" | "csv">("xlsx");
  const [state, setState] = useState<LoadState>(emptyState);

  useEffect(() => {
    if (!selected) return;
    setValues(Object.fromEntries(selected.parameters.map((parameter) => [parameter.name, parameter.default ?? ""])));
    setRowLimit(selected.default_row_limit);
    setPreview(null);
    setState(emptyState);
  }, [selected?.id]);

  async function runPreview() {
    if (!selected) return;
    setState({ loading: true, error: null, notice: null });
    try {
      setPreview(await previewReport(selected.id, values, rowLimit));
      setState(emptyState);
    } catch (error) {
      setState({ loading: false, error: errorMessage(error), notice: null });
    }
  }

  async function download() {
    if (!selected) return;
    setState({ loading: true, error: null, notice: null });
    try {
      await exportReport(selected, values, format, rowLimit);
      setState({ loading: false, error: null, notice: "Файл сформирован" });
    } catch (error) {
      setState({ loading: false, error: errorMessage(error), notice: null });
    }
  }

  if (visible.length === 0) return <Empty icon="file" title="Нет доступных отчетов" text="Опубликованные отчеты появятся здесь." />;

  return (
    <main className="catalog-layout">
      <aside className="report-list" aria-label="Список отчетов">
        <div className="section-title"><span>{visible.length}</span><h2>Отчеты</h2></div>
        {visible.map((report) => (
          <button key={report.id} className={report.id === selected?.id ? "report-item active" : "report-item"} type="button" onClick={() => setSelectedId(report.id)}>
            <span className="report-icon"><Icon name="file" size={18} /></span>
            <span><strong>{report.name}</strong><small>{report.data_source_name}</small></span>
            {!report.is_published && <i>Черновик</i>}
          </button>
        ))}
      </aside>
      {selected && (
        <section className="report-workspace">
          <header className="report-header">
            <div><div className="status-line"><span className={selected.is_published ? "status good" : "status wait"}>{selected.is_published ? "Опубликован" : "Черновик"}</span><span>{selected.data_source_name}</span></div><h2>{selected.name}</h2><p>{selected.description || "Без описания"}</p></div>
          </header>
          {state.error && <Notice tone="error" text={state.error} onClose={() => setState(emptyState)} />}
          {state.notice && <Notice tone="success" text={state.notice} onClose={() => setState(emptyState)} />}
          <form className="run-form" onSubmit={(event) => { event.preventDefault(); void runPreview(); }}>
            <div className="parameter-grid">
              {selected.parameters.map((parameter) => (
                <ParameterInput key={parameter.name} parameter={parameter} value={values[parameter.name]} onChange={(value) => setValues({ ...values, [parameter.name]: value })} />
              ))}
              <label>Строк в выгрузке<input type="number" min="1" max={selected.max_row_limit} value={rowLimit} onChange={(event) => setRowLimit(Number(event.target.value))} /></label>
            </div>
            <div className="run-actions">
              <button className="button secondary" type="submit" disabled={state.loading}><Icon name="search" size={16} /> Предпросмотр</button>
              <div className="segmented" aria-label="Формат файла">
                <button className={format === "xlsx" ? "active" : ""} type="button" onClick={() => setFormat("xlsx")}>XLSX</button>
                <button className={format === "csv" ? "active" : ""} type="button" onClick={() => setFormat("csv")}>CSV</button>
              </div>
              <button className="button primary" type="button" disabled={state.loading} onClick={() => void download()}><Icon name="arrow" size={16} /> Выгрузить</button>
            </div>
          </form>
          <PreviewTable preview={preview} loading={state.loading} />
        </section>
      )}
    </main>
  );
}

function ParameterInput({ parameter, value, onChange }: { parameter: ReportParameter; value: unknown; onChange: (value: unknown) => void }) {
  if (parameter.type === "boolean") {
    return <label className="checkbox-field"><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} /><span>{parameter.label}</span></label>;
  }
  const type = parameter.type === "date" ? "date" : parameter.type === "datetime" ? "datetime-local" : parameter.type === "integer" || parameter.type === "decimal" ? "number" : "text";
  return <label>{parameter.label}<input required={parameter.required} type={type} step={parameter.type === "decimal" ? "any" : undefined} value={String(value ?? "")} placeholder={parameter.placeholder || undefined} onChange={(event) => onChange(event.target.value)} /></label>;
}

function PreviewTable({ preview, loading }: { preview: Preview | null; loading: boolean }) {
  if (loading) return <Loading label="Выполнение отчета" />;
  if (!preview) return <div className="preview-empty"><Icon name="database" size={24} /><span>Предпросмотр результата</span></div>;
  return <section className="preview-section"><div className="table-heading"><h3>Результат</h3><span>{preview.row_count} строк · {preview.duration_ms} мс{preview.truncated ? " · показана часть" : ""}</span></div><div className="table-wrap"><table><thead><tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, index) => <td key={`${rowIndex}-${index}`}>{formatCell(value)}</td>)}</tr>)}</tbody></table></div></section>;
}

function ReportAdminPage({ reports, onChanged }: { reports: ReportSummary[]; onChanged: () => Promise<void> }) {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ReportWrite>(emptyReport());
  const [state, setState] = useState<LoadState>(emptyState);

  useEffect(() => {
    fetchSources().then((rows) => { setSources(rows); setForm((current) => current.data_source_id ? current : { ...current, data_source_id: rows[0]?.id || 0 }); }).catch((error) => setState({ ...emptyState, error: errorMessage(error) }));
  }, []);

  async function edit(id: number) {
    setState({ loading: true, error: null, notice: null });
    try {
      const report = await fetchAdminReport(id);
      setEditingId(id);
      setForm({
        slug: report.slug, name: report.name, description: report.description || "", data_source_id: report.data_source_id,
        query_template: report.query_template, parameters: report.parameters, default_row_limit: report.default_row_limit,
        max_row_limit: report.max_row_limit, is_published: report.is_published,
      });
      setState(emptyState);
    } catch (error) { setState({ ...emptyState, error: errorMessage(error) }); }
  }

  function startNew() {
    setEditingId(null);
    setForm({ ...emptyReport(sources[0]?.id || 0), query_template: queryTemplateForEngine(sources[0]?.engine) });
    setState(emptyState);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState({ loading: true, error: null, notice: null });
    try {
      const saved = await saveReport(form, editingId || undefined);
      setEditingId(saved.id);
      setState({ loading: false, error: null, notice: "Отчет сохранен" });
      await onChanged();
    } catch (error) { setState({ loading: false, error: errorMessage(error), notice: null }); }
  }

  function updateParameter(index: number, patch: Partial<ReportParameter>) {
    setForm({ ...form, parameters: form.parameters.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }

  return <main className="admin-layout">
    <aside className="admin-list"><div className="admin-list-header"><h2>Отчеты</h2><button className="icon-button" type="button" title="Новый отчет" onClick={startNew}><Icon name="plus" size={18} /></button></div>{reports.map((report) => <button className={editingId === report.id ? "admin-list-item active" : "admin-list-item"} key={report.id} type="button" onClick={() => void edit(report.id)}><span><strong>{report.name}</strong><small>{report.slug}</small></span><i className={report.is_published ? "dot good" : "dot"} /></button>)}</aside>
    <form className="editor" onSubmit={submit}>
      <div className="editor-toolbar"><div><span className="eyebrow">{editingId ? `Отчет #${editingId}` : "Новый отчет"}</span><h2>{form.name || "Без названия"}</h2></div><div className="toolbar-actions"><label className="publish-toggle"><input type="checkbox" checked={form.is_published} onChange={(event) => setForm({ ...form, is_published: event.target.checked })} /><span>{form.is_published ? "Опубликован" : "Черновик"}</span></label><button className="button primary" type="submit" disabled={state.loading}>Сохранить</button></div></div>
      {state.error && <Notice tone="error" text={state.error} onClose={() => setState(emptyState)} />}{state.notice && <Notice tone="success" text={state.notice} onClose={() => setState(emptyState)} />}
      <section className="editor-section"><h3>Карточка</h3><div className="form-grid"><label>Название<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Код<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value.toLowerCase() })} /></label><label>Источник<select required value={form.data_source_id || ""} onChange={(event) => setForm({ ...form, data_source_id: Number(event.target.value) })}><option value="">Выберите источник</option>{sources.filter((source) => source.is_active).map((source) => <option value={source.id} key={source.id}>{source.name}</option>)}</select></label><label className="span-3">Описание<textarea rows={2} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label></div></section>
      <section className="editor-section sql-section"><div className="section-heading"><h3>SQL-шаблон</h3><span>{sources.find((source) => source.id === form.data_source_id)?.engine === "postgresql" ? "PostgreSQL" : "MSSQL"}</span></div><p className="form-hint">Разрешён один параметризованный SELECT или CTE. Не используйте INSERT, UPDATE, DELETE и другие команды изменения данных.</p><textarea className="sql-editor" spellCheck={false} required placeholder={sources.find((source) => source.id === form.data_source_id)?.engine === "postgresql" ? "SELECT\n  column_name\nFROM public.table_name\nWHERE created_at >= :date_from" : "SELECT\n  TOP 100 column_name\nFROM dbo.table_name\nWHERE created_at >= :date_from"} value={form.query_template} onChange={(event) => setForm({ ...form, query_template: event.target.value })} /></section>
      <section className="editor-section"><div className="section-heading"><h3>Параметры</h3><button className="button secondary compact" type="button" onClick={() => setForm({ ...form, parameters: [...form.parameters, { name: "parameter", label: "Параметр", type: "text", required: true, default: null, placeholder: null }] })}><Icon name="plus" size={15} /> Добавить</button></div><div className="parameter-admin-list">{form.parameters.map((parameter, index) => <div className="parameter-row" key={`${index}-${parameter.name}`}><label>Имя<input required value={parameter.name} onChange={(event) => updateParameter(index, { name: event.target.value })} /></label><label>Подпись<input required value={parameter.label} onChange={(event) => updateParameter(index, { label: event.target.value })} /></label><label>Тип<select value={parameter.type} onChange={(event) => updateParameter(index, { type: event.target.value as ParameterType })}>{["text", "integer", "decimal", "date", "datetime", "boolean"].map((type) => <option key={type}>{type}</option>)}</select></label><label className="checkbox-field"><input type="checkbox" checked={parameter.required} onChange={(event) => updateParameter(index, { required: event.target.checked })} /><span>Обязательный</span></label><button className="icon-button danger" title="Удалить параметр" type="button" onClick={() => setForm({ ...form, parameters: form.parameters.filter((_, itemIndex) => itemIndex !== index) })}><Icon name="ban" size={16} /></button></div>)}</div></section>
      <section className="editor-section"><h3>Лимиты</h3><div className="form-grid limits"><label>По умолчанию<input type="number" min="1" max={form.max_row_limit} value={form.default_row_limit} onChange={(event) => setForm({ ...form, default_row_limit: Number(event.target.value) })} /></label><label>Максимум<input type="number" min="1" max="50000" value={form.max_row_limit} onChange={(event) => setForm({ ...form, max_row_limit: Number(event.target.value) })} /></label></div></section>
    </form>
  </main>;
}

function SourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const emptySourceForm = {
    name: "",
    engine: "mssql" as DataSource["engine"],
    host: "",
    port: "",
    database: "",
    username: "",
    password: "",
    schemas: "",
  };
  const [form, setForm] = useState(emptySourceForm);
  const [state, setState] = useState<LoadState>({ ...emptyState, loading: true });
  async function load() { try { setSources(await fetchSources()); setState(emptyState); } catch (error) { setState({ ...emptyState, error: errorMessage(error) }); } }
  useEffect(() => { void load(); }, []);
  function buildDsn() {
    const user = encodeURIComponent(form.username);
    const password = encodeURIComponent(form.password);
    const host = form.host.trim();
    const port = form.port.trim();
    const database = encodeURIComponent(form.database.trim());
    if (form.engine === "mssql") {
      return `mssql+pyodbc://${user}:${password}@${host}:${port}/${database}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes`;
    }
    return `postgresql+psycopg://${user}:${password}@${host}:${port}/${database}`;
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setState({ loading: true, error: null, notice: null });
    try {
      await createSource({ name: form.name, engine: form.engine, dsn: buildDsn(), allowed_schemas: form.schemas.split(",").map((item) => item.trim()).filter(Boolean), is_active: true });
      setForm(emptySourceForm);
      await load();
      setState({ ...emptyState, notice: "Источник добавлен" });
    } catch (error) { setState({ ...emptyState, error: errorMessage(error) }); }
  }
  async function check(id: number) { setState({ loading: true, error: null, notice: null }); try { const result = await testSource(id); setState({ ...emptyState, notice: result.message }); } catch (error) { setState({ ...emptyState, error: errorMessage(error) }); } }
  return <main className="sources-layout"><form className="source-form" onSubmit={submit}><h2>Новый источник</h2><p className="form-hint">Параметры подключения вводятся отдельно. Пароль хранится на сервере в зашифрованном виде.</p>{state.error && <div className="inline-error">{state.error}</div>}<label>Название<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>СУБД<select value={form.engine} onChange={(event) => { const engine = event.target.value as DataSource["engine"]; setForm({ ...form, engine, schemas: "", port: "" }); }}><option value="mssql">Microsoft SQL Server</option><option value="postgresql">PostgreSQL</option></select></label><div className="source-connection-grid"><label>IP / Host<input required value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} /></label><label>Порт<input required inputMode="numeric" pattern="[0-9]{1,5}" value={form.port} onChange={(event) => setForm({ ...form, port: event.target.value })} /></label></div><label>База данных<input required value={form.database} onChange={(event) => setForm({ ...form, database: event.target.value })} /></label><label>Логин<input required autoComplete="username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label><label>Пароль<input required type="password" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label><label>Разрешенные схемы<input required value={form.schemas} onChange={(event) => setForm({ ...form, schemas: event.target.value })} /><small className="field-hint">Несколько схем — через запятую.</small></label><button className="button primary full" type="submit" disabled={state.loading}><Icon name="plus" size={16} /> Добавить</button></form><section className="source-list"><div className="table-heading"><h2>Подключения</h2><span>{sources.length}</span></div>{state.notice && <Notice tone="success" text={state.notice} onClose={() => setState(emptyState)} />}{sources.length === 0 && !state.loading ? <Empty icon="database" title="Источников нет" text="Добавьте первое подключение." /> : sources.map((source) => <article className="source-item" key={source.id}><span className="source-icon"><Icon name="database" size={20} /></span><div><strong>{source.name}</strong><small>{source.engine.toUpperCase()} · {source.target}</small><p>{source.allowed_schemas.join(", ")}</p></div><span className={source.is_active ? "status good" : "status muted"}>{source.is_active ? "Активен" : "Отключен"}</span><button className="button secondary compact" type="button" disabled={state.loading} onClick={() => void check(source.id)}><Icon name="activity" size={15} /> Проверить</button></article>)}</section></main>;
}

function AuditPage() {
  const [rows, setRows] = useState<Execution[]>([]);
  const [state, setState] = useState<LoadState>({ ...emptyState, loading: true });
  useEffect(() => { fetchExecutions().then((items) => { setRows(items); setState(emptyState); }).catch((error) => setState({ ...emptyState, error: errorMessage(error) })); }, []);
  if (state.loading) return <Loading />;
  if (state.error) return <Notice tone="error" text={state.error} onClose={() => setState(emptyState)} />;
  if (!rows.length) return <Empty icon="activity" title="Запусков пока нет" text="Журнал заполнится после выполнения отчета." />;
  return <main className="audit-page"><div className="table-wrap"><table><thead><tr><th>Время</th><th>Отчет</th><th>Пользователь</th><th>Формат</th><th>Строки</th><th>Время</th><th>Статус</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{formatDate(row.started_at)}</td><td><strong>{row.report_name}</strong></td><td>{row.actor || "-"}</td><td>{row.output_format.toUpperCase()}</td><td>{row.row_count ?? "-"}</td><td>{row.duration_ms != null ? `${row.duration_ms} мс` : "-"}</td><td><span className={row.status === "success" ? "status good" : "status bad"}>{row.status === "success" ? "Успешно" : row.error_code || "Ошибка"}</span></td></tr>)}</tbody></table></div></main>;
}

function Notice({ tone, text, onClose }: { tone: "error" | "success"; text: string; onClose: () => void }) { return <div className={`notice ${tone}`}><span>{text}</span><button type="button" title="Закрыть" onClick={onClose}>×</button></div>; }
function Loading({ label = "Загрузка" }: { label?: string }) { return <div className="loading"><span /><p>{label}...</p></div>; }
function Empty({ icon, title, text }: { icon: "file" | "database" | "activity"; title: string; text: string }) { return <div className="empty"><Icon name={icon} size={28} /><h2>{title}</h2><p>{text}</p></div>; }
function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }
function formatCell(value: unknown): string { if (value == null) return "-"; if (typeof value === "object") return JSON.stringify(value); return String(value); }
function formatDate(value: string): string { return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
