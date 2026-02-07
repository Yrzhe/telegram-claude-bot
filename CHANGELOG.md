# Changelog

All notable changes are documented in this file. Newest changes at the top.

---

## [2026-02-07] Memory Agent: Automatic Memory Loading & Extraction

### Problem
- Main Agent doesn't proactively search or save memories during conversations
- User preferences and interests not automatically loaded at conversation start
- Memories only extracted when user manually runs `/new` command
- Agent "forgets" to use memory tools even though prompted to do so

### Solution: Memory Agent Architecture
Implemented a separate "Memory Agent" that handles memory operations automatically:

1. **Pre-conversation Memory Loading** (in `get_agent_for_user()`):
   - Automatically searches and loads relevant memories when creating agent
   - Loads: user preferences, current interests, active goals/projects, career context
   - Injects loaded memories into system prompt context
   - Main Agent sees these memories without needing to call memory tools

2. **Post-conversation Memory Extraction** (in `_auto_archive_on_session_expired()`):
   - When session expires, automatically runs `run_memory_analysis()`
   - Uses Claude to analyze conversation and extract missed memories
   - Silently saves important info (preferences, interests, goals) for future use
   - No longer requires user to manually `/new` to trigger memory extraction

### How It Works
```
[User sends message]
       ↓
[Memory Agent: Load relevant memories into context]
       ↓
[Main Agent: Process message with memory context]
       ↓
[Session expires/ends]
       ↓
[Memory Agent: Analyze conversation, extract & save memories]
```

### Benefits
- User preferences are always applied (tone, style, interests)
- Important discussions are automatically remembered
- Main Agent can focus on conversation without memory management burden
- Memories accumulate over time, improving personalization

### Modified Files
- `bot/handlers.py` - Added memory loading in `get_agent_for_user()` and memory extraction in `_auto_archive_on_session_expired()`

---

## [2026-02-07] Proactive Context Loading & Improved Search Behavior

### Problem 1: Context Loss After Time Gap
- User replies after a delay (e.g., 10+ minutes) but agent loses conversation context
- Claude API session might be stale internally even though our session ID is valid
- Previously context was only loaded during explicit session failure retry

### Problem 2: Passive Search Behavior
- When user asks to search for something, agent only searches memory/chat history
- Agent gives up after local search fails instead of using web search
- Agent doesn't proactively delegate complex research to sub-agents

### Fix 1: Proactive Context Loading
- Modified `bot/handlers.py` to always check time since last message
- If >10 minutes elapsed, automatically include recent chat history in message
- Applied to all 4 message handlers: text, voice, image, and document
- Uses last 6000 chars of chat log to preserve context without token overflow
- Logs when context is proactively included for debugging

### Fix 2: Proactive Search Instructions
- Added new "Proactive Search Behavior" section to `prompts/rules.md`
- Instructs agent to try multiple search methods (memory → chat history → web search)
- Provides example of correct vs wrong behavior when searching
- Emphasizes using web search when local search fails
- Recommends delegating complex research to sub-agents

### Modified Files
- `bot/handlers.py` - Added proactive context loading to all handlers
- `prompts/rules.md` - Added proactive search behavior instructions

---

## [2026-02-07] Fix Silent Session Resume Failure

### Problem
- User sent messages but got no response
- Logs showed `turns=0, tokens=0, cost=$0.0000` and `error: None`
- Session resume was failing silently without triggering retry
- When retry did happen, previous conversation context was lost

### Root Cause
- Session expired on server but SDK returned `is_error=True` with `error_message=None`
- Existing check only looked for "No conversation found" in error message
- When error_message is None, the retry logic was not triggered
- Retry logic didn't load previous chat history as context

### Fix
- Modified session failure detection in `bot/handlers.py`
- Now also checks for `is_error=True AND num_turns=0 AND resume_session_id exists`
- **NEW**: When retrying, loads previous chat history from `chat_logs/` as context
- Context limited to last 8000 chars to avoid token overflow
- Applied to all 3 message handlers: text, voice, and image

---

## [2026-02-05] Fix Scheduled Task Missing Context

### Problem
- Scheduled tasks sent generic messages instead of specific task content
- When user asked follow-up questions, Bot said "we never discussed this"
- Example: SEO Skills reminder didn't include the specific npx commands

### Root Cause
- `sub_system_prompt` ended with "Task instructions:" but prompt content was not appended
- Sub Agent received prompt as user message but system prompt was incomplete
- Agent generated generic response without knowing specific task details

### Fix
- Modified `main.py` `execute_scheduled_task()` to include `{prompt}` in system prompt
- Added rule to always include specific details (commands, links) in reminder responses

---

## [2026-02-04] Fix Chat History Search to Include Recent Logs

### Problem
- `chat_history_search` tool only searched archived summaries in `chat_summaries/`
- Recent conversations in `chat_logs/` were not searchable
- Users couldn't find conversations from the past few days (since last `/new` command)

### Root Cause
- Archiving only happens when user runs `/new` or session expires
- If user stays active, conversations remain in `chat_logs/` indefinitely
- Search tool was not looking at `chat_logs/` directory

### Changes Made

**Modified `bot/agent/tools.py` - `chat_history_search` function**
- Now searches both `chat_logs/` (recent) and `chat_summaries/` (archived)
- Results sorted by modification time (newest first)
- Each result labeled as `[Recent]` or `[Archived]`
- Combined results up to the specified limit

---

## [2026-02-04] Fix Data Directory Paths and Remove Tasks Page

### Problems Fixed
1. Memory and task files were being saved to wrong `data/data/` subdirectory
2. Mini app had redundant Tasks page that duplicated Agents page functionality
3. Two separate `memories.json` files existed due to path bug

### Changes Made

**1. Fixed MemoryManager path (`bot/memory/manager.py`)**
- `user_data_dir` parameter is already the `data/` directory
- Changed from `user_data_dir / "data" / "memories.json"` to `user_data_dir / "memories.json"`
- Merged 10 memories from both files into single correct location

**2. Fixed TaskManager paths (`bot/agent/task_manager.py`)**
- Fixed `running_tasks`, `completed_tasks`, and `review_logs` directories
- Now correctly placed in `users/{id}/data/` instead of `users/{id}/data/data/`

**3. Removed Tasks page from Mini App**
- Removed from TabBar (`webapp/src/components/layout/TabBar.tsx`)
- Removed route from App.tsx
- Tasks functionality already covered by Agents page

**4. Cleaned up directory structure**
- Removed erroneous `data/data/` directory
- Migrated task files to correct locations

### Files Modified
- `bot/memory/manager.py` - Fixed memories file path
- `bot/agent/task_manager.py` - Fixed task directories paths
- `webapp/src/components/layout/TabBar.tsx` - Removed Tasks tab
- `webapp/src/App.tsx` - Removed Tasks route

---

## [2026-02-04] Enhanced Chat History System - Search, Auto-Archive, and Context Loading

### Problem
1. Agent couldn't search past conversation summaries - only memories
2. When session expired, conversations were lost without summary
3. Agent didn't have context from previous conversations

### Changes Made

**1. New `chat_history_search` tool (`bot/agent/tools.py`)**
- Agent can now search through `chat_summaries/` directory
- Use when user asks "remember what we discussed?" or "我们之前讨论的..."
- Returns matched conversation summaries with dates and previews

**2. Auto-archive on session expiry (`bot/handlers.py`)**
- New `_auto_archive_on_session_expired()` function
- When Claude SDK returns "No conversation found" error:
  - First: Generate summary of current chat log
  - Then: Archive to `chat_summaries/` directory
  - Finally: Clear session and retry
- No more lost conversations when sessions expire

**3. Load recent summaries on agent creation (`bot/handlers.py`)**
- In `get_agent_for_user()`, now loads last 3 chat summaries
- Summaries are added to agent's context_summary
- Agent starts each conversation with awareness of recent history

**4. Added `chat_history_search` to allowed_tools (`bot/agent/client.py`)**

### Files Modified
- `bot/agent/tools.py`: Added `chat_history_search` tool (~100 lines)
- `bot/agent/client.py`: Added tool to allowed_tools list
- `bot/handlers.py`:
  - Added `_auto_archive_on_session_expired()` function
  - Modified `get_agent_for_user()` to load recent summaries
  - Modified 6 session expiry handlers to call auto-archive first

### Expected Behavior After Fix
- User: "我们之前讨论过什么?" → Agent uses `chat_history_search` to find past conversations
- Session expires → Summary auto-generated and saved before retry
- New conversation starts → Agent already knows about recent conversations

---

## [2026-02-04] Fix Memory System - Missing Tools + Discussion Topic Storage

### Problem
1. Agent was not saving discussion topics (e.g., "X agent" project idea) to memory
2. Some memory tools were missing from allowed_tools list
3. Agent didn't remember meaningful conversations from earlier in the day

### Root Cause Analysis
1. `allowed_tools` in `client.py` was missing: `memory_save_with_supersede`, `memory_update`, `memory_stats`
2. `prompts/memory.md` only emphasized saving "user preferences" but not "discussion topics/ideas/projects"
3. Agent didn't recognize that project discussions should be saved as memories

### Changes Made

**1. Added missing memory tools to `bot/agent/client.py`:**
- `mcp__telegram__memory_save_with_supersede`
- `mcp__telegram__memory_update`
- `mcp__telegram__memory_stats`

**2. Enhanced `prompts/memory.md` with new Rule 3:**
- "ALWAYS Save Discussion Topics & Ideas"
- Added table of what counts as "meaningful discussion" (projects, technical discussions, plans, brainstorming)
- Added example showing X/Twitter agent discussion being saved
- Emphasized: "Next time user asks 'remember what we discussed?' and you have no idea" as WRONG behavior

### Files Modified
- `bot/agent/client.py`: Added 3 missing memory tools to allowed_tools
- `prompts/memory.md`: Added Rule 3 for discussion topic storage

### Expected Behavior After Fix
- When user discusses a project idea, Agent saves it to memory under `goals` category
- When user asks "remember what we talked about?", Agent searches memories first
- User no longer needs to explicitly say "remember this" for important discussions

---

## [2026-02-04] Fix Sub Agent Misleading "Cannot Send File" Message

### Problem
Scheduled task completion messages showed misleading text like "无法直接发送文件给用户" (cannot send file to user directly), but files were still sent successfully. This confused users.

### Root Cause
1. Sub Agent's system prompt said "you MUST send files using send_telegram_file tool"
2. But Sub Agent doesn't have access to that tool (by design)
3. Agent correctly reported it couldn't send, but system's `file_tracker` automatically sent files anyway
4. Result: contradictory message + file delivery

### Fix
Updated Sub Agent's system prompt in `main.py`:
- **Before**: "If you create report files, you MUST send them using send_telegram_file tool"
- **After**: "Any files you create will be AUTOMATICALLY sent to the user by the system - just create the file, no need to send it manually"

Also clarified that the Agent's final response is shown to the user as the task completion message.

### Files Modified
- `main.py`: Updated `sub_system_prompt` (lines 291-301)

---

## [2026-02-04] Silent Review Loop - No More Rejection Spam

### Problem
During delegate_and_review tasks, every rejection would send a message to the user showing the rejection reason and retry count. This was annoying as users only care about the final result.

### Changes
Modified `bot/agent/task_manager.py` to make the review loop silent:

1. **No intermediate messages** - Removed sending of:
   - Result preview after each attempt
   - Rejection notifications with feedback

