export interface HealthStatus {
  status: "ok" | "degraded" | "unhealthy";
  app: string;
  version: string;
  database: string;
  kane_cli_installed: boolean;
  kane_cli_executable?: boolean;
  kane_cli_authenticated?: boolean;
  kane_auth_detail?: string | null;
  agy_cli_installed: boolean;
  agy_cli_executable?: boolean;
  ide_handoff_available?: boolean;
  execution_engine_available?: boolean;
  execution_mode?: string;
  timestamp: string;
}

export interface VerificationStep {
  id: string;
  run_id: string;
  step_index: number;
  status: "running" | "done" | "failed";
  remark: string;
  screenshot_path?: string | null;
  annotated_screenshot_path?: string | null;
  error_message?: string | null;
  duration_ms?: number | null;
  created_at: string;
}

export interface VerificationEvent {
  id: string;
  run_id: string;
  event_type: string;
  step_number?: number | null;
  status?: string | null;
  description?: string | null;
  raw_event?: Record<string, unknown> | null;
  created_at: string;
}

export interface EvidenceArtifact {
  step_index?: number | null;
  artifact_type: "screenshot" | "annotated_screenshot" | "failure_yaml" | "console_log" | "network_har" | string;
  filename: string;
  relative_path: string;
  file_size_bytes: number;
}

export interface EvidenceResponse {
  run_id: string;
  pack_path?: string | null;
  execution_id?: string | null;
  extracted_dir?: string | null;
  has_evidence: boolean;
  has_failure_yaml: boolean;
  failure_details?: Record<string, unknown> | null;
  artifacts: EvidenceArtifact[];
  console_errors_count: number;
  network_failures_count: number;
}

export interface RepairSummary {
  id: string;
  run_id: string;
  project_name?: string | null;
  attempt_number: number;
  status: RepairStatus;
  execution_mode: "ide_mediated" | "programmatic" | string;
  diagnosis?: string | null;
  patch_diff?: string | null;
  files_modified?: string[] | null;
  git_commit_before?: string | null;
  git_commit_after?: string | null;
  retest_run_id?: string | null;
  retest_passed: boolean;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  approved_diff_hash?: string | null;
  approval_decision?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface RepairPacket {
  run_id: string;
  kane_session_id?: string | null;
  target_url: string;
  objective: string;
  failed_step?: number | null;
  failure_message?: string | null;
  failure_yaml?: Record<string, unknown> | null;
  screenshot_paths: string[];
  console_errors: Record<string, unknown>[];
  network_errors: Record<string, unknown>[];
  project_dir: string;
  relevant_files: string[];
  git_commit_before?: string | null;
  execution_mode: string;
  created_at: string;
}

export interface RepairEvent {
  id: string;
  repair_id: string;
  from_state?: string | null;
  to_state: string;
  description?: string | null;
  raw_payload?: Record<string, unknown> | null;
  created_at: string;
}

export interface RepairDetail extends RepairSummary {
  failing_step_index?: number | null;
  files_modified?: string[] | null;
  patch_diff?: string | null;
  repair_packet?: RepairPacket | null;
  prompt_markdown?: string | null;
  job_directory?: string | null;
  failure_notes?: string | null;
  events: RepairEvent[];
}

export type RepairStatus =
  | "CREATED"
  | "JOB_PUBLISHED"
  | "AWAITING_AGENT"
  | "AGENT_RESPONSE_RECEIVED"
  | "AWAITING_APPROVAL"
  | "APPLYING"
  | "VALIDATING"
  | "RETESTING"
  | "VERIFIED"
  | "REJECTED"
  | "UNRESOLVED"
  | "FAILED"
  | "CANCELLED";

export type RunStatus =
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "incomplete"
  | "cancelled"
  | "error"
  | "verified";

export interface VerificationRun {
  id: string;
  project_id?: string | null;
  project_name?: string | null;
  title: string;
  objective: string;
  target_url: string;
  status: RunStatus;
  mode: string;
  kane_session_id?: string | null;
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  exit_code?: number | null;
  repaired: boolean;
  repair_attempts: number;
  created_at: string;
  completed_at?: string | null;
  execution_id?: string | null;
  evidence_pack_path?: string | null;
  failure_reason?: string | null;
  verification_proof?: string | null;
  steps?: VerificationStep[];
  repairs?: RepairSummary[];
  events_count?: number;
}

export interface PaginatedRuns {
  items: VerificationRun[];
  total: number;
  limit: number;
  offset: number;
}

export interface Project {
  id: string;
  name: string;
  target_url: string;
  repo_path?: string | null;
  framework: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OverviewStats {
  total_runs: number;
  passed_runs: number;
  failed_runs: number;
  verified_runs?: number;
  running_runs: number;
  cancelled_or_incomplete_runs: number;
  total_repairs: number;
  repairs_verified: number;
  repairs_awaiting_approval: number;
  repairs_in_progress: number;
  total_projects: number;
  recent_runs: VerificationRun[];
  recent_repairs: RepairSummary[];
}

export interface RevenueGuardStatus {
  enabled: boolean;
  interval_seconds: number;
  interval_label: string;
  target_url: string;
  objective: string;
  state: "running" | "alarm" | "active" | "paused";
  last_status: "healthy" | "alarm" | "running" | "idle";
  seconds_until_next: number;
  last_probe_iso?: string | null;
  next_probe_iso?: string | null;
  last_run_id?: string | null;
  total_probes: number;
  passed_probes: number;
  failed_probes: number;
  revenue_protected: number;
  revenue_at_risk: number;
  recent_alerts: Array<{
    timestamp: string;
    run_id: string;
    reason: string;
    revenue_risk: number;
  }>;
}
