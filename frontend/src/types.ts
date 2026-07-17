export type ParameterType = "text" | "integer" | "decimal" | "date" | "datetime" | "boolean";

export type ReportParameter = {
  name: string;
  label: string;
  type: ParameterType;
  required: boolean;
  default: unknown;
  placeholder: string | null;
};

export type ReportSummary = {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  parameters: ReportParameter[];
  default_row_limit: number;
  max_row_limit: number;
  is_published: boolean;
  data_source_name: string;
  updated_at: string;
};

export type ReportAdmin = ReportSummary & {
  data_source_id: number;
  query_template: string;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
};

export type ReportWrite = {
  slug: string;
  name: string;
  description: string;
  data_source_id: number;
  query_template: string;
  parameters: ReportParameter[];
  default_row_limit: number;
  max_row_limit: number;
  is_published: boolean;
};

export type DataSource = {
  id: number;
  name: string;
  engine: "mssql" | "postgresql";
  target: string;
  allowed_schemas: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Preview = {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
};

export type CurrentUser = {
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  can_manage_reports: boolean;
  can_manage_sources: boolean;
  can_read_audit: boolean;
};

export type Execution = {
  id: number;
  report_id: number;
  report_name: string;
  actor: string | null;
  output_format: string;
  status: string;
  row_count: number | null;
  duration_ms: number | null;
  error_code: string | null;
  started_at: string;
};