2. **Review log file** - All attempts are logged to a markdown file:
   - Saved to `data/review_logs/review_{task_id}.md`
   - Contains: attempt number, timestamp, status, feedback, suggestions
   - Sent to user only at the end (if there were retries)

3. **Clean final notifications**:
   - Success: `✅ Task completed (after X attempts)`
   - Max retries: `⚠️ Task completed after X attempts (review log attached)`

### Files Modified
- `bot/agent/task_manager.py`:
  - Added `_save_and_send_review_log()` method
  - Modified `create_review_task()` to log instead of notify

---

## [2026-02-04] Fix ReviewAgent Date Confusion

### Problem
ReviewAgent was flagging 2026 dates as incorrect and suggesting "correct all dates to 2025 timeline". This happened because the review prompt had no date context, so Claude defaulted to its training data cutoff (May 2025) as reference.

### Fix
Added current date to ReviewAgent's evaluation prompt:
```
## IMPORTANT: Current Date Context
**Today's date is {current_date}**. When evaluating dates in the result, use this as reference...
```

### Files Modified
- `bot/agent/review.py`: Added `datetime` import and current date injection into review prompt

---

## [2026-02-04] Enhanced Memory System - Proactive Storage & Retrieval

### Problem Addressed
When users express clear preferences (e.g., "call me 主人", "speak more sharply"), the Agent was not automatically saving these to memory. Users had to explicitly ask "will you remember this?" to trigger memory storage.

### Changes Made
Enhanced `prompts/memory.md` with more aggressive memory handling:

1. **CRITICAL: Memory Operations Every Message**
   - Added explicit rule: ALWAYS search memories at START of processing any message
   - Added explicit rule: ALWAYS save user preferences IMMEDIATELY when expressed

2. **Trigger Phrases That MUST Cause Memory Save**
   - "叫我..." / "称呼我为..." / "Call me..." → Save addressing preference
   - "说话...一点" / "语气..." / "风格..." → Save communication style
   - "我喜欢..." / "我不喜欢..." → Save personal preferences
   - "以后..." / "从现在开始..." → Save future behavior instructions
   - Any stated preference about interaction → Save to preferences category

3. **Clear Example of Correct vs Wrong Behavior**
   - Correct: Save memory BEFORE responding when user states preference
   - Wrong: Responding with preference applied but NOT saving to memory

### Files Modified
- `prompts/memory.md`: Added new "CRITICAL" section at top with explicit memory rules

### Expected Behavior After Fix
User says "以后叫我主人" → Agent IMMEDIATELY calls `memory_save()` → THEN responds "好的，主人"

---

## [2026-02-04] Mini App Complete UI Redesign v2 + Multi-Select Feature

### Overview
Complete redesign of the Mini App with iOS Settings app inspired design system. This is the second iteration addressing user feedback about proper edge margins and cleaner layouts.

### Design System (v2 - Complete Rewrite)
- **CSS Class-Based Architecture**: New semantic classes (`.page`, `.card`, `.list-item`) replacing inline Tailwind
- **Consistent 16px Edge Margins**: All pages have proper spacing from phone edges
- **Large 34px Bold Titles**: iOS-style large titles with subtle subtitles
- **Grouped Card Containers**: 12px rounded corners, white background, proper shadows
- **List Items with Dividers**: 56px height, left-aligned dividers, icon + content + accessory pattern
- **Safe Area Handling**: Proper padding for notched devices and TabBar clearance

### UI Components Rewritten
- **All Pages**: FilesPage, TasksPage, SchedulesPage, SubAgentsPage - unified layout structure
- **All Lists**: FileList, FileItem, TaskList, ScheduleList - consistent card + list-item pattern
- **TabBar**: Simplified with fixed height and safe area padding
- **Layout**: Minimal wrapper, consistent background color
- **Removed**: StorageBar component (storage now shown in header subtitle + inline progress bar)

### New Features (from v1)
- **Edit Mode**: "Edit" button in header to toggle multi-select mode
- **Multi-Select**: Circular checkboxes appear next to files in edit mode
- **Floating Action Bar**: Appears when files selected with "Download" and "Delete" buttons
- **Batch Download**: Single file sent directly, multiple files/folders zipped via Telegram Bot
- **Batch Delete**: Delete multiple files/folders at once
- **Toast Notifications**: Feedback at top of screen

### Technical Changes
- Complete CSS rewrite with design system variables
- Safe area inset support (`env(safe-area-inset-bottom)`)
- Page padding that clears TabBar (`padding-bottom: calc(tabbar + safe-area + 16px)`)
- Batch API endpoints with Telegram file sending

### Files Modified
- `webapp/src/index.css`: Complete design system rewrite
- `webapp/src/components/layout/Layout.tsx`: Simplified
- `webapp/src/components/layout/TabBar.tsx`: CSS class-based
- `webapp/src/pages/FilesPage.tsx`: New layout structure
- `webapp/src/pages/TasksPage.tsx`: New layout structure
- `webapp/src/pages/SchedulesPage.tsx`: New layout structure
- `webapp/src/pages/SubAgentsPage.tsx`: New layout structure
- `webapp/src/components/files/FileList.tsx`: Card + list-item pattern
- `webapp/src/components/files/FileItem.tsx`: List-item classes
- `webapp/src/components/tasks/TaskList.tsx`: Card + list-item pattern
- `webapp/src/components/schedules/ScheduleList.tsx`: Card + list-item pattern
- `webapp/src/stores/files.ts`: Selection state, batch actions
- `webapp/src/api/client.ts`: batchDelete, batchDownload methods
- `api/routes/files.py`: /batch/delete and /batch/download endpoints
- `api/dependencies.py`: bot_token storage
- `api/server.py`: Pass bot_token to Dependencies

### Files Removed
- `webapp/src/components/files/StorageBar.tsx`: Replaced by inline progress bar in FilesPage

### New Files
- `webapp/src/components/files/FloatingActionBar.tsx`: Multi-select action bar
- `webapp/src/components/common/Toast.tsx`: Toast notification component

---

## [2026-02-03] Mini App UI Redesign + SubAgents API Fix

### UI Improvements
- Redesigned all pages with modern card-based layout and gradient icons
- Added polished headers with icon badges and status indicators
- Improved TabBar with gradient backgrounds for active tabs
- Better empty states with helpful descriptions
- Card-based file items with colored icons per file type
- Consistent styling across Files, Tasks, Schedules, and Agents pages
- Smooth transitions and active states for touch feedback

### Bug Fixes
- Fixed SubAgents API response format mismatch (`completed` -> `tasks`)
- Updated frontend types to match backend response structure
- Fixed useEffect dependency arrays to prevent unnecessary re-renders

### Modified Files
- `api/routes/subagents.py`: Fixed history response field name
- `webapp/src/api/types.ts`: Updated SubAgentHistoryItem interface
- `webapp/src/pages/*.tsx`: Redesigned all page layouts
- `webapp/src/components/**/*.tsx`: Updated all components with new design
- Removed unused component files (Header, TaskCard, ScheduleCard, ExecutionLog)

---

## [2026-02-03] Add Persistent Mini App Menu Button

### Changes
- Added `MenuButtonWebApp` to provide a persistent entry point for the Mini App dashboard
- The menu button appears next to the text input field (bottom-left corner)
- Button labeled "📱 Dashboard" opens the Mini App when tapped
- Menu button is automatically set up when users interact with the bot

### Modified Files
- `bot/handlers.py`: Added `setup_menu_button()` function and integrated it with existing user setup flow

---

## [2026-02-03] Mini App Complete Implementation - All Phases Done

### Overview
Completed all 6 phases of the Telegram Mini App implementation. The bot now includes a full web dashboard accessible via the Mini App button in Telegram.

### Phase 5 - Bot Integration
- Added `mini_app_url` config option in config.json
- Added Mini App button to /start command using InlineKeyboardButton + WebAppInfo
- Button only appears when mini_app_url is configured (HTTPS required)

### Phase 6 - Deployment
- Created `nginx.conf` with:
  - Static file serving for frontend
  - API reverse proxy to port 8000
  - WebSocket proxy support
  - Gzip compression
  - Static asset caching (1 year)
  - Health check endpoint at /health

- Updated `Dockerfile`:
  - Added nginx installation
  - Added frontend build step
  - Copy built frontend to /var/www/html
  - Copy nginx.conf

- Updated `docker-compose.yml`:
  - Added port mapping 8080:80
  - Updated healthcheck to use curl

- Updated `entrypoint.sh`:
  - Start nginx if mini_app_api_enabled is true

### Modified Files
- `config.example.json` - Added mini_app_url option
- `bot/handlers.py` - Added Mini App button to start command
- `main.py` - Pass mini_app_url to setup_handlers
- `Dockerfile` - Added nginx and frontend build
- `docker-compose.yml` - Added port mapping
- `entrypoint.sh` - Start nginx before bot
- `nginx.conf` - New file for reverse proxy config

### Configuration
To enable Mini App:
1. Set `mini_app_api_enabled: true` in config.json
2. Set `mini_app_url` to your HTTPS domain (e.g., "https://yourdomain.com")
3. Rebuild and restart: `docker compose up --build -d`
4. The Mini App button will appear in /start command

---

## [2026-02-03] Mini App Frontend - Phase 2

### Overview
Implemented the React frontend for the Telegram Mini App dashboard. This phase includes the complete UI with file browsing, task monitoring, schedule viewing, and Sub Agent status.

### Technology Stack
- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS v4 (styling)
- Zustand (state management)
- @twa-dev/sdk (Telegram Mini App integration)
- react-router-dom (routing)
- lucide-react (icons)

### New Features

**Authentication Flow**:
- Telegram initData authentication on app load
- JWT token storage with Zustand persist
- Auto-reconnect WebSocket on token restore
- Development mode bypass for local testing

**Files Page**:
- Directory browsing with navigation
- Storage quota progress bar
- File/folder icons based on type
- Download files directly
- Delete files with confirmation
- Create new directories

**Tasks Page**:
- Running tasks with cancel option
- Recently completed tasks list
- Task status indicators (running, completed, failed, cancelled)
- Real-time updates via WebSocket

**Schedules Page**:
- Active and inactive schedule lists
- Schedule type indicators (daily, weekly, interval)
- Last run and next run times
- Execution history/logs

**Sub Agents Page**:
- Agent pool status with progress bar
- Running agents with elapsed time
- Completed agents history
- Retry count display

**Real-time Updates**:
- WebSocket client with auto-reconnect
- Task status updates
- Storage quota updates
- Schedule execution notifications

### New Files
- `webapp/` - Complete React application directory
  - `src/api/types.ts` - TypeScript type definitions
  - `src/api/client.ts` - API client with JWT auth
  - `src/api/websocket.ts` - WebSocket client
  - `src/stores/auth.ts` - Auth state (Zustand)
  - `src/stores/files.ts` - Files state
  - `src/stores/tasks.ts` - Tasks state
  - `src/stores/schedules.ts` - Schedules state
  - `src/stores/subagents.ts` - Sub Agents state
  - `src/hooks/useTelegram.ts` - Telegram SDK hook
  - `src/hooks/useWebSocket.ts` - WebSocket subscriptions
  - `src/components/layout/` - Layout, Header, TabBar
  - `src/components/files/` - StorageBar, FileList, FileItem
  - `src/components/tasks/` - TaskList, TaskCard
  - `src/components/schedules/` - ScheduleList, ScheduleCard, ExecutionLog
  - `src/pages/` - FilesPage, TasksPage, SchedulesPage, SubAgentsPage
  - `src/App.tsx` - Root component with routing
  - `src/index.css` - Tailwind CSS with theme variables
  - `vite.config.ts` - Vite config with API proxy
  - `index.html` - Entry point with Telegram script

