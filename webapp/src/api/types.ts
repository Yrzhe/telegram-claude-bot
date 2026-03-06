// API Response Types

export interface User {
  user_id: number
  username?: string
  first_name: string
  last_name?: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface StorageInfo {
  used_bytes: number
  quota_bytes: number
  used_percent: number
}

export interface FileItem {
  name: string
  type: 'file' | 'directory'
  size?: number
  modified: string
}

export interface FileListResponse {
  path: string
  items: FileItem[]
  storage: StorageInfo
}

export interface TaskItem {
  task_id: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  completed_at?: string
  result_preview?: string
  progress?: number
}

export interface TaskListResponse {
  running: TaskItem[]
  recent_completed: TaskItem[]
  stats: {
    pending: number
    running: number
    completed: number
    failed: number
    cancelled: number
  }
}

export interface ScheduleItem {
  task_id: string
  name: string
  schedule_type: 'once' | 'daily' | 'weekly' | 'interval'
  time?: string
  weekdays?: number[]
  interval_minutes?: number
  enabled: boolean
  last_run?: string
  run_count: number
  max_runs?: number
  next_run?: string
}

export interface ScheduleListResponse {
  timezone: string
  tasks: ScheduleItem[]
}

export interface ScheduleLog {
  timestamp: string
  action: 'create' | 'update' | 'delete' | 'execute' | 'enable' | 'disable'
  task_id: string
  details?: Record<string, unknown>
}

export interface ScheduleLogsResponse {
  logs: ScheduleLog[]
}

export interface SubAgentTask {
  task_id: string
  description: string
  started_at: string
  elapsed_seconds: number
  retry_count?: number
  max_retries?: number
}

export interface SubAgentStatusResponse {
  max_agents: number
  active_count: number
  available_slots: number
  running_tasks: SubAgentTask[]
}

export interface SubAgentHistoryItem {
  task_id: string
  description: string
  status: 'completed' | 'failed' | 'cancelled'
  created_at: string
  duration_seconds?: number
  result_preview?: string
}

// Skills
export interface SkillItem {
  name: string
  description: string
}

export interface SkillListResponse {
  skills: SkillItem[]
  count: number
}

export interface SkillDetailResponse {
  name: string
  description: string
  content: string
  files: string[]
}

// WebSocket Message Types
export interface WSMessage {
  type: 'task_update' | 'task_created' | 'schedule_executed' | 'storage_update' | 'cleanup_update'
  data: unknown
}

export interface TaskUpdateData {
  task_id: string
  status: string
  result?: string
}

export interface StorageUpdateData {
  used_bytes: number
  quota_bytes: number
}

// Cleanup
export interface CleanupAction {
  action: 'delete' | 'archive' | 'move'
  path: string
  target?: string
  reason: string
  size_bytes: number
  item_count: number
}

export interface CleanupPlan {
  plan_id: string
  actions: CleanupAction[]
  total_size_bytes: number
  total_items: number
  summary: string
  created_at: string
  error?: string
}

export interface CleanupRulesResponse {
  content: string
  modified_at?: string
}

export interface CleanupResult {
  success_count: number
  fail_count: number
  freed_bytes: number
  errors?: string[]
}

export interface CleanupStatusResponse {
  status: 'idle' | 'planning' | 'ready' | 'executing' | 'completed' | 'failed'
  plan?: CleanupPlan
  result?: CleanupResult
  error?: string
}
