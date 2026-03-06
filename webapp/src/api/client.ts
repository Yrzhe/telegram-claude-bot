import type {
  AuthResponse,
  FileListResponse,
  TaskListResponse,
  TaskItem,
  ScheduleListResponse,
  ScheduleLogsResponse,
  SubAgentStatusResponse,
  SubAgentHistoryItem,
  StorageInfo,
  SkillListResponse,
  SkillDetailResponse,
  CleanupRulesResponse,
  CleanupStatusResponse,
} from './types'

const API_BASE = '/api'

class ApiClient {
  private token: string | null = null

  setToken(token: string | null) {
    this.token = token
  }

  private getHeaders(): HeadersInit {
    return {
      'Content-Type': 'application/json',
      ...(this.token && { Authorization: `Bearer ${this.token}` }),
    }
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...options.headers,
      },
    })

    if (!response.ok) {
      if (response.status === 401) {
        this.token = null
        throw new Error('Session expired. Please reopen the app.')
      }
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `API Error: ${response.status}`)
    }

    return response.json()
  }

  // Auth
  async authenticate(initData: string): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
    })
  }

  async getCurrentUser() {
    return this.request<{ user: AuthResponse['user'] }>('/auth/me')
  }

  // Files
  async listFiles(path: string = '/'): Promise<FileListResponse> {
    return this.request<FileListResponse>(`/files?path=${encodeURIComponent(path)}`)
  }

  async deleteFile(path: string): Promise<{ success: boolean }> {
    return this.request(`/files/${encodeURIComponent(path)}`, { method: 'DELETE' })
  }

  async createDirectory(path: string): Promise<{ success: boolean }> {
    return this.request('/files/mkdir', {
      method: 'POST',
      body: JSON.stringify({ path }),
    })
  }

  async getStorageInfo(): Promise<StorageInfo> {
    return this.request<StorageInfo>('/files/storage')
  }

  getDownloadUrl(path: string): string {
    return `${API_BASE}/files/download/${encodeURIComponent(path)}?token=${this.token}`
  }

  async batchDelete(paths: string[]): Promise<{ success: boolean }> {
    return this.request('/files/batch/delete', {
      method: 'POST',
      body: JSON.stringify({ paths }),
    })
  }

  async batchDownload(paths: string[]): Promise<{ success: boolean }> {
    return this.request('/files/batch/download', {
      method: 'POST',
      body: JSON.stringify({ paths }),
    })
  }

  // Tasks
  async listTasks(): Promise<TaskListResponse> {
    return this.request<TaskListResponse>('/tasks')
  }

  async getTask(taskId: string): Promise<TaskItem> {
    return this.request<TaskItem>(`/tasks/${taskId}`)
  }

  async cancelTask(taskId: string): Promise<{ success: boolean }> {
    return this.request(`/tasks/${taskId}/cancel`, { method: 'POST' })
  }

  async getTaskHistory(limit: number = 50): Promise<{ tasks: TaskItem[] }> {
    return this.request(`/tasks/history?limit=${limit}`)
  }

  // Schedules
  async listSchedules(): Promise<ScheduleListResponse> {
    return this.request<ScheduleListResponse>('/schedules')
  }

  async getSchedule(taskId: string): Promise<ScheduleListResponse['tasks'][0]> {
    return this.request(`/schedules/${taskId}`)
  }

  async getScheduleLogs(limit: number = 20): Promise<ScheduleLogsResponse> {
    return this.request<ScheduleLogsResponse>(`/schedules/logs?limit=${limit}`)
  }

  async getScheduleHistory(limit: number = 50) {
    return this.request(`/schedules/history?limit=${limit}`)
  }

  // Sub Agents
  async getSubAgentStatus(): Promise<SubAgentStatusResponse> {
    return this.request<SubAgentStatusResponse>('/subagents/status')
  }

  async getRunningSubAgents(): Promise<{ tasks: SubAgentStatusResponse['running_tasks'] }> {
    return this.request('/subagents/running')
  }

  async getSubAgentHistory(limit: number = 20): Promise<{ tasks: SubAgentHistoryItem[] }> {
    return this.request(`/subagents/history?limit=${limit}`)
  }

  async getSubAgentDocument(taskId: string): Promise<{ content: string }> {
    return this.request(`/subagents/${taskId}/document`)
  }

  // Skills
  async getSkills(): Promise<SkillListResponse> {
    return this.request<SkillListResponse>('/skills')
  }

  async getSkill(name: string): Promise<SkillDetailResponse> {
    return this.request<SkillDetailResponse>(`/skills/${encodeURIComponent(name)}`)
  }

  async deleteSkill(name: string): Promise<{ success: boolean }> {
    return this.request(`/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })
  }

  // Cleanup
  async getCleanupRules(): Promise<CleanupRulesResponse> {
    return this.request<CleanupRulesResponse>('/cleanup/rules')
  }

  async updateCleanupRules(content: string): Promise<{ success: boolean }> {
    return this.request('/cleanup/rules', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    })
  }

  async generateCleanupPlan(feedback?: string): Promise<CleanupStatusResponse> {
    return this.request<CleanupStatusResponse>('/cleanup/plan', {
      method: 'POST',
      body: JSON.stringify({ feedback: feedback || null }),
    })
  }

  async executeCleanup(planId: string): Promise<CleanupStatusResponse> {
    return this.request<CleanupStatusResponse>('/cleanup/execute', {
      method: 'POST',
      body: JSON.stringify({ plan_id: planId }),
    })
  }

  async getCleanupStatus(): Promise<CleanupStatusResponse> {
    return this.request<CleanupStatusResponse>('/cleanup/status')
  }

  async cancelCleanup(): Promise<{ success: boolean }> {
    return this.request('/cleanup/cancel', { method: 'POST' })
  }
}

export const api = new ApiClient()