### Build Output
- Production build: ~325KB JS (gzipped ~98KB)
- CSS: ~12KB (gzipped ~3KB)

---

## [2026-02-03] Mini App API Backend - Phase 1

### Overview
Implemented the backend API server for the Telegram Mini App dashboard. This phase includes authentication, all REST API endpoints, and WebSocket support for real-time updates.

### New Features

**Authentication System**:
- Telegram initData validation with HMAC-SHA256
- JWT token generation and verification
- 24-hour token expiration

**REST API Endpoints**:
- `POST /api/auth` - Exchange initData for JWT token
- `GET /api/auth/me` - Get current user info
- `GET /api/files` - List files with storage info
- `GET /api/files/download/{path}` - Download file
- `DELETE /api/files/{path}` - Delete file
- `POST /api/files/mkdir` - Create directory
- `GET /api/files/storage` - Get storage quota
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{id}` - Get task details
- `POST /api/tasks/{id}/cancel` - Cancel task
- `GET /api/schedules` - List scheduled tasks
- `GET /api/schedules/logs` - Get operation logs
- `GET /api/subagents/status` - Get Sub Agent pool status
- `GET /api/subagents/running` - List running agents
- `WS /api/ws` - WebSocket for real-time updates

**WebSocket Events**:
- `task_update` - Task status changes
- `task_created` - New task created
- `schedule_executed` - Schedule ran
- `storage_update` - Storage quota changed

**Integration**:
- Shared manager instances with bot
- Async startup with bot polling
- Configurable via config.json

### New Files
- `api/__init__.py` - API package exports
- `api/auth.py` - Telegram initData + JWT authentication
- `api/websocket.py` - WebSocket connection manager
- `api/dependencies.py` - FastAPI dependency injection
- `api/server.py` - FastAPI app creation
- `api/routes/__init__.py` - Routes package
- `api/routes/auth.py` - Authentication endpoints
- `api/routes/files.py` - File management endpoints
- `api/routes/tasks.py` - Task endpoints
- `api/routes/schedules.py` - Schedule endpoints
- `api/routes/subagents.py` - Sub Agent endpoints

### Modified Files
- `main.py` - Added async startup with API server integration
- `requirements.txt` - Added FastAPI, uvicorn, python-jose dependencies
- `config.example.json` - Added Mini App API configuration options

### Configuration
New config options:
- `mini_app_api_enabled` (default: true) - Enable/disable API server
- `mini_app_api_port` (default: 8000) - API server port
- `mini_app_api_dev_mode` (default: false) - Enable Swagger docs

---

## [2026-02-03] Telegram Mini App Technical Design Document

### Overview
Created comprehensive technical design document for implementing a Telegram Mini App (TWA) dashboard for each user.

### Document Contents

**Architecture Design**:
- React 18 + TypeScript frontend with Tailwind CSS + shadcn/ui
- FastAPI backend with JWT authentication
- WebSocket real-time updates
- Same Docker container deployment with Nginx reverse proxy

**Features Planned**:
- File management UI (browse, download, delete files)
- Task execution status monitoring with real-time updates
- Sub Agent pool status and history
- Scheduled task management and execution logs

**Security**:
- Telegram initData HMAC-SHA256 validation
- JWT token-based API authentication
- User data isolation

**Integration**:
- Shared manager instances between bot and API
- WebSocket broadcasting for task/schedule events
- Mini App buttons in bot menu

### New Files
- `docs/MINI_APP_TECHNICAL_DESIGN.md` - Complete technical specification

---

## [2026-02-03] MarkdownV2 Rich Text Support

### Overview
Added Telegram MarkdownV2 format support for rich text display. Claude's markdown output is now converted to Telegram's native format.

### New Features

**Rich Text Formatting**:
- `**bold**` → *bold* (displayed as bold)
- `*italic*` → _italic_ (displayed as italic)
- `` `code` `` → `code` (displayed as monospace)
- `[text](url)` → clickable links
- Code blocks preserved with syntax highlighting

**Fallback Mechanism**:
- If MarkdownV2 parsing fails, automatically falls back to plain text
- Ensures messages are always delivered

### Technical Details
- Added `convert_to_markdown_v2()` function in `bot/agent/tools.py`
- Special characters escaped properly for MarkdownV2
- Code blocks and inline code protected during conversion

### Modified Files
- `bot/agent/tools.py` - Added MarkdownV2 conversion function
- `bot/handlers.py` - Updated send_long_message with MarkdownV2 support
- `bot/message_queue.py` - Updated message queue with MarkdownV2 support

---

## [2026-02-03] Admin Broadcast and Menu Refresh

### Overview
Added admin commands to broadcast messages to all users and refresh command menus.

### New Features

**Broadcast Command**:
- `/admin broadcast <message>` - Send announcement to all enabled users
- Shows success/failure count after broadcast

**Menu Refresh Command**:
- `/admin refresh_menu` - Refresh command menus for all enabled users
- Useful after bot updates to push new commands to users
- Users just need to type `/` to see updated menu

### Modified Files
- `bot/handlers.py` - Added broadcast and refresh_menu commands

---

## [2026-02-03] Dynamic Bot Commands Menu

### Overview
Implemented dynamic command menu that shows different commands based on user role. Admin users see additional management commands while regular users see only standard commands.

### New Features

**Role-Based Command Menu**:
- Regular users see standard commands (ls, storage, session, etc.)
- Admin users see additional `/admin` command
- Commands are set per-user using Telegram's BotCommandScopeChat

**Auto-Setup**:
- Command menu is automatically set on first user interaction (/start or message)
- When a user is enabled via `/admin enable`, their command menu is set up immediately
- Commands are cached per session to avoid redundant API calls

### Technical Details

**User Commands** (14 commands):
- start, help, ls, storage, status, session
- new, compact, env, packages, schedule, skill, voice, del

**Admin Commands** (15 commands):
- All user commands plus `/admin`

### Modified Files
- `bot/handlers.py` - Added dynamic command menu setup logic

---

## [2026-02-03] OpenAI Research Tools Integration

### Overview
Added OpenAI research capabilities using gpt-4o for web search and o3 for deep reasoning and analysis. Enables comprehensive research workflows that combine real-time web data with advanced analytical capabilities.

### New Features

**OpenAI Research Tools**:
- `openai_web_search` - Web search using gpt-4o with OpenAI's web search capability
- `openai_deep_analyze` - Deep analysis using o3 for complex reasoning
- `openai_research` - Complete research pipeline (search + analysis)
- `openai_chat` - Simple chat with gpt-4o/gpt-4o-mini

**Research Workflow**:
1. Search phase: gpt-4o + web_search (o3 doesn't support direct web search)
2. Analysis phase: o3 with high reasoning effort (default)
3. Agent automatically selects tools based on user intent

**Default Configuration**:
- Analysis model: o3 (most capable)
- Reasoning effort: high (thorough analysis)

### New Files
- `bot/openai_research/__init__.py` - Module init
- `bot/openai_research/client.py` - OpenAI Research Client wrapper
- `.claude/skills/openai-research/SKILL.md` - Skill documentation with usage scenarios

### Modified Files
- `bot/agent/tools.py` - Added OpenAI research tools and `_openai_api_key` config
- `bot/agent/client.py` - Added `openai_api_key` parameter and allowed tools
- `bot/handlers.py` - Pass `openai_api_key` to TelegramAgentClient

### Configuration
Uses `openai_api_key` from `config.json` (already configured).

---

## [2026-02-03] Memory System: On-Demand Recall

### Overview
Changed memory retrieval from auto-inject to on-demand recall. Instead of loading all memories into the system prompt (which wastes tokens), the Agent now searches memories only when handling personalized requests.

### Changes

**On-Demand Recall**:
- Agent searches `memory_search()` before answering personalized requests
- Different request types trigger different category searches:
  - Writing tasks → search `preferences`
  - Work advice → search `career`
  - Goal discussions → search `goals`
- Saves tokens by not loading memories for simple/generic requests

### Modified Files
- `prompts/memory.md` - Added "Recall Before Responding" section with search guidelines
- `prompts/context.md` - Removed `{user_memories}` placeholder
- `bot/prompt_builder.py` - Removed auto memory injection
- `bot/agent/client.py` - Removed user_data_dir parameter

---

## [2026-02-03] Enhanced Memory System with Proactive Learning and User Feedback

### Overview
Major upgrade to the memory system enabling proactive information capture with user visibility controls and correction mechanisms. The AI now actively identifies valuable information during conversations and notifies users about each saved memory.

### New Features

**Proactive Memory Capture**:
- AI proactively identifies and saves valuable user information without explicit requests
- Every saved memory triggers a notification to the user (expandable blockquote format)
- Users can correct, modify visibility, or delete any memory

**Public/Private Visibility**:
- Memories now have visibility levels: `public` (🌐) or `private` (🔒)
- Default visibility based on category (career/interests/goals = public; personal/emotions/preferences = private)
- User corrections automatically train future visibility preferences

**Memory Timeline & Supersede**:
- Memories maintain temporal relationships (supersedes/superseded_by)
- Job changes, life updates create new entries while preserving history
- Timeline view shows progression over time

**Post-Processing Analysis**:
- Memory analysis runs on `/new` command (session end)
- Background analysis every 10 messages to catch missed information
- Uses Claude API to identify overlooked valuable information

### New Memory Categories
Added: `relationships`, `emotions` (both default to private)

### New Memory Tools
- `memory_save_with_supersede` - Update information while preserving timeline
- `memory_update` - Modify content, visibility, confirm memories
- `memory_stats` - View memory statistics

### Notification Format
```
📝 记住了：「在字节跳动担任产品经理」
📂 职业 | 🌐 公开
回复可修改~
```

### New Files
- `bot/memory/__init__.py` - Module exports
- `bot/memory/models.py` - Memory, MemoryVisibility, UserMemoryPreferences data models
- `bot/memory/manager.py` - MemoryManager class with CRUD operations
- `bot/memory/analyzer.py` - MemoryAnalyzer for post-processing conversations

### Modified Files
- `prompts/memory.md` - Complete rewrite with proactive memory rules
- `bot/agent/tools.py` - Enhanced memory tools using MemoryManager
- `bot/handlers.py` - Added memory analysis triggers in /new and periodic checks

---

## [2026-02-03] Simplify voice transcription UI

Removed redundant text preview in processing message since transcript file is already sent to user.

### Modified Files
- `bot/handlers.py` - Removed duplicate text display in voice processing

---

## [2026-02-03] Fix: Convert .oga to .mp3 for OpenAI API compatibility

OpenAI's GPT-4o Transcribe API doesn't support `.oga` format directly. Added automatic conversion from `.oga` to `.mp3` before transcription.

### Fixed
- Voice transcription now works with Telegram voice messages (.oga format)
- Uses pydub/ffmpeg to convert .oga → .mp3 before API call

### Modified Files
- `bot/transcribe.py` - Added .oga to .mp3 conversion in transcribe() method

---

## [2026-02-03] Voice-to-Text Transcription with GPT-4o Transcribe

### Overview
Added comprehensive voice message transcription support using OpenAI's GPT-4o Transcribe API. Users can now send voice messages to the bot, which will be automatically transcribed, saved, and processed by the Claude Agent.

### New Features

**Voice Transcription**:
- Supports Telegram voice messages (.oga format) and audio files
- Uses GPT-4o Transcribe model for high-accuracy transcription
- Long audio files automatically split using VAD (Voice Activity Detection)
- Transcripts permanently saved to user's `transcripts/` folder
- Voice files kept for 24 hours then auto-deleted

**User Dictionary**:
- Custom vocabulary corrections for improved accuracy
- Context prompts for domain-specific transcription
- `/voice` command for managing settings

**Commands**:
```
/voice - Show current settings
/voice add <wrong> <correct> - Add vocabulary correction
/voice del <wrong> - Remove vocabulary correction
/voice list - List all corrections
/voice prompt <text> - Set context prompt
/voice prompt clear - Clear context prompt
```

### Configuration

Added `openai_api_key` to `config.json`:
```json
{
    "openai_api_key": "sk-..."
}
```

### New Files
- `bot/transcribe.py` - VoiceTranscriber, VoiceDictionary, TranscriptManager classes

### Modified Files
- `config.json` - Added `openai_api_key` field
- `main.py` - Added `openai_api_key` to api_config, added voice file cleanup job
- `requirements.txt` - Added `openai>=1.0.0`, `pydub>=0.25.0`
- `Dockerfile` - Added `ffmpeg` system dependency
- `bot/handlers.py` - Updated voice handling, added `/voice` command
- `bot/i18n.py` - Added voice transcription and dictionary strings

### Data Storage
- `{user_dir}/transcripts/` - Permanent transcript storage
- `{user_dir}/.voice_temp/` - Temporary voice files (24h retention)
- `{user_dir}/voice_dictionary.json` - User vocabulary settings

### Technical Details
- Voice Activity Detection (VAD) used for splitting long audio
- Maximum 25MB per API call, auto-split for larger files
- Supports caption merging with transcribed text
- Daily cleanup job removes voice files older than 24 hours

---

## [2026-02-02] Dynamic Topic-Based Context Management System

### Overview
Implemented a flexible, semantic topic management system that automatically detects topic changes, dynamically manages context, and allows topic recall.

### New Features

**Topic Detection (3-Tier Classification)**:
- Tier 1: Heuristics (free) - handles ~70% of cases with keyword matching and signal detection
- Tier 2: Haiku API (~$0.0003) - for ambiguous cases requiring semantic understanding
- Tier 3: Full model (reserved for edge cases)

**TopicManager**:
- Automatic topic creation and tracking
- Active topics limit (max 5)
- Topic archival after 2 hours of inactivity
- Topic recall by name reference
- Context injection into system prompt

**Auto-Compaction Based on Token Pressure**:
- < 100K tokens: Normal operation
- 100-140K tokens: Archive topics inactive > 1 hour
- > 140K tokens: Force archive all except current topic

**Session Integration**:
- `/session` command now shows current topic info
- `/new` command clears all topics

### New Files
- `bot/topic/__init__.py` - Module exports
- `bot/topic/manager.py` - TopicManager class, Topic dataclass, TopicContext
- `bot/topic/classifier.py` - TopicClassifier with 3-tier classification

### Modified Files
- `bot/session/manager.py` - Added `current_topic_id` to SessionInfo
- `bot/prompt_builder.py` - Added `topic_context` parameter to build_system_prompt()
- `bot/agent/client.py` - Added `topic_context` parameter to TelegramAgentClient
- `bot/handlers.py` - Integrated TopicManager for message classification and context injection

### Data Storage
Topics are stored per-user in `{user_dir}/topics.json`:
```json
{
  "active_topic_ids": ["topic_20260202_abc"],
  "current_topic_id": "topic_20260202_abc",
  "topics": {
    "topic_20260202_abc": {
      "id": "topic_20260202_abc",
      "title": "Stock analysis for TSLA",
      "keywords": ["TSLA", "stock", "earnings"],
      "status": "active",
      "message_count": 12,
      "summary": ""
    }
  }
}
```

---

## [2026-02-01] Fix Duplicate Message Sending

### Overview
Fixed issue where the bot would send the same response twice when the Agent uses `send_telegram_message` tool.

### Problem
When Agent uses `send_telegram_message` tool to reply, the message was sent twice:
1. First via the tool itself
2. Then again via `handlers.py` sending `response.text`

### Solution
- Added `message_sent` flag to `AgentResponse` dataclass
- Track when `send_telegram_message` tool is used during processing
- Skip sending `response.text` if message was already sent via tool

### Modified Files
- `bot/agent/client.py` - Added `message_sent` tracking in AgentResponse and process_message
- `bot/handlers.py` - Added `and not response.message_sent` checks before sending response

---

## [2026-02-01] Memory Storage Order - Newest First

### Overview
Changed memories.json storage order so newest memories appear at the top of the file for easier viewing.

### Changes
- Modified `memory_save` in `bot/agent/tools.py` to insert new memories at the beginning of the list instead of appending
- New memories now appear first when viewing the raw JSON file

### Modified Files
- `bot/agent/tools.py` - Changed `append()` to `insert(0, ...)` for memory storage

---

## [2026-02-01] Proactive Memory System

### Overview
Added a proactive memory system that allows the Agent to automatically learn and remember important information about users without requiring explicit "remember this" commands.

### New Features

**Memory Tools** (4 new tools):
- `memory_save` - Save new memories with category, tags, and timeline support
- `memory_search` - Search memories by keyword or category
- `memory_list` - View full timeline of a category (e.g., career history)
- `memory_delete` - Remove memories when user asks to forget

**Memory Categories**:
- personal, family, career, education, interests
- preferences, goals, finance, health, schedule, context

**Memory Structure** (memories.json):
```json
{
  "id": "mem_20260201_abc123",
  "content": "用户在字节跳动做产品总监",
  "category": "career",
  "source_type": "explicit",  // or "inferred"
  "tags": ["工作", "字节跳动"],
  "valid_from": "2026-02-01",
  "valid_until": null,
  "related_to": ["mem_xxx"]   // timeline links
}
```

**Proactive Learning**:
- Agent identifies important info during conversation
- Saves without waiting for "remember this" command
- Handles timeline changes (job changes are not contradictions)
- Asks user when real contradictions detected

### Modified Files
- `prompts/memory.md` (NEW) - Proactive memory guidelines
- `bot/agent/tools.py` - Added 4 memory tools
- `bot/agent/client.py` - Added memory tools to allowed_tools
- `bot/prompt_builder.py` - Integrated memory module

### Storage
- Location: `users/{user_id}/data/memories.json`
- Supports timeline queries (see career/education history)
- Automatic deduplication

---

## [2026-02-01] Multi-Task Handling & Time-Bound Task Parsing

### Problem 1: Agent couldn't handle multiple tasks in one message
Previous rule was too strict: "After calling delegate_task, STOP immediately"
This prevented Agent from:
- Delegating a research task AND creating a scheduled reminder
- Handling multiple independent tasks in one user message

### Solution 1: Multi-Task Handling
Updated `prompts/tools.md` to allow handling multiple tasks:
- Agent can now call multiple tools (delegate_task + schedule_create, etc.)
- Must still send only ONE final summary message
- Cannot wait for delegated tasks or check status immediately

### Problem 2: Time-bound task misunderstanding
Agent misunderstood complex time-bound user requests:
- User: "晚上提醒我调研一下中兴通讯吧，你可以先给一些资料给我"
- Wrong interpretation: Execute research NOW + set separate reminder for tonight (failed)
- Correct interpretation: Schedule a research task for tonight that will notify user when complete

Issues identified:
1. **Semantic misunderstanding**: "晚上提醒我调研X" should mean "schedule research for tonight" not "research now + remind tonight"
2. **Task discontinuity**: When scheduled task creation failed, Agent gave up instead of retrying or offering alternatives
3. **No clarification mechanism**: Agent didn't ask for clarification on ambiguous time instructions

### Solution
Created new prompt module `prompts/task_understanding.md` with:

1. **Time-Bound Task Patterns**: Clear rules for parsing "时间 + 提醒我 + 动作" patterns
2. **Task Failure Recovery**: Guidelines to retry failed tasks or offer alternatives
3. **Clarification Rules**: When to ask user vs when to assume
4. **Multi-Step Task Handling**: How to chain dependent tasks correctly
5. **Default Time Mappings**: "晚上" → 20:00, "下午" → 15:00, etc.

### Modified Files
- `prompts/task_understanding.md` (NEW) - Task understanding rules and patterns
- `prompts/tools.md` - Updated Sub Agent rules to allow multi-task handling
- `bot/prompt_builder.py` - Added task_understanding module to system prompt assembly

### Key Improvements
- Agent can now handle multiple tasks in one message (e.g., delegate + schedule)
- Agent will now correctly interpret "晚上提醒我调研X" as a single scheduled task
- When task creation fails, Agent will retry or offer alternatives
- Agent will ask for clarification on ambiguous requests before acting

---

## [2026-01-27] Sub Agent File Delivery Fix

### Problem
When Sub Agents complete tasks that generate files (reports/, analysis/), the files were never sent to users:
1. Sub Agent saves files to allowed directories
2. TaskManager sends text result (truncated to 3000 chars)
3. Files are never delivered - no mechanism existed to detect and send them

### Solution
Integrated FileTracker into TaskManager to automatically send generated files:

1. **File Tracking**: Create FileTracker before task execution, detect new/modified files after completion
2. **Automatic File Delivery**: Send files to user via send_file_callback
3. **Result Enhancement**: Append file list to result for Main Agent awareness
4. **Increased Truncation Limit**: 3000 → 8000 characters for result preview

### Modified Files
- `bot/agent/task_manager.py`
  - Added `send_file_callback` and `send_message_callback` parameters to `__init__`
  - Added `_send_task_files()` method using FileTracker
  - Updated `run_task()` and `run_task_with_review()` to track and send files
  - Increased truncation limit from 3000 to 8000 characters
- `bot/handlers.py`
  - Updated `get_task_manager()` to pass file callbacks to TaskManager
- `bot/i18n.py`
  - Updated `SYNTHESIZE_RESULTS_PROMPT` to mention files were auto-sent

### Code Flow After Fix
```
Sub Agent executes
    ↓
