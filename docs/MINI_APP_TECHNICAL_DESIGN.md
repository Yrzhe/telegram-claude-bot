# Telegram Mini App Technical Design Document

## 1. Overview

### 1.1 Project Goal

Build a Telegram Mini App that provides each user with a web-based dashboard to:
- Manage files in their personal storage
- Monitor real-time task execution status
- View Sub Agent states and history
- Browse scheduled task history and logs

### 1.2 Technology Stack

| Layer | Technology | Reason |
|-------|------------|--------|
| Frontend | React 18 + TypeScript | Mature ecosystem, type safety |
| UI Framework | Tailwind CSS + shadcn/ui | Rapid development, consistent design |
| Telegram SDK | @twa-dev/sdk | Official Mini App integration |
| State Management | Zustand | Lightweight, simple API |
| Backend | FastAPI | Async support, auto OpenAPI docs |
| Real-time | WebSocket (FastAPI) | Native async WebSocket support |
| Deployment | Same Docker container | Simplified ops, shared data layer |

### 1.3 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram Client                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 Mini App (React SPA)                       │  │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐  │  │
│  │  │  Files  │ │  Tasks  │ │ Schedules│ │   SubAgents    │  │  │
│  │  └─────────┘ └─────────┘ └──────────┘ └────────────────┘  │  │
│  │                         │                                  │  │
│  │              WebSocket + REST API                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     VPS Docker Container                         │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │   Nginx      │    │           Application                 │   │
│  │  (Reverse    │───▶│  ┌────────────┐  ┌────────────────┐  │   │
│  │   Proxy)     │    │  │ Telegram   │  │   FastAPI      │  │   │
│  │              │    │  │ Bot        │  │   API Server   │  │   │
│  │  - /api/* ──────▶│  │ (main.py)  │  │   (api/)       │  │   │
│  │  - /ws/*  ──────▶│  │            │  │                │  │   │
│  │  - /* (static)   │  └────────────┘  └────────────────┘  │   │
│  └──────────────┘    │         │              │             │   │
│                      │         └──────┬───────┘             │   │
│                      │                ▼                     │   │
│                      │  ┌──────────────────────────────┐    │   │
│                      │  │     Shared Data Layer        │    │   │
│                      │  │  - UserManager               │    │   │
│                      │  │  - TaskManager               │    │   │
│                      │  │  - ScheduleManager           │    │   │
│                      │  │  - SessionManager            │    │   │
│                      │  └──────────────────────────────┘    │   │
│                      └──────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    /app/users/{user_id}/                  │   │
│  │  ├── data/                                                │   │
│  │  │   ├── uploads/                                         │   │
│  │  │   ├── documents/                                       │   │
│  │  │   ├── running_tasks/                                   │   │
│  │  │   ├── completed_tasks/                                 │   │
│  │  │   └── schedules/                                       │   │
│  │  └── config.json                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Authentication & Security

### 2.1 Telegram initData Validation

Telegram Mini Apps receive `initData` containing user information signed by Telegram. We must validate this signature server-side.

```python
# api/auth.py
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs
from fastapi import HTTPException, Header

def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict:
    """
    Validate Telegram Mini App initData.

    Args:
        init_data: The initData string from Telegram
        bot_token: Bot token for HMAC validation
        max_age: Maximum age of initData in seconds (default 24h)

    Returns:
        Parsed user data if valid

    Raises:
        HTTPException: If validation fails
    """
    try:
        # Parse the initData
        parsed = parse_qs(init_data)

        # Extract hash
        received_hash = parsed.get('hash', [None])[0]
        if not received_hash:
            raise HTTPException(status_code=401, detail="Missing hash")

        # Check auth_date
        auth_date = int(parsed.get('auth_date', [0])[0])
        if time.time() - auth_date > max_age:
            raise HTTPException(status_code=401, detail="initData expired")

        # Build data-check-string (sorted, excluding hash)
        data_check_parts = []
        for key in sorted(parsed.keys()):
            if key != 'hash':
                data_check_parts.append(f"{key}={parsed[key][0]}")
        data_check_string = '\n'.join(data_check_parts)

        # Compute HMAC
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256
        ).digest()

        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        # Compare hashes
        if not hmac.compare_digest(computed_hash, received_hash):
            raise HTTPException(status_code=401, detail="Invalid hash")

        # Extract user data
        user_data = json.loads(parsed.get('user', ['{}'])[0])
        return {
            "user_id": user_data.get("id"),
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "auth_date": auth_date
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Validation error: {e}")
```

### 2.2 API Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Mini App   │     │   FastAPI   │     │  Telegram   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │  window.Telegram  │                   │
       │  .WebApp.initData │                   │
       │◀──────────────────│───────────────────│
       │                   │                   │
       │  POST /api/auth   │                   │
       │  {initData: "..."}│                   │
       │──────────────────▶│                   │
       │                   │                   │
       │                   │ validate_init_data()
       │                   │──────────┐        │
       │                   │          │        │
       │                   │◀─────────┘        │
       │                   │                   │
       │  {token: "jwt"}   │                   │
       │◀──────────────────│                   │
       │                   │                   │
       │  GET /api/files   │                   │
       │  Auth: Bearer jwt │                   │
       │──────────────────▶│                   │
       │                   │                   │
       │  {files: [...]}   │                   │
       │◀──────────────────│                   │
       │                   │                   │
```

### 2.3 JWT Token Structure

```python
# Token payload
{
    "user_id": 123456789,
    "username": "john_doe",
    "exp": 1704067200,  # Expiration timestamp
    "iat": 1704063600   # Issued at timestamp
}
```

### 2.4 Security Considerations

1. **HTTPS Required**: Mini Apps must be served over HTTPS
2. **CORS Policy**: Restrict to Telegram domains
3. **Rate Limiting**: Prevent API abuse
4. **User Isolation**: Each user can only access their own data
5. **Input Validation**: Sanitize all file paths to prevent directory traversal

## 3. Backend API Design

### 3.1 Directory Structure

```
telegram bot/
├── api/
│   ├── __init__.py
│   ├── server.py           # FastAPI app initialization
│   ├── auth.py             # Authentication utilities
│   ├── dependencies.py     # Dependency injection
│   ├── websocket.py        # WebSocket manager
│   └── routes/
│       ├── __init__.py
│       ├── auth.py         # POST /api/auth
│       ├── files.py        # /api/files/*
│       ├── tasks.py        # /api/tasks/*
│       ├── schedules.py    # /api/schedules/*
│       └── subagents.py    # /api/subagents/*
```

### 3.2 API Endpoints

#### 3.2.1 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth` | Exchange initData for JWT token |
| GET | `/api/auth/me` | Get current user info |

#### 3.2.2 Files API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files in directory |
| GET | `/api/files/download/{path}` | Download a file |
| DELETE | `/api/files/{path}` | Delete a file |
| POST | `/api/files/mkdir` | Create directory |
| GET | `/api/files/storage` | Get storage quota info |

**Request/Response Examples:**

```typescript
// GET /api/files?path=/documents
{
  "path": "/documents",
  "items": [
    {
      "name": "report.pdf",
      "type": "file",
      "size": 1024000,
      "modified": "2026-02-03T10:30:00Z"
    },
    {
      "name": "images",
      "type": "directory",
      "modified": "2026-02-02T15:00:00Z"
    }
  ],
  "storage": {
    "used_bytes": 52428800,
    "quota_bytes": 5368709120,
    "used_percent": 0.98
  }
}
```

#### 3.2.3 Tasks API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all tasks (running + recent completed) |
| GET | `/api/tasks/{task_id}` | Get task details |
| POST | `/api/tasks/{task_id}/cancel` | Cancel a running task |
| GET | `/api/tasks/history` | Get completed task history |

**Response Example:**

```typescript
// GET /api/tasks
{
  "running": [
    {
      "task_id": "abc12345",
      "description": "Analyze stock data",
      "status": "running",
      "created_at": "2026-02-03T10:30:00Z",
      "progress": null
    }
  ],
  "recent_completed": [
    {
      "task_id": "def67890",
      "description": "Generate report",
      "status": "completed",
      "created_at": "2026-02-03T09:00:00Z",
      "completed_at": "2026-02-03T09:15:00Z",
      "result_preview": "Report generated successfully..."
    }
  ],
  "stats": {
    "pending": 0,
    "running": 1,
    "completed": 15,
    "failed": 2,
    "cancelled": 0
  }
}
```

#### 3.2.4 Schedules API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/schedules` | List all scheduled tasks |
| GET | `/api/schedules/{task_id}` | Get schedule details |
| GET | `/api/schedules/logs` | Get operation logs |
| GET | `/api/schedules/history` | Get execution history |

**Response Example:**

```typescript
// GET /api/schedules
{
  "timezone": "Asia/Shanghai",
  "tasks": [
    {
      "task_id": "daily_report",
      "name": "Daily Stock Report",
      "schedule_type": "daily",
      "time": "09:00",
      "enabled": true,
      "last_run": "2026-02-03T09:00:00Z",
      "run_count": 45,
      "max_runs": null,
      "next_run": "2026-02-04T09:00:00Z"
    }
  ]
}

// GET /api/schedules/logs?limit=20
{
  "logs": [
    {
      "timestamp": "2026-02-03T10:30:00Z",
      "action": "create",
      "task_id": "weekly_backup",
      "details": {
        "name": "Weekly Backup",
        "schedule_type": "weekly",
        "weekdays": [0, 4]
      }
    }
  ]
}
```

#### 3.2.5 Sub Agents API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/subagents/status` | Get Sub Agent pool status |
| GET | `/api/subagents/running` | List running Sub Agents |
| GET | `/api/subagents/{task_id}/document` | Get task document content |

**Response Example:**

```typescript
// GET /api/subagents/status
{
  "max_agents": 10,
  "active_count": 2,
  "available_slots": 8,
  "running_tasks": [
    {
      "task_id": "abc12345",
      "description": "Analyze stock data",
      "started_at": "2026-02-03T10:30:00Z",
      "elapsed_seconds": 120
    }
  ]
}
```

### 3.3 WebSocket API

#### 3.3.1 Connection

```
WS /api/ws?token={jwt_token}
```

#### 3.3.2 Message Types

**Server → Client:**

```typescript
// Task status update
{
  "type": "task_update",
  "data": {
    "task_id": "abc12345",
    "status": "completed",
    "result": "Task completed successfully"
  }
}

// New task created
{
  "type": "task_created",
  "data": {
    "task_id": "xyz98765",
    "description": "New background task"
  }
}

// Schedule executed
{
  "type": "schedule_executed",
  "data": {
    "task_id": "daily_report",
    "run_count": 46,
    "next_run": "2026-02-04T09:00:00Z"
  }
}

// Storage update
{
  "type": "storage_update",
  "data": {
    "used_bytes": 52500000,
    "quota_bytes": 5368709120
  }
}
```

**Client → Server:**

```typescript
// Subscribe to specific events
{
  "type": "subscribe",
  "events": ["task_update", "schedule_executed"]
}

// Ping (keep-alive)
{
  "type": "ping"
}
```

### 3.4 WebSocket Manager Implementation

```python
# api/websocket.py
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
import json

class WebSocketManager:
    """Manages WebSocket connections per user."""

    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]

    async def send_to_user(self, user_id: int, message: dict):
        """Send message to all connections of a user."""
        async with self._lock:
            connections = self._connections.get(user_id, set()).copy()

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                # Connection closed, will be cleaned up
                pass

    async def broadcast_task_update(self, user_id: int, task_id: str, status: str, result: str = None):
        await self.send_to_user(user_id, {
            "type": "task_update",
            "data": {
                "task_id": task_id,
                "status": status,
                "result": result
            }
        })

# Global instance
ws_manager = WebSocketManager()
```

## 4. Frontend Design

### 4.1 Directory Structure

```
webapp/
├── public/
│   └── index.html
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # Root component with routing
│   ├── api/
│   │   ├── client.ts         # API client with auth
│   │   ├── websocket.ts      # WebSocket client
│   │   └── types.ts          # API response types
│   ├── stores/
│   │   ├── auth.ts           # Auth state (Zustand)
│   │   ├── files.ts          # Files state
│   │   ├── tasks.ts          # Tasks state
│   │   └── schedules.ts      # Schedules state
│   ├── components/
│   │   ├── ui/               # shadcn/ui components
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── TabBar.tsx
│   │   │   └── Layout.tsx
│   │   ├── files/
│   │   │   ├── FileList.tsx
│   │   │   ├── FileItem.tsx
│   │   │   ├── StorageBar.tsx
│   │   │   └── FilePreview.tsx
│   │   ├── tasks/
│   │   │   ├── TaskList.tsx
│   │   │   ├── TaskCard.tsx
│   │   │   └── TaskDetail.tsx
│   │   └── schedules/
│   │       ├── ScheduleList.tsx
│   │       ├── ScheduleCard.tsx
│   │       └── ExecutionLog.tsx
│   ├── pages/
│   │   ├── FilesPage.tsx
│   │   ├── TasksPage.tsx
│   │   ├── SchedulesPage.tsx
│   │   └── SubAgentsPage.tsx
│   ├── hooks/
│   │   ├── useTelegram.ts    # Telegram SDK hooks
│   │   └── useWebSocket.ts   # WebSocket hook
│   └── styles/
│       └── globals.css
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

### 4.2 Page Designs

#### 4.2.1 Files Page

```
┌─────────────────────────────────────────┐
│ ← Back    Files           Storage: 1.2GB│
├─────────────────────────────────────────┤
│ ████████████░░░░░░░░░░░░░░  24% of 5GB  │
├─────────────────────────────────────────┤
│ 📁 /documents                           │
├─────────────────────────────────────────┤
│ 📁 analysis/                    Feb 02  │
│ 📁 uploads/                     Feb 03  │
│ 📄 report.pdf              1.2MB Feb 01 │
│ 📄 notes.txt               4KB   Jan 30 │
│ 📄 data.xlsx              256KB  Jan 28 │
│                                         │
│                                         │
├─────────────────────────────────────────┤
│  📁 Files  │  📋 Tasks  │  ⏰ Schedule  │
└─────────────────────────────────────────┘
```

#### 4.2.2 Tasks Page

```
┌─────────────────────────────────────────┐
│ ← Back        Tasks                     │
├─────────────────────────────────────────┤
│ Running (2)                             │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ 🔄 Analyze stock data               │ │
│ │ Started 2 min ago                   │ │
│ │                          [Cancel]   │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ 🔄 Generate weekly report           │ │
│ │ Started 5 min ago                   │ │
│ │                          [Cancel]   │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ Completed Today (5)                     │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ ✅ Web research: AI trends          │ │
│ │ Completed 10:30 AM                  │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│  📁 Files  │  📋 Tasks  │  ⏰ Schedule  │
└─────────────────────────────────────────┘
```

#### 4.2.3 Schedules Page

```
┌─────────────────────────────────────────┐
│ ← Back      Schedules                   │
├─────────────────────────────────────────┤
│ Active Schedules (3)                    │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ 📅 Daily Stock Report       [ON]    │ │
│ │ Every day at 09:00                  │ │
│ │ Last run: Today 09:00  (45 runs)    │ │
│ │ Next: Tomorrow 09:00                │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ 📅 Weekly Backup            [ON]    │ │
│ │ Mon, Fri at 18:00                   │ │
│ │ Last run: Feb 02  (12 runs)         │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ Execution History                       │
├─────────────────────────────────────────┤
│ • 09:00 daily_report ✅ completed       │
│ • 08:30 morning_check ✅ completed      │
│ • Yesterday 18:00 weekly_backup ✅      │
├─────────────────────────────────────────┤
│  📁 Files  │  📋 Tasks  │  ⏰ Schedule  │
└─────────────────────────────────────────┘
```

#### 4.2.4 Sub Agents Page

```
┌─────────────────────────────────────────┐
│ ← Back     Sub Agents                   │
├─────────────────────────────────────────┤
│ Agent Pool: 2/10 active                 │
│ ██░░░░░░░░  8 slots available           │
├─────────────────────────────────────────┤
│ Running Agents                          │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ 🤖 Agent #abc123                    │ │
│ │ Task: Analyze stock data            │ │
│ │ Running for: 2m 30s                 │ │
│ │ Retry: 0/10                         │ │
│ │                          [Cancel]   │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ Recent Completed                        │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ ✅ Agent #def456                    │ │
│ │ Task: Generate report               │ │
│ │ Duration: 5m 12s                    │ │
│ │ Attempts: 2/10 (passed on 2nd)      │ │
│ │                      [View Result]  │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│  📁 Files  │  📋 Tasks  │  ⏰ Schedule  │
└─────────────────────────────────────────┘
```

### 4.3 Telegram SDK Integration

```typescript
// src/hooks/useTelegram.ts
import { useEffect, useState } from 'react';

declare global {
  interface Window {
    Telegram: {
      WebApp: {
        initData: string;
        initDataUnsafe: {
          user?: {
            id: number;
            first_name: string;
            last_name?: string;
            username?: string;
          };
        };
        ready: () => void;
        expand: () => void;
        close: () => void;
        MainButton: {
          text: string;
          show: () => void;
          hide: () => void;
          onClick: (callback: () => void) => void;
        };
        BackButton: {
          show: () => void;
          hide: () => void;
          onClick: (callback: () => void) => void;
        };
        themeParams: {
          bg_color: string;
          text_color: string;
          hint_color: string;
          button_color: string;
          button_text_color: string;
        };
      };
    };
  }
}

export function useTelegram() {
  const [isReady, setIsReady] = useState(false);
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    if (tg) {
      tg.ready();
      tg.expand();
      setIsReady(true);
    }
  }, []);

  return {
    tg,
    isReady,
    user: tg?.initDataUnsafe?.user,
    initData: tg?.initData,
    themeParams: tg?.themeParams,
  };
}
```

### 4.4 API Client

```typescript
// src/api/client.ts
import { useAuthStore } from '../stores/auth';

const API_BASE = '/api';

class ApiClient {
  private getHeaders(): HeadersInit {
    const token = useAuthStore.getState().token;
    return {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
    };
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...options.headers,
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
  }

  // Auth
  async authenticate(initData: string) {
    return this.request<{ token: string }>('/auth', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
    });
  }

  // Files
  async listFiles(path: string = '/') {
    return this.request<FileListResponse>(`/files?path=${encodeURIComponent(path)}`);
  }

  async deleteFile(path: string) {
    return this.request(`/files/${encodeURIComponent(path)}`, { method: 'DELETE' });
  }

  async getStorageInfo() {
    return this.request<StorageInfo>('/files/storage');
  }

  // Tasks
  async listTasks() {
    return this.request<TaskListResponse>('/tasks');
  }

  async cancelTask(taskId: string) {
    return this.request(`/tasks/${taskId}/cancel`, { method: 'POST' });
  }

  // Schedules
  async listSchedules() {
    return this.request<ScheduleListResponse>('/schedules');
  }

  async getScheduleLogs(limit: number = 20) {
    return this.request<ScheduleLogsResponse>(`/schedules/logs?limit=${limit}`);
  }

  // Sub Agents
  async getSubAgentStatus() {
    return this.request<SubAgentStatusResponse>('/subagents/status');
  }
}

export const api = new ApiClient();
```

### 4.5 WebSocket Client

```typescript
// src/api/websocket.ts
import { useAuthStore } from '../stores/auth';

type MessageHandler = (data: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  connect() {
    const token = useAuthStore.getState().token;
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws?token=${token}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const handlers = this.handlers.get(message.type);
        if (handlers) {
          handlers.forEach((handler) => handler(message.data));
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
    }
  }

  subscribe(eventType: string, handler: MessageHandler) {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);

    return () => {
      this.handlers.get(eventType)?.delete(handler);
    };
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}

export const wsClient = new WebSocketClient();
```

## 5. Integration with Existing Bot

### 5.1 Shared Manager Instances

The API server and bot share the same manager instances:

```python
# main.py (updated)
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application

from bot import setup_handlers
from bot.user import UserManager
from bot.session import SessionManager
from bot.schedule import ScheduleManager
from bot.agent.task_manager import TaskManager
from api.server import create_api_app
from api.websocket import ws_manager

# Shared instances
user_manager: UserManager = None
session_manager: SessionManager = None
schedule_manager: ScheduleManager = None
task_managers: dict = {}  # user_id -> TaskManager

def get_or_create_task_manager(user_id: int) -> TaskManager:
    """Get or create TaskManager for a user."""
    if user_id not in task_managers:
        user_dir = user_manager.get_user_directory(user_id)
        task_managers[user_id] = TaskManager(
            user_id=user_id,
            working_directory=user_dir,
            on_task_complete=lambda tid, desc, result:
                asyncio.create_task(ws_manager.broadcast_task_update(user_id, tid, "completed", result))
        )
    return task_managers[user_id]

async def main():
    global user_manager, session_manager, schedule_manager

    # Load config
    config = load_config()

    # Initialize shared managers
    user_manager = UserManager(config["users_data_directory"])
    session_manager = SessionManager(config["sessions_file"])
    schedule_manager = ScheduleManager(config["users_data_directory"])

    # Create FastAPI app with shared managers
    api_app = create_api_app(
        user_manager=user_manager,
        session_manager=session_manager,
        schedule_manager=schedule_manager,
        get_task_manager=get_or_create_task_manager,
        bot_token=config["bot_token"]
    )

    # Create Telegram bot
    bot_app = Application.builder().token(config["bot_token"]).build()
    setup_handlers(bot_app, user_manager, session_manager, schedule_manager)

    # Run both servers
    # ... (see section 5.2)
```

### 5.2 Running Both Servers

```python
# main.py (continued)
import uvicorn
from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig

async def main():
    # ... (initialization code from above)

    # Configure Hypercorn for FastAPI
    hypercorn_config = HypercornConfig()
    hypercorn_config.bind = ["127.0.0.1:8000"]

    # Start both servers concurrently
    async with bot_app:
        await bot_app.start()

        # Start the API server
        api_task = asyncio.create_task(
            serve(api_app, hypercorn_config)
        )

        # Start the bot polling
        await bot_app.updater.start_polling()

        # Wait forever
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
```

### 5.3 WebSocket Event Broadcasting

When tasks complete or schedules execute, broadcast to connected clients:

```python
# bot/agent/task_manager.py (updated)
from api.websocket import ws_manager

class TaskManager:
    async def _on_task_complete_internal(self, task_id: str, description: str, result: str):
        """Internal callback when task completes."""
        # Broadcast to WebSocket clients
        await ws_manager.broadcast_task_update(
            self.user_id,
            task_id,
            "completed",
            result
        )

        # Call original callback if set
        if self._on_task_complete:
            await self._on_task_complete(task_id, description, result)
```

## 6. Deployment Configuration

### 6.1 Updated Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build frontend
COPY webapp/package*.json webapp/
RUN cd webapp && npm install

COPY webapp/ webapp/
RUN cd webapp && npm run build

# Copy backend code
COPY . .

# Copy frontend build to nginx
RUN cp -r webapp/dist/* /var/www/html/

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Expose port
EXPOSE 80

# Start script
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
```

### 6.2 Nginx Configuration

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    server {
        listen 80;
        server_name _;

        # Frontend static files
        location / {
            root /var/www/html;
            try_files $uri $uri/ /index.html;
        }

        # API proxy
        location /api/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # WebSocket support
            proxy_read_timeout 86400;
        }
    }
}
```

### 6.3 Docker Entrypoint

```bash
#!/bin/bash
# docker-entrypoint.sh

# Start nginx in background
nginx

# Start the main application (bot + API)
exec python main.py
```

### 6.4 Updated docker-compose.yml

```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: telegram-bot
    restart: unless-stopped
    ports:
      - "443:80"  # HTTPS termination handled by external proxy or certbot
    volumes:
      - ./users:/app/users
      - ./config.json:/app/config.json:ro
      - ./sessions.json:/app/sessions.json
    environment:
      - TZ=Asia/Shanghai
```

## 7. Bot Integration

### 7.1 Add Mini App Button to Bot

```python
# bot/handlers.py (updated)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with Mini App button."""
    user = update.effective_user

    # Mini App URL (must be HTTPS)
    webapp_url = "https://your-domain.com/"

    keyboard = [
        [InlineKeyboardButton(
            text="📱 Open Dashboard",
            web_app=WebAppInfo(url=webapp_url)
        )],
        [InlineKeyboardButton(
            text="📁 Files",
            web_app=WebAppInfo(url=f"{webapp_url}#/files")
        )],
        [InlineKeyboardButton(
            text="📋 Tasks",
            web_app=WebAppInfo(url=f"{webapp_url}#/tasks")
        )],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Hello {user.first_name}! 👋\n\n"
        "I'm your AI assistant with file management capabilities.\n\n"
        "Use the buttons below to open the dashboard:",
        reply_markup=reply_markup
    )
```

### 7.2 Menu Button Configuration

```python
# Set the menu button to open Mini App
from telegram import MenuButtonWebApp, WebAppInfo

async def setup_menu_button(bot, webapp_url: str):
    """Configure the menu button to open Mini App."""
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Dashboard",
            web_app=WebAppInfo(url=webapp_url)
        )
    )
```

## 8. Development Workflow

### 8.1 Local Development

```bash
# Terminal 1: Run backend
cd "telegram bot"
python main.py

# Terminal 2: Run frontend dev server
cd webapp
npm run dev

# Frontend dev server proxies /api to backend
```

### 8.2 Frontend Vite Config

```typescript
// webapp/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
```

### 8.3 Testing

For local testing without Telegram:

```typescript
// src/hooks/useTelegram.ts (development mode)
export function useTelegram() {
  const isDev = import.meta.env.DEV;

  if (isDev && !window.Telegram?.WebApp) {
    // Mock Telegram WebApp for development
    return {
      isReady: true,
      user: { id: 123456789, first_name: 'Dev', username: 'dev_user' },
      initData: 'mock_init_data_for_dev',
      themeParams: {
        bg_color: '#ffffff',
        text_color: '#000000',
        hint_color: '#999999',
        button_color: '#3390ec',
        button_text_color: '#ffffff',
      },
    };
  }

  // ... production code
}
```

## 9. Security Checklist

- [ ] HTTPS enforced for Mini App URL
- [ ] initData validation on every API request
- [ ] JWT tokens with short expiration (1 hour)
- [ ] Rate limiting on API endpoints
- [ ] File path sanitization (prevent directory traversal)
- [ ] User isolation (each user accesses only their data)
- [ ] CORS restricted to Telegram domains
- [ ] Input validation on all endpoints
- [ ] Secure WebSocket connections (WSS)
- [ ] No sensitive data in frontend logs

## 10. Future Enhancements

1. **File Upload via Mini App**: Allow uploading files directly through the web interface
2. **Task Creation**: Create new tasks from the Mini App
3. **Schedule Management**: Create/edit/delete schedules from the UI
4. **Real-time Chat**: View chat history with the bot
5. **Theme Support**: Match Telegram's dark/light mode
6. **Offline Support**: PWA with service worker for offline access
7. **Push Notifications**: Notify when tasks complete (via Telegram)

## 11. Implementation Progress

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1 | Backend API + Auth | ✅ **DONE** |
| Phase 2 | Frontend skeleton + Files page | ✅ **DONE** |
| Phase 3 | Tasks + Sub Agents pages | ✅ **DONE** |
| Phase 4 | Schedules page + WebSocket integration | ✅ **DONE** |
| Phase 5 | Bot integration + Testing | ✅ **DONE** |
| Phase 6 | Deployment (Nginx, Docker) + Polish | ✅ **DONE** |

### Phase 1 - Backend API + Auth ✅ COMPLETED (2026-02-03)

**Implemented:**
- `api/auth.py` - Telegram initData HMAC-SHA256 validation + JWT token
- `api/websocket.py` - WebSocket connection manager with user isolation
- `api/dependencies.py` - FastAPI dependency injection for shared managers
- `api/server.py` - FastAPI app factory with CORS, routes, WebSocket
- `api/routes/auth.py` - POST /api/auth, GET /api/auth/me
- `api/routes/files.py` - File listing, download, delete, mkdir, storage
- `api/routes/tasks.py` - Task list, detail, cancel, history
- `api/routes/schedules.py` - Schedule list, detail, operation logs
- `api/routes/subagents.py` - Sub Agent status, running list, history
- `main.py` - Async startup integrating bot + API server
- `requirements.txt` - Added fastapi, uvicorn, python-jose dependencies
- `config.example.json` - Added mini_app_api_* config options

### Phase 2 - Frontend Skeleton + Files Page ✅ COMPLETED (2026-02-03)

**Implemented:**
- Initialized React + TypeScript + Vite project in `webapp/`
- Configured Tailwind CSS v4 with Telegram theme variables
- Implemented `useTelegram` hook with SDK integration and dev mode
- Created API client with JWT authentication
- Created WebSocket client with auto-reconnect
- Built Zustand stores for auth, files, tasks, schedules, subagents
- Implemented Layout with TabBar navigation (4 tabs)
- Implemented Files page with StorageBar and FileList
- File icons, delete, download, directory navigation

### Phase 3 - Tasks + Sub Agents Pages ✅ COMPLETED (2026-02-03)

**Implemented:**
- Tasks page with running/completed sections
- TaskCard component with status indicators
- Cancel task functionality
- SubAgents page with pool status bar
- Agent detail view with elapsed time and retry count
- Recent completed agents history

### Phase 4 - Schedules Page + WebSocket ✅ COMPLETED (2026-02-03)

**Implemented:**
- Schedules page with active/inactive sections
- ScheduleCard with type indicators and next run
- ExecutionLog component for history
- WebSocket hook with subscriptions to all event types
- Real-time updates for tasks, schedules, storage

### Phase 5 - Bot Integration + Testing ✅ COMPLETED (2026-02-03)

**Implemented:**
- Added `mini_app_url` config option
- Added InlineKeyboardButton with WebAppInfo to /start command
- Mini App button appears when `mini_app_url` is configured
- Updated main.py to pass mini_app_url to handlers

### Phase 6 - Deployment + Polish ✅ COMPLETED (2026-02-03)

**Implemented:**
- Created `nginx.conf` with reverse proxy configuration
- Updated `Dockerfile` to build frontend and include nginx
- Updated `docker-compose.yml` with port 8080:80 mapping
- Updated `entrypoint.sh` to start nginx before bot
- Added health check endpoint at `/health`
- Configured gzip compression and static asset caching

---

*Document Version: 1.1*
*Created: 2026-02-03*
*Last Updated: 2026-02-03 (Phase 1 completed)*