FileTracker.start() [before execution]
    ↓
Files created in reports/, analysis/
    ↓
FileTracker.get_new_files() [after execution]
    ↓
_send_task_files() → Files sent to user
    ↓
Result includes: "📎 Generated Files (2): reports/analysis.md, ..."
    ↓
Main Agent synthesizes and acknowledges files
```

---

## [2026-01-26] Fix Sub Agent Attempting to Use Unauthorized Tools

### Problem
- Sub Agent displayed "need authorization for send_telegram_file and send_telegram_message tools"
- Users could not receive files generated by Sub Agent

### Root Cause
- Sub Agent's system prompt stated "you MUST send files using send_telegram_file tool"
- However, Sub Agent does NOT have permission for `send_telegram_file` and `send_telegram_message` (only Main Agent has these)
- This was a prompt vs actual permissions mismatch bug

### Fix
Updated Sub Agent's Output Rules:
- Removed "MUST send files using send_telegram_file tool" instruction
- Clarified that Sub Agent cannot directly send messages/files to users
- Sub Agent should save files to directories and return result summary
- Main Agent handles all user communication

### Modified Files
- `bot/prompt_builder.py` - Updated Sub Agent Output Rules

### Additional Changes
- `docker-compose.yml` - Added `.claude/skills` volume mount for easier skill updates (restart only, no rebuild needed)

---

## [2026-01-26] Deep Research System - Enhanced Research Task Quality

### Problems
1. Research tasks (especially financial research) had inconsistent data accuracy
2. Research depth was insufficient, lacking systematic exploration mindset
3. Rejection mechanism only had simple feedback, no guided improvement directions

### Solution

**New deep-research Skill**
- Created `.claude/skills/deep-research/SKILL.md`
- Auto-trigger: Detects keywords like "research", "analyze", "investigate", "deep dive"
- Four-phase research flow: Planning → Data Collection → Deep Exploration → Comprehensive Report
- Data verification rules: Multi-source cross-verification + mandatory timestamp annotation
- Review checklist: Coverage, Depth, Data Quality, Logic

**Enhanced ReviewAgent Review Mechanism**
- Review prompt changed from simple PASS/REJECT to exploratory review
- New output format: MISSING (missing dimensions), SUGGESTIONS (improvement directions)
- ReviewResult structure enhanced with suggestions and missing_dimensions lists

**Enhanced retry_history Structure**
- Each rejection record includes: feedback, suggestions, missing_dimensions, result_summary
- Sub Agent can see complete rejection context including:
  - Rejection reasons from each previous attempt
  - List of missing dimensions
  - Main Agent's suggested exploration directions

**Enhanced User Notification on Rejection**
- Shows specific issues
- Shows missing dimensions
- Shows improvement direction suggestions
- Shows current attempt count

**Enhanced Sub Agent Rules**
- Added core principle of deep exploration
- Added research depth requirements (Foundation → Analysis → Insight → Recommendation levels)
- Added guidance for handling rejections

**Main Agent Tools Documentation Update**
- Added "Research Tasks - Quality Review Delegation" section
- Explained when to use delegate_and_review
- Provided review_criteria writing guidance

### Modified Files
- `.claude/skills/deep-research/SKILL.md` - New deep research Skill
- `bot/agent/review.py` - Enhanced review prompt and return structure
- `bot/agent/task_manager.py` - Enhanced retry_history structure and rejection notifications
- `bot/prompt_builder.py` - Enhanced Sub Agent prompt retry history display and rules
- `prompts/tools.md` - Added research task review delegation documentation

### Usage
When user sends tasks containing keywords like "research", "analyze", the Agent will:
1. Use deep-research skill to formulate research plan
2. Use delegate_and_review to delegate to Sub Agent
3. Automatically review results, provide specific improvement directions when rejecting
4. Sub Agent improves based on rejection history, up to 10 iterations

---

## [2026-01-24] Sub Agent 模块化提示词 + 时间意识

### 问题
1. Sub Agent 使用简单的硬编码提示词，没有动态 Skills 列表
2. 主 Agent 和 Sub Agent 都没有日期意识，导致金融数据调研时不知道今天是什么时间
3. Sub Agent 打回重试时，只在 prompt 中附加最后一次的 feedback，没有完整历史

### 解决方案

**为主 Agent 添加时间意识**
- 在 `prompts/context.md` 添加 `{current_date}` 和 `{current_weekday}` 占位符
- 在 `prompt_builder.py` 中动态填充当前日期

**Sub Agent 模块化提示词**
- 新增 `build_sub_agent_prompt()` 函数，构建结构化的 Sub Agent 提示词
- 包含：当前日期、任务描述、质量标准、完整打回历史、动态 Skills 列表
- 打回历史显示所有之前的尝试和拒绝原因，帮助 Sub Agent 避免重复错误

**时间敏感数据验证**
- 在提示词中强调验证数据时间戳的重要性
- 金融数据调研必须标注数据日期

### 修改文件
- `prompts/context.md` - 添加日期占位符
- `bot/prompt_builder.py` - 添加日期支持，新增 `build_sub_agent_prompt()` 函数
- `bot/handlers.py` - 使用新的模块化构建函数创建 Sub Agent 提示词

---

## [2026-01-24] 临时文件管理优化 - 减少中间文件发送

### 问题
之前系统会自动发送任务执行期间创建的所有文件，包括中间过程文件（如草稿、临时数据等）。这些中间文件发送后也没有被清理，导致用户文件夹臃肿。

### 解决方案

**新增 temp/ 临时目录机制**
- 中间过程文件应放在 `temp/` 目录
- `temp/` 目录中的文件不会被自动追踪和发送
- 任务完成后自动清理 `temp/` 目录内容

**扩展文件排除规则**
- 新增排除目录：`temp`, `tmp`, `working`, `cache`, `drafts`
- 新增排除文件名模式：`*_draft.*`, `*_temp.*`, `*_tmp.*`, `*_wip.*`, `*_step*.*`, `*_intermediate.*`

**系统提示词更新**
- 在 `prompts/rules.md` 中添加"临时文件管理"章节
- 详细说明何时使用 temp/ 目录
- 提供正确的工作流示例

### 修改文件
- `bot/file_tracker.py` - 扩展排除规则，新增 cleanup_temp_directory() 函数
- `bot/agent/client.py` - 任务完成后调用临时目录清理
- `prompts/rules.md` - 新增临时文件管理规则章节

---

## [2026-01-23] /status 显示累计统计（跨会话）

### 问题
`/new` 后 `/status` 统计归零，用户希望看到累计总量而非单次会话。

### 修复

**新增累计统计字段**
- UserConfig 新增：total_input_tokens, total_output_tokens, total_cost_usd, total_messages, total_sessions
- 数据持久化到 users.json，重启后不丢失

**更新 /status 显示**
- 显示 All Time 累计统计（消息数、会话数、Token、费用）
- 显示 Current Session 当前会话信息
- `/new` 后累计不归零，只清除当前会话

**新增方法**
- `user_manager.update_cumulative_stats()` - 更新累计统计
- `user_manager.get_cumulative_stats()` - 获取累计统计
- `user_manager.reset_cumulative_stats()` - 重置累计统计（管理员用）

### 修改文件
- `bot/user/manager.py` - UserConfig 新增统计字段和方法
- `bot/handlers.py` - 更新 status_command，新增 update_usage_stats 辅助函数

---

## [2026-01-23] 启用 Bash 命令执行能力（带安全检查）

### 背景
之前 Bash 被完全禁用，导致 Agent 无法执行 Python 脚本（如生成 GIF）。用户只能收到脚本文件而非执行结果。

### 新增功能

**多层安全检查机制**
- `bot/bash_safety.py` - Bash 命令安全检查器
- 在 PreToolUse hook 中拦截并验证每条 Bash 命令

**安全检查层级**：

1. **危险模式黑名单**（Layer 1）
   - `rm -rf /`, `rm -rf ~` - 系统破坏
   - `sudo`, `su` - 提权命令
   - `shutdown`, `reboot` - 系统控制
   - `chmod 777 /` - 权限攻击
   - `curl | bash` - 远程代码执行
   - 访问 `/etc/`, `/proc/`, `/sys/`

2. **安全前缀白名单**（Layer 2）
   - `python`, `pip` - Python 操作
   - `ls`, `cat`, `head`, `tail` - 文件查看
   - `git`, `node`, `npm` - 开发工具
   - `ffmpeg`, `convert` - 多媒体处理

3. **路径敏感命令验证**（Layer 3）
   - `rm`, `cp`, `mv`, `chmod` 等命令
   - 验证所有路径都在用户工作目录内

4. **未知命令监控**（Layer 4）
   - 不在白名单但无危险模式的命令
   - 允许执行但记录日志监控

### 允许的操作示例
```bash
pip install pillow           # 安装 Python 包
python scripts/gen_gif.py    # 运行 Python 脚本
ffmpeg -i input.mp4 out.gif  # 视频转 GIF
ls -la documents/            # 查看文件
```

### 被阻止的操作示例
```bash
sudo apt install xxx         # 需要 root
rm -rf /                     # 系统破坏
cat /etc/passwd              # 敏感文件
curl xxx | bash              # 远程执行
```

### 修改文件
- `bot/bash_safety.py` - 新增安全检查模块
- `bot/agent/client.py` - 启用 Bash，添加安全 hook
- `prompts/rules.md` - 添加 Bash 使用规则
- `prompts/tools.md` - 更新能力列表

### 使用场景
- 生成 GIF/图片（Python + PIL）
- 运行数据处理脚本
- 安装 Python 依赖
- 多媒体格式转换

---

## [2026-01-23] 系统提示词模块化重构

### 背景
原有的 `system_prompt.txt` 是一个 314 行的单体文件，难以维护和扩展。Skills 信息也是静态的，无法动态加载。

### 重构内容

**模块化提示词架构**
创建 `prompts/` 目录，将提示词拆分为独立模块：

- `prompts/soul.md` - Bot 人格和身份（品牌、价值观、语言偏好）
- `prompts/rules.md` - 操作规则（格式规则、安全规则、路径显示规则）
- `prompts/tools.md` - 可用工具描述（核心能力、工具列表、使用指南）
- `prompts/skills_intro.md` - Skills 系统介绍模板
- `prompts/context.md` - 用户上下文模板（动态填充）
- `prompts/skills/README.md` - Skills 开发指南

**动态 Skills 加载**
- Skills 列表现在从 `.claude/skills/` 目录动态生成
- 自动提取每个 Skill 的 YAML frontmatter（name, description, triggers）
- 新增或删除 Skill 无需修改系统提示词

**新增 Prompt Builder 模块**
- `bot/prompt_builder.py` - 提示词组装器
- `build_system_prompt()` - 从模块化组件构建完整提示词
- `get_available_skills()` - 动态获取可用 Skills
- `extract_skill_metadata()` - 从 SKILL.md 提取元数据

### 修改文件
- `prompts/` - 新增目录及 5 个模块文件
- `bot/prompt_builder.py` - 新增提示词构建器
- `bot/agent/client.py` - 使用新的 prompt builder

### 优势
- 各模块职责单一，易于维护
- Skills 动态加载，添加新 Skill 无需改代码
- 提示词全部英文，避免编码问题
- 易于扩展新的提示词模块

---

## [2026-01-23] 修复消息顺序问题 - 消息队列序列化

### 问题背景
- 用户反馈 Bot 发送的消息顺序有时不正确
- 例如：Claude 说 "现在发送给你" 但文件先到达，或者消息顺序错乱
- 原因：多个异步消息/文件发送操作没有序列化，存在竞态条件
- Telegram API 不保证消息按发送顺序到达

### 修复内容

**新增消息队列系统**
- 创建 `bot/message_queue.py` 模块
- `MessageQueueManager` - 全局消息队列管理器
- `UserMessageQueue` - 每用户独立的消息队列
- 所有消息/文件发送操作通过队列序列化，确保 FIFO 顺序

**队列工作原理**
1. 发送消息/文件时，请求入队
2. 专门的处理任务按顺序处理队列
3. 每条消息发送完成后才处理下一条
4. 支持自动队列刷新和并发安全

**集成改动**
- `handlers.py` 中的 `send_message` 和 `send_file` 回调现在使用队列包装
- Agent 工具、文件追踪、Sub Agent 等所有发送操作都自动序列化
- 无需修改其他模块，改动对调用方透明

### 修改文件
- `bot/message_queue.py` - 新增消息队列模块
- `bot/handlers.py` - 集成 MessageQueueManager，使用队列包装的回调

### 注意事项
- 需要 `docker compose up --build -d` 重新构建
- 队列是异步处理，不会阻塞调用方
- 每个用户有独立的队列，不同用户之间不互相影响

---

## [2026-01-23] Bug 修复：API 配置和 /status 显示

### 修复内容

1. **修复 "Invalid API key" 错误**
   - 问题：Claude Agent SDK 无法读取 API key，导致 "Invalid API key · Please run /login"
   - 原因：entrypoint.sh 依赖环境变量，但 docker-compose.yml 未设置
   - 修复：entrypoint.sh 现在直接从 config.json 读取 `anthropic_api_key` 和 `anthropic_base_url`

2. **修复 /status 命令显示 "Model: unknown"**
   - 问题：/status 显示的模型名称始终是 unknown
   - 原因：handlers.py 查找的 key 是 `claude_model`，但 api_config 传递的是 `model`
   - 修复：改为 `api_config.get('model', 'unknown')`

3. **修复 Reactions 随机表情问题**
   - 问题：API 调用失败时会回退到随机正面表情（如 🔥），导致不恰当的反应
   - 修复：API 失败时不添加任何反应，而不是随机选择

### 修改文件
- `entrypoint.sh` - 从 config.json 读取 API 配置
- `bot/handlers.py` - 修复 model key 和 reaction 回退逻辑

---

## [2026-01-23] 新增 Typing Indicator 和 Message Reactions 功能

### 新增功能

**Typing Indicator（输入中提示）**
- 在 Bot 处理消息期间显示 "typing..." 状态
- 每 4 秒自动刷新 typing 状态（Telegram 要求）
- 应用于所有消息处理场景：文字消息、图片、文档
- 处理完成或出错时自动停止

**Message Reactions（消息表情反应）**
- 30% 概率对用户消息添加表情反应
- 使用 Claude Haiku (claude-3-5-haiku) 进行轻量级判断
- LLM 根据消息内容选择合适的表情，或决定不反应
- 支持的表情包括：👍 ❤ 🔥 👏 😁 🎉 🤩 💯 等
- 不会干扰主要回复流程（异步执行）

**技术实现**
- `TypingIndicator` 类：使用 asyncio 任务循环发送 typing action
- `maybe_add_reaction` 函数：概率触发 + Haiku LLM 决策
- `_get_reaction_emoji` 函数：调用 Haiku API 选择表情

### 修改文件
- `bot/handlers.py` - 新增 TypingIndicator 类、reaction 函数，集成到消息处理流程

### 注意事项
- Reactions 使用额外的 API 调用（Haiku 模型），成本极低
- 如果 API 调用失败，会静默失败不影响主流程
- 可通过修改 `probability` 参数调整反应频率

---

## [2026-01-23] 新增 /compact 命令 - 上下文压缩功能

### 新增功能

**手动上下文压缩 (/compact)**
- 新增 `/compact` 命令，手动压缩当前对话上下文
- 压缩流程：
  1. 生成当前对话的详细总结（使用 Claude API）
  2. 保存总结到用户目录 (.context_summary.txt)
  3. 清除 session_id，下次消息开始新会话
  4. 新会话系统提示中包含上下文总结，保持对话连续性

**自动上下文压缩**
- 当 Token 使用量达到 150K 时自动触发压缩
- 自动压缩在消息处理完成后检测
- 压缩完成后通知用户

**上下文总结特性**
- 总结包含：主要话题、关键决策、用户偏好、待办事项、语言偏好
- 总结附带会话统计（消息数、Token 数、费用、压缩次数）
- 总结存储在用户目录，重启后仍然有效

### 修改文件
- `bot/session/manager.py` - 新增 compact_session、needs_compaction、end_session 方法
- `bot/user/manager.py` - 新增上下文总结存储方法 (save/get/clear_context_summary)
- `bot/agent/client.py` - 新增 context_summary 参数，系统提示支持上下文总结
- `bot/handlers.py` - 新增 compact_command、_generate_context_summary、_auto_compact_session
- `bot/i18n.py` - 添加 /compact 相关翻译字符串
- `system_prompt.txt` - 添加 {context_summary} 占位符

### 使用说明
```
/compact - 手动压缩上下文（保留对话记忆）
```

### 与 /new 的区别
| 命令 | /new | /compact |
|------|------|----------|
| 清除会话 | ✅ | ✅ |
| 保留统计 | ❌ | ✅ |
| 生成总结 | 简短 | 详细 |
| 上下文继承 | ❌ | ✅ |
| 使用场景 | 完全重新开始 | 上下文满了但想保持连续性 |

### 注意事项
- 自动压缩阈值为 150K tokens（约为 Claude 上下文的 75%）
- 总结生成需要额外 API 调用
- 需要 `docker compose up --build -d` 重新构建

---

## [2026-01-23] 新增 /status 命令 - 显示 Token 使用量和费用统计

### 新增功能

**Usage Statistics Tracking**
- 新增 `/status` 命令，显示当前会话的详细使用统计
- 统计信息包括：
  - Session ID 和消息数
  - API 调用轮次 (turns)
  - Token 使用量（输入/输出/总计，支持 K/M 格式）
  - API 费用统计（USD）
  - 会话活跃时间和剩余时间
  - 当前使用的模型

**Session 数据增强**
- `SessionInfo` 新增字段：`total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `total_turns`
- `AgentResponse` 新增字段：`input_tokens`, `output_tokens`, `cost_usd`, `num_turns`
- 所有消息处理位置都会累计使用统计

### 修改文件
- `bot/session/manager.py` - SessionInfo 添加使用统计字段，update_session 支持 usage 参数
- `bot/agent/client.py` - AgentResponse 添加使用统计字段，从 ResultMessage 提取 usage 信息
- `bot/handlers.py` - 新增 status_command，所有 session 更新调用传递 usage 统计
- `bot/i18n.py` - 添加 /status 相关的翻译字符串

### 使用说明
```
/status - 查看当前会话的 Token 使用量、费用等统计信息
```

### 注意事项
- Token 统计来自 Claude Agent SDK 的 ResultMessage.usage 字段
- 费用统计可能有细微误差，以 Anthropic 账单为准
- 需要 `docker compose up --build -d` 重新构建

---

## [2026-01-22] README 国际化 - 英文版 + 中文版

### 修改内容
- 将 README.md 改为英文版本
- 新增 README_CN.md 中文版本
- 两个版本互相链接，方便切换

### 修改文件
- `README.md` - 英文版本（新内容）
- `README_CN.md` - 中文版本（新增）

---

## [2026-01-22] 新增 AKShare 股票数据 Skill + Skills 使用意识强化

### 新增功能

**AKShare 股票数据查询 Skill**
- 新增 `akshare-stocks` skill，支持 A股、港股、美股数据查询
- 功能包括：
  - 实时行情（股价、涨跌幅、成交量）
  - 历史 K 线数据（日/周/月，支持前复权/后复权）
  - 估值指标（PE、PB、PS、总市值）
  - 财务指标（ROE、ROA、净利率、毛利率）
  - 股东户数变化
- 提供常用股票代码速查表（A股/港股/美股热门股）

**Skills 使用意识强化**
- 更新 system_prompt.txt，要求 Agent 在执行任务前先检查可用的 Skills
- 明确列出常用 Skills 及其使用场景
- 引导 Agent 在股票查询、文档分析等场景主动使用对应 Skill

### 修改文件
- `.claude/skills/akshare-stocks/SKILL.md` - 新增股票数据 skill
- `requirements.txt` - 添加 akshare>=1.14.0 依赖
- `system_prompt.txt` - 新增 Skills System 章节，列出可用 skills 和使用指导

### 注意事项
- 需要 `docker compose up --build -d` 重新构建容器以安装 akshare 依赖
- AKShare 数据有约 15 分钟延迟，非实时交易数据

---

## [2026-01-21] 图片分析功能 + 修复 "No response requested" bug

### Bug 修复

**过滤 Claude 内部消息**
- 修复：Agent 有时会发送 "No response requested." 给用户的问题
- 这是 Claude 的内部消息，表示它认为不需要回复
- 现在这类消息会被自动过滤，不会发送给用户

### 修改文件（Bug 修复）
- `bot/handlers.py` - 新增 `should_skip_response()` 函数过滤内部消息

---

## [2026-01-21] 图片分析功能支持

### 新增功能

**图片分析 (Vision)**
- 用户发送图片时，Agent 可以分析图片内容
- 支持图片 + 文字一起发送，Agent 会结合上下文理解
- 智能判断是否需要保存图片：
  - 用户明确要求保存时：移动到指定或推荐的文件夹
  - 用户只是提供信息时：仅分析不保存（临时文件会自动清理）

**使用方式**
- 发送图片 + "这是什么？" → Agent 分析图片内容
- 发送图片 + "保存到我的图片文件夹" → Agent 保存图片到 images/
- 发送图片（无文字）→ Agent 描述图片并询问需求

### 修改文件
- `bot/handlers.py` - 重写 `handle_photo_message`，下载图片到临时文件，引导 Agent 使用 Read 工具查看
- `system_prompt.txt` - 新增图片分析规则和处理指导

### 技术实现
- 图片保存到用户目录的 `.temp/` 文件夹
- Agent 使用 Read 工具读取图片文件（Claude Code 的 Read 工具支持图片）
- 用户要求保存时，Agent 将文件从临时目录移动到目标目录
- 临时文件会在后续清理中自动删除

---

## [2026-01-18] Sub Agent 任务质量审核与打回机制

### 新增功能

**自动质量审核**
- 新增 `delegate_and_review` 工具，支持委派带自动审核的任务
- 任务完成后自动进行质量评估
- 不符合标准时自动打回重试（最多 10 次）
- 每次打回都向用户发送完整结果 + 打回原因 + 尝试次数

**使用方式**
```
主 Agent 调用 delegate_and_review(
    description="分析文档并写报告",
    prompt="详细分析文档内容...",
    review_criteria="报告需包含：摘要、关键发现、建议，每部分至少200字"
)
```

**审核流程**
1. 主 Agent 使用 `delegate_and_review` 创建任务
2. Sub Agent 在后台执行任务
3. 任务完成后自动发送结果给用户
4. ReviewAgent 评估结果是否符合审核标准
5. 不通过则发送打回通知并自动重试
6. 通过则发送成功通知

**与原有 delegate_task 的区别**
- `delegate_task` - 普通委派，无审核，主 Agent 需手动获取结果
- `delegate_and_review` - 带审核委派，自动审核和打回，自动向用户报告进度

### 新增文件
- `bot/agent/review.py` - ReviewAgent 审核代理，使用 Claude API 评估结果质量

### 修改文件
- `bot/agent/task_manager.py` - SubAgentTask 新增审核相关字段；新增 `create_review_task` 方法
- `bot/agent/tools.py` - 新增 `delegate_and_review` 工具；`set_tool_config` 新增 `delegate_review_callback` 参数
- `bot/agent/client.py` - 新增 `delegate_review_callback` 参数；`allowed_tools` 添加新工具
- `bot/agent/__init__.py` - 导出 ReviewAgent、ReviewResult、create_review_callback
- `bot/handlers.py` - 实现 `delegate_review_callback`；连接 ReviewAgent 和 TaskManager
- `bot/i18n.py` - 新增审核系统相关消息和工具显示名称

### SubAgentTask 新增字段
```python
needs_review: bool = False           # 是否需要审核
review_criteria: str = ""            # 审核标准
retry_count: int = 0                 # 当前重试次数
max_retries: int = 10                # 最大重试次数
retry_history: List[Dict]            # 重试历史记录
original_prompt: str = ""            # 原始 prompt（重试时使用）
```

### 用户体验
- 任务创建后立即返回任务 ID，不阻塞主 Agent
- 用户收到完整的进度报告：
  - `📋 任务结果 [第X次/最多10次]` - 当前结果
  - `🔄 第X次打回` - 打回原因和重试通知
  - `✅ 任务审核通过！` - 最终成功通知
  - `⚠️ 已达到最大重试次数` - 达到上限通知

---

## [2026-01-17] 修复 Agent 无法使用 custom_command 工具的问题

### 问题
- Agent 说已经创建了命令，但实际上没有创建
- 用 `/admin command list` 查看显示没有命令
- Agent 在"假装"完成任务（幻觉）

### 原因
`custom_command_*` 工具虽然在 `tools.py` 中创建了，但没有被添加到 `client.py` 的 `allowed_tools` 列表中。Agent 根本看不到这些工具。

### 修复
在 `allowed_tools` 列表中添加所有 custom_command 工具：
- `mcp__telegram__custom_command_list`
- `mcp__telegram__custom_command_get`
- `mcp__telegram__custom_command_create`
- `mcp__telegram__custom_command_update`
- `mcp__telegram__custom_command_delete`
- `mcp__telegram__custom_command_rename`
- `mcp__telegram__custom_command_list_media`

同时添加了之前遗漏的 task 管理工具：
- `mcp__telegram__get_task_result`
- `mcp__telegram__list_tasks`

### 修改文件
- `bot/agent/client.py` - 在 allowed_tools 列表中添加工具

---

## [2026-01-17] 自定义命令系统增强 - Admin 权限检查 + Agent 设计命令

### 新增功能

**Admin 权限验证**
- 所有自定义命令管理工具（custom_command_*）现在都需要 Admin 权限
- 非 Admin 用户调用这些工具会收到权限拒绝错误
- 权限检查在 MCP 工具层实现，确保安全性

**Agent 驱动的命令创建**
- `/admin command create` 命令现在会委派给 Agent 来设计命令
- Agent 会根据需求描述自动：
  1. 确定合适的命令名称
  2. 选择命令类型（random_media 或 agent_script）
  3. 设计执行脚本或提示词
  4. 调用 custom_command_create 工具创建命令

**两种创建方式都支持**
1. 通过对话：直接告诉 Agent "为用户 xxx 创建一个 xxx 命令"
2. 通过命令：`/admin command create <用户ID> <需求描述>`

**命令类型说明**
- `random_media` - 随机发送媒体文件（语音、图片、视频等）
- `agent_script` - Agent 执行自定义脚本/提示词（可组合使用）

### 使用示例
```
/admin command create <USER_ID> 创建一个反馈命令，用户可以提交反馈保存到文件

Agent 会自动：
- 命名为 /feedback
- 类型设为 agent_script
- 脚本：将反馈内容加时间戳保存到 feedback.txt
```

### 修改文件
- `bot/agent/tools.py` - 添加 _admin_user_ids 全局变量，所有 custom_command 工具增加权限检查
- `bot/agent/client.py` - 新增 admin_user_ids 参数，传递给 set_tool_config
- `bot/handlers.py` - 修改 /admin command create 逻辑，委派给 Agent 设计；传递 admin_user_ids 给 TelegramAgentClient

---

## [2026-01-17] 修复 /admin 帮助文本缺少自定义命令入口

### 问题
- `/admin` 命令的帮助文本中没有显示自定义命令管理选项
- 用户无法发现 `/admin command` 功能

### 修复
- 在 `/admin` 帮助文本末尾添加 "🎯 自定义命令管理" 入口
- 现在用户输入 `/admin` 可以看到 `/admin command` 提示

### 修改文件
- `bot/handlers.py` - 更新 admin_command 帮助文本

---

## [2026-01-17] 自定义命令系统 - 新增 agent_script 类型

### 新增功能
扩展自定义命令系统，支持 Agent 执行脚本类型命令。

**命令类型**：
1. `random_media` - 随机媒体文件发送（原有功能）
2. `agent_script` - Agent 执行自定义脚本（新增）

**agent_script 类型说明**：
- Admin 可以为命令编写执行脚本/指令
- 用户触发命令时，Agent 按脚本执行
- 支持用户输入参数（命令后的文字）
- 可用于：反馈收集、日报生成、自定义查询等

**Agent 工具（Admin 可用）**：
- `custom_command_list` - 列出所有自定义命令
- `custom_command_get` - 查看命令详情（含脚本）
- `custom_command_create` - 创建命令
- `custom_command_update` - 更新命令（描述、脚本、类型）
- `custom_command_delete` - 删除命令
- `custom_command_rename` - 重命名命令
- `custom_command_list_media` - 列出媒体文件统计

**示例**：
```
Admin 创建 /feedback 命令：
- target_user_id: <USER_ID>
- command_type: agent_script
- description: 提交反馈
- script: "将用户的反馈保存到 feedback.txt，加上时间戳，然后确认收到。"

用户发送: /feedback 这个功能很好用！
→ Agent 执行脚本，保存反馈并回复确认
```

### 修改文件
- `bot/custom_command/manager.py` - 增加 script 字段和 agent_script 类型支持
- `bot/agent/tools.py` - 新增 7 个自定义命令管理工具
- `bot/agent/client.py` - 传递 custom_command_manager 参数
- `bot/handlers.py` - agent_script 类型命令执行逻辑
- `system_prompt.txt` - 添加自定义命令工具使用说明

---

## [2026-01-17] 新增自定义命令系统

### 新增功能
Admin 可以为特定用户创建自定义命令，实现个性化功能。

**核心功能**：
- Admin 为指定用户创建专属命令（如为 Yumi 创建 `/yumi`）
- 支持随机媒体类型命令（语音、图片、视频、文件）
- 平衡模式：优先发送发送次数少的文件，保持均匀分布
- 发送统计：记录每个文件的发送次数和最后发送时间

**Admin 命令**：
- `/admin command list` - 查看所有自定义命令
- `/admin command create <用户ID> <命令名> <描述>` - 创建命令
- `/admin command delete <命令名>` - 删除命令
- `/admin command rename <旧名> <新名>` - 重命名命令
- `/admin command info <命令名>` - 查看命令详情
- `/admin command files <命令名>` - 查看媒体文件列表

**添加媒体文件**：
- Admin 发送 `/<命令名>` 进入添加模式
- 发送语音/图片/视频/文件即可添加
- 发送 `/cancel` 退出添加模式

**用户使用**：
- 用户在 `/help` 中看到专属命令
- 发送命令后随机收到一个媒体文件

**数据存储**：
```
admin用户目录/custom_commands/
├── commands.json        # 命令配置
├── yumi/                # yumi 命令的媒体文件夹
│   ├── voice_xxx.ogg
│   └── stats.json       # 发送统计
└── other_cmd/
```

### 新增文件
- `bot/custom_command/__init__.py`
- `bot/custom_command/manager.py` - CustomCommandManager 类

### 修改文件
- `bot/handlers.py` - 集成自定义命令处理、媒体处理、/help 显示

---

## [2026-01-17] 新增用户偏好记忆功能

### 新增功能
Agent 现在会记住用户的个人偏好和要求，存储在 `preferences.txt` 文件中。

**功能说明**：
- 用户可以告诉 Agent 自己的偏好（语气、风格、记住的事情等）
- Agent 会自动保存到 `preferences.txt`
- 每次对话开始时，Agent 会读取偏好文件
- 支持添加、更新、删除偏好
- 新旧偏好冲突时自动覆盖

**触发场景**：
- "记住我喜欢..." / "remember that..."
- "说话简洁一点" / "speak more casually"
- "以后不要..." / "don't do that anymore"
- "忘掉之前说的..." / "forget that rule"

**文件格式**：
```
[语气/Tone]
- 说话要简洁直接

[记住的事情/Remember]
- 用户喜欢喝咖啡

[其他要求/Other]
- 回复时不要用表情符号
```

### 修改文件
- `system_prompt.txt` - 添加用户偏好记忆机制说明

---

## [2026-01-17] 修复新用户注册逻辑 & 添加用户信息记录 & Agent 友好称呼

### 问题背景
- `allow_new_users = false` 设置形同虚设，新用户仍然会被自动注册
- 原因：`can_access` 函数先调用 `get_user_config()`，该方法会自动创建用户配置
- 然后检查用户是否存在，此时已经被创建了，检查永远为 True
- 用户 <USER_ID> 就是这样被意外注册的
- Agent 跟用户聊天时只显示 User ID，感觉冷漠

### 修复内容

**1. 修复 can_access 逻辑**
- 新增 `user_exists()` 方法，仅检查用户是否存在，不自动创建
- `can_access` 先调用 `user_exists()` 检查，不存在则根据 `allow_new_users` 决定
- 真正实现了"不允许新用户自动注册"的功能

**2. 记录用户 Telegram 信息**
- `UserConfig` 新增 `username` 和 `first_name` 字段
- 用户每次交互时自动更新用户名（用户名可能会变化）
- 新增 `create_user()` 和 `update_user_info()` 方法
- 用户名变化时自动清除 Agent 缓存以使用新名称

**3. 未授权用户处理**
- 新增 `handle_unauthorized_user()` 函数
- 未授权用户尝试访问时：
  - 记录用户信息到 users.json（但 enabled=false）
  - 通知所有管理员（包含用户 ID、用户名、名字）
  - 给用户发送提示，引导联系 Twitter: https://x.com/yrzhe_top

**4. Agent 友好称呼用户**
- `TelegramAgentClient` 新增 `user_display_name` 参数
- `system_prompt.txt` 添加用户称呼规则
- Agent 会用用户名或名字称呼用户，而不是冷冰冰的 ID
- 优先使用 username，如果没有则用 first_name

### 修改文件
- `bot/user/manager.py` - 新增 user_exists()、create_user()、update_user_info() 方法，UserConfig 添加 username/first_name 字段
- `bot/handlers.py` - 修复 can_access 逻辑，新增 handle_unauthorized_user()，传递 user_display_name
- `bot/agent/client.py` - 新增 user_display_name 参数
- `system_prompt.txt` - 添加用户称呼规则

### 管理员操作
- 收到新用户通知后，使用 `/admin enable <user_id>` 启用用户
- 使用 `/admin users` 查看所有用户（包含用户名信息）

---

## [2026-01-16] 添加对话日志和会话总结功能

### 新增功能

**对话日志记录（txt 格式）**
- 每次用户和 Agent 对话时，自动记录到人类可读的 txt 文件
- 日志保存在用户目录下的 `chat_logs/` 文件夹
- 每个会话一个独立的日志文件，文件名包含时间戳和会话 ID
- 日志格式清晰，包含时间戳、用户消息、Agent 回复

**会话超时改为 1 小时**
- 默认会话超时时间从 30 分钟改为 1 小时
- 用户超过 1 小时不聊天自动退出 Agent 对话
- 对话日志会保留，不会因超时而丢失

**/new 命令对话总结**
- 使用 /new 命令时会自动生成对话总结
- 使用 Claude API 智能总结对话的主要内容和关键点
- 总结保存在 `chat_summaries/` 文件夹
- 原始对话记录会附加在总结文件末尾
- 如果 API 调用失败，会保存简单的统计信息

### 修改文件
- `bot/session/chat_logger.py` - 新增对话日志记录器
- `bot/session/manager.py` - 修改默认超时时间为 1 小时（3600 秒）
- `bot/session/__init__.py` - 导出 ChatLogger
- `bot/__init__.py` - 导出 ChatLogger
- `bot/handlers.py` - 集成对话日志记录，增强 /new 命令

### 配置说明
- 如需修改超时时间，编辑 `config.json` 中的 `session_timeout_minutes`
- 默认值现在是 60 分钟

---

## [2026-01-14] 修复 Sub Agent 尝试写入 /tmp 目录被拒绝的问题

### 问题背景
- Sub Agent 执行定时任务时尝试将报告写入 `/tmp/` 目录
- 安全检查拒绝了在用户工作目录外的写入操作
- Agent 无法创建文件，导致任务"文件访问失败"

### 修复内容
- 在 Sub Agent 的 system prompt 中添加明确的文件路径规则
- 告知 Agent 只能使用 `reports/`, `analysis/`, `documents/`, `output/` 等目录
- 明确禁止使用 `/tmp`, `/var` 等系统目录
- 提供正确的路径使用示例

### 修改文件
- `bot/handlers.py` - 更新 Sub Agent system prompt

---

## [2026-01-14] 修复 send_telegram_file 文件发送失败的问题

### 问题背景
Agent 创建文件后使用 `send_telegram_file` 工具发送时经常失败，原因：
- Agent 创建文件时可能使用子目录路径（如 `reports/file.pdf`）
- 发送时可能只传递文件名（如 `file.pdf`）
- 原有的路径解析逻辑只尝试两种情况，找不到文件就直接返回 False
- 没有详细的错误日志，Agent 只能猜测失败原因

### 修复内容

**改进路径搜索逻辑**
- 尝试多种路径组合：
  1. 相对于用户目录的原始路径
  2. 绝对路径（如果是绝对路径）
  3. 用户目录根目录下的同名文件
  4. 常见子目录下搜索：reports、analysis、documents、uploads、output

**添加详细日志**
- 文件未找到时记录尝试过的所有路径
- 文件发送成功时记录实际使用的路径
- Telegram API 调用失败时记录具体错误

**异常处理**
- 包装 `bot.send_document` 调用，捕获 Telegram API 异常
- 失败时返回 False 而非抛出异常

### 修改文件
- `bot/handlers.py` - 重写 `send_file` 回调函数

---

## [2026-01-13] Sub Agent 交互架构优化 - 确保主 Agent 获取所有上下文

### 问题背景
原有设计中，Sub Agent 完成任务后会直接通过 `on_task_complete` 回调将结果发送给用户，绕过了主 Agent。这导致：
- 主 Agent 无法获知 Sub Agent 的执行结果
- 用户收到的信息缺乏主 Agent 的整合和解释
- 主 Agent 失去了对话上下文

### 修改内容

**移除直接用户通知**
- `handlers.py` 中的 `on_task_complete` 回调不再直接发送消息给用户
- 改为仅记录日志，由主 Agent 负责获取和传达结果

**新增任务管理工具**
- `get_task_result(task_id)` - 让主 Agent 获取指定 Sub Agent 任务的结果
- `list_tasks()` - 让主 Agent 查看所有已委派任务的状态

**更新 delegate_task 工具描述**
- 明确说明主 Agent 必须使用 `list_tasks` 检查状态，使用 `get_task_result` 获取结果
- 主 Agent 负责向用户报告 Sub Agent 的发现

### 新的交互流程
```
用户 → 主 Agent → delegate_task → Sub Agent 执行
                                        ↓
主 Agent ← list_tasks/get_task_result ← 结果存储
    ↓
用户 ← 主 Agent 整合报告
```

### 修改文件
- `bot/handlers.py` - 简化 on_task_complete，传递 task_manager
- `bot/agent/tools.py` - 新增 get_task_result、list_tasks 工具，更新 delegate_task 描述
- `bot/agent/client.py` - 添加 task_manager 参数支持
- `bot/agent/task_manager.py` - 新增 get_task、get_all_tasks 方法

### 设计原则
- Sub Agent 只能与主 Agent 通信，不能直接与用户通信
- 主 Agent 保持所有上下文，负责向用户报告
- 确保对话的连贯性和完整性

---

## [2026-01-11] 定时任务扩展 - 支持多种周期类型和执行次数限制

### 新增功能

**周期类型扩展**
- `daily` - 每天执行（原有功能）
- `weekly` - 每周指定星期执行，如 `weekly 09:00 mon,wed,fri`
- `monthly` - 每月指定日期执行，如 `monthly 10:00 15`
- `interval` - 按间隔执行，如 `interval 30m`、`interval 2h`、`interval 1d`
  - 支持 `--start HH:MM` 指定首次执行时间，如 `interval 1h --start 22:00`
  - 也支持完整时间 `--start YYYY-MM-DDTHH:MM`
- `once` - 一次性任务，如 `once 2025-02-01 14:00`

**执行次数限制**
- 可选 `--max N` 参数限制执行次数
- 达到上限后任务自动禁用（保留配置）
- 可通过 `/schedule reset <id>` 重置并重新启用

**新增命令**
- `/schedule reset <id>` - 重置已完成任务的执行计数并重新启用
- `/schedule info <id>` - 查看任务详细信息（包含完整 prompt）

### 修改文件
- `bot/schedule/manager.py` - 扩展 ScheduledTask 数据模型，新增调度逻辑
- `bot/schedule/__init__.py` - 导出新常量
- `bot/handlers.py` - 更新命令解析，支持新格式
- `bot/agent/tools.py` - 更新 Agent 工具参数
- `bot/i18n.py` - 更新帮助文本

### 向后兼容
- 现有任务自动视为 `daily` 类型
- 旧命令格式 `/schedule add <id> HH:MM 名称` 继续有效

---

## [2026-01-11] /ls 命令支持直接发送文件

### 新增功能
- `/ls <文件路径>` 如果指定的是文件而非目录，直接发送该文件到 Telegram
- 例如：`/ls financial_scripts/report.md` 会直接发送这个文件

### 修改文件
- `bot/handlers.py` - ls 命令增加文件判断逻辑

---

## [2026-01-11] 新增规划类 Skills（头脑风暴、写计划、执行计划）

### 新增功能
- **brainstorming** - 头脑风暴技能：帮助用户将想法转化为完整计划
  - 一次问一个问题，逐步理清需求
  - 提供 2-3 个方案供选择
  - 分段展示计划，每段验证
- **writing-plans** - 写计划技能：将需求拆解为详细的执行步骤
  - 每个步骤都是小而具体的动作
  - 包含文件路径、验证方法
  - 保存到 `plans/` 目录
- **executing-plans** - 执行计划技能：按步骤执行计划
  - 逐个任务执行，报告进度
  - 遇到问题立即停止询问
  - 完成后汇总成果

### 新增文件
- `.claude/skills/brainstorming/SKILL.md`
- `.claude/skills/writing-plans/SKILL.md`
- `.claude/skills/executing-plans/SKILL.md`

### 说明
- 基于 superpowers 技能包改编
- 移除了 git、bash、TDD 等开发专用功能
- 适配 Telegram Bot 的文件管理和 AI 助手场景

---

## [2026-01-11] 修复 Agent 定时任务工具不可用的问题（第二次修复）

### 问题
- Agent 报告 "schedule_list 等定时任务管理工具不可用"
- 原因：使用 `docker compose restart` 只重启容器，不会更新代码
- Docker 容器内的代码仍是旧版本，没有 schedule_manager 参数

### 修复
- 使用 `docker compose up --build -d` 重新构建镜像
- 确认容器内代码已更新

### 重要教训
- **代码修改后必须用 `docker compose up --build -d`**
- `docker compose restart` 只能用于配置文件（config.json）修改

---

## [2026-01-11] 修复 Agent 不知道自己有定时任务管理工具的问题

### 问题
- Agent 说"schedules 目录我无法直接访问"，让用户手动用 /schedule 命令
- 原因：system_prompt.txt 没有告诉 Agent 它有 schedule_* 工具

### 修复
- 在 system_prompt.txt 中添加了定时任务管理工具的说明
- 明确告诉 Agent 可以直接用 schedule_update 修改 prompt
- 不需要引导用户用命令，Agent 自己就能操作

### 修改文件
- `system_prompt.txt` - 添加 schedule_* 工具说明

### 关联
- 修复 [2026-01-11] Agent 定时任务控制功能的配套问题

---

## [2026-01-11] Agent 定时任务控制 & 任务结束强制发送文件

### 新增功能
- **Agent 定时任务完全控制**：Agent 可通过 5 个新工具管理定时任务
  - `schedule_list` - 列出所有定时任务
  - `schedule_get` - 获取任务详情（含 prompt）
  - `schedule_create` - 创建新任务（带格式校验）
  - `schedule_update` - 更新任务属性
  - `schedule_delete` - 删除任务
- **定时任务操作日志**：所有操作记录到 `operation_log.jsonl`，删除时保存完整快照便于恢复
- **任务结束强制发送文件**：任务完成后自动检测并发送新生成的文件
  - 排除临时文件（.tmp, .log, __pycache__/ 等）
  - ≤5 个文件逐个发送，>5 个打包 zip 发送后删除

### 新增文件
- `bot/file_tracker.py` - 文件变更追踪器

### 修改文件
- `bot/schedule/manager.py` - 添加操作日志、验证方法、update_task
- `bot/agent/tools.py` - 添加 5 个定时任务工具
- `bot/agent/client.py` - 集成 FileTracker，添加 schedule_manager
- `bot/handlers.py` - 传入 schedule_manager 到 Agent
- `main.py` - 定时任务执行集成 FileTracker
- `bot/i18n.py` - 添加新工具的显示名称

---

## [初始版本] 产品功能概述

### 核心功能

#### 1. AI 助手对话
- 基于 Claude Agent SDK 的智能对话
- 支持会话上下文记忆（30 分钟超时）
- 支持会话恢复（resume）

#### 2. 文件管理
- 用户独立的文件存储空间
- 存储配额管理（默认 5GB）
- 文件上传、下载、删除
- 目录浏览（/ls）

#### 3. 定时任务
- 用户自定义定时任务
- 支持时区设置
- 通过 Sub Agent 执行任务
- 命令：/schedule add/del/enable/disable/edit/list/timezone

#### 4. 自定义技能（Skills）
- 用户可上传自定义技能包
- 技能验证和安全检查
- 命令：/skill list/del/info

#### 5. 环境变量管理
- 用户独立的环境变量
- 命令：/env set/del

#### 6. Python 包管理
- 用户独立的虚拟环境
- 命令：/packages list/install/init

#### 7. 管理员功能
- 用户管理（启用/禁用）
- 配额管理
- 会话监控
- 统计和历史查看
- 命令：/admin users/quota/enable/disable/sessions/stats/history

### Agent 可用工具
- `send_telegram_message` - 发送消息
- `send_telegram_file` - 发送文件
- `web_search` - 网络搜索（DuckDuckGo）
- `web_fetch` - 获取网页内容
- `pdf_to_markdown` - PDF 转 Markdown（Mistral OCR）
- `delete_file` - 删除文件
- `compress_folder` - 压缩文件夹
- `delegate_task` - 委派任务给 Sub Agent
- `schedule_*` - 定时任务管理（5 个工具）
- Read/Write/Edit/Glob/Grep - 文件操作
- Skill - 执行技能

### 技术架构
- Telegram Bot（python-telegram-bot）
- Claude Agent SDK
- Docker 容器化部署
- 多用户隔离
- MCP 工具集成
