# Nanorole Single-Role Studio Design

## Goal

Nanorole 的下一阶段目标是成为一个本地优先的单角色长期陪伴与角色扮演工作台。

必须能力：

- 单角色会话稳定、可持久化、可恢复。
- 角色世界观、角色设定、用户长期记忆、关系状态和会话摘要是核心上下文。
- 用户可以查看、编辑、删除长期记忆。
- 开发者可以解释一次回复用了哪些记忆、关系状态、世界观和会话摘要。
- 页面从“能聊天的 demo”升级为“能创作、调试、观察状态”的本地工作台。

可选能力：

- 单角色任务、剧情、事件、章节、线索推进。
- 这些能力只在 session 显式启用时参与上下文，普通陪伴会话不承担剧情状态。

明确暂缓：

- 多角色对话。
- 多角色 director/orchestrator。
- 回合制剧本杀。
- 角色间私有知识隔离。
- 投票、胜负、计分等完整剧本杀规则。
- Graph RAG、向量库、STT/TTS、云同步、账号系统。

## Current State

当前仓库主干已经具备比早期 roadmap 更靠后的能力：

- Python runtime 使用 FastAPI，核心入口在 `python/nanorole_runtime/src/nanorole_runtime/api.py`。
- SQLite migration runner 已存在于 `python/nanorole_runtime/src/nanorole_runtime/storage.py`。
- 持久会话、消息、记忆、关系状态、摘要、事件日志已经落地。
- `CompanionTurnPipeline` 已经从 `SessionManager` 中抽出一部分单角色回合流程。
- `SessionManager` 仍然承担过多职责：会话创建、scenario 创建、story state、event apply、message persistence、context preview、turn dispatch、memory extraction、summary update、logging。
- TypeScript demo 仍是单文件内嵌 HTML 字符串，`packages/demo/src/pages.ts` 同时承载 chat、memory、logs 三个页面。
- 当前测试基线稳定：`uv run pytest` 通过 75 个 Python 测试，`corepack yarn test` 通过 26 个 TypeScript 测试。

这说明下一步不应该先继续堆多人剧情功能，而应该收窄产品主路径，把单角色内核的边界、数据模型和工作台体验稳定下来。

## Product Model

Nanorole 的主路径只有一种角色关系：

```text
local user <-> one companion role
```

每个 session 可以是以下两种形态之一：

- `companion`: 默认会话。只有角色、世界观、长期记忆、关系状态、会话摘要、消息历史。
- `story`: 单角色剧情会话。包含 `companion` 的全部能力，并额外启用任务、剧情阶段、事件、线索等 story state。

`story` 不是多人模式。即使 story package 未来能描述更多角色，第一阶段 runtime 也只选择一个 active companion role，并把其他人物作为世界观或剧情事实，而不是参与者。

## Required State Layers

### Role Package

角色包继续使用 `examples/roles/<role>/character.yaml`。

职责：

- 角色身份：`id`, `name`, `version`
- 稳定角色设定：`world`, `background`, `persona`
- 行为方向：`goals`, `style`, `safety_rules`
- 默认开场：`opening`

角色包不是运行时记忆，也不是会话状态。

### World Context

世界观是每个角色和可选剧情层共同使用的背景知识。

第一阶段不新增独立世界包，先把 `RolePackage.world` 作为必需世界观入口，并在 context package 中明确为 `world_context`。

后续可以演进为：

```yaml
world:
  id: brass-city
  summary: A brass city where public clocks regulate memory archives.
  rules:
    - Public clocks define the official archive schedule.
  locations:
    - name: Forgotten Observatory
      summary: An abandoned observatory above the old archive wing.
```

但当前计划只做结构边界，不做 YAML schema 扩张。

### Session State

Session state 是运行时事实：

- session id
- user id
- companion id
- role id/name/version
- mode: `companion` 或 `story`
- title/status/timestamps
- persisted messages
- latest summary id/text

Session state 不应该直接保存长期用户事实。用户长期事实属于 memory。

### Memory State

Memory 继续使用当前 `MemoryStore` 和 `memories` 表。

职责：

- 用户长期偏好。
- 稳定用户事实。
- 重要事件。
- 明确边界。
- 用户与角色的长期关系片段。

Memory 必须保持用户可控：inspect、add、edit、archive、delete。

Memory 写入继续遵守保守策略：

- 临时情绪不写。
- 敏感信息默认不写。
- “不要记住”必须阻止写入。
- 用户纠正旧事实时，旧 memory 应归档或更新。

### Relationship State

Relationship state 是用户和该 companion 的长期关系摘要，不是普通 memory 的堆叠。

当前 `relationship_states` 表可继续使用：

- `summary`
- `familiarity`
- `trust`
- `preferred_address`
- `communication_style`

下一阶段要把 relationship state 作为 context package 中的显式字段，而不是在 prompt 字符串里隐式拼接。

### Context Package

Context package 是一次模型调用前的可解释上下文对象。

建议内部结构：

```python
@dataclass(frozen=True)
class ContextPackage:
    session_id: str
    mode: str
    role: RolePackage
    world_context: str
    relationship: RelationshipState | None
    selected_memories: list[MemoryRecord]
    session_summary: str | None
    recent_messages: list[ChatMessage]
    story: StoryContext | None
    model_messages: list[dict[str, str]]
```

`ContextAssembler` 应返回 `ContextPackage`，API 再从中暴露 preview 所需字段。这样 context preview 不需要重新解析 prompt 字符串。

### Event Stream

所有重要状态变化都应该进入 `session_events`：

- session created/updated
- user message persisted
- context built
- memory retrieval
- assistant message persisted
- memory extraction result/failure
- summary update result/failure
- optional story event appended

事件日志用于解释和调试，不作为主状态读取路径。

## Optional Story Layer

Story layer 是 session 的可选附加能力，不是单角色主路径的必需条件。

第一阶段 story layer 的目标是“单角色任务推进”，不是多人剧本杀：

- `story_enabled`: session 是否启用剧情层。
- `current_scene`: 当前场景文字。
- `current_phase`: 当前阶段，例如 `opening`, `investigation`, `reflection`, `ending`。
- `objectives`: 当前任务目标。
- `facts`: 已公开剧情事实。
- `clues`: 可揭示线索。
- `events`: 用户行动、角色回复后的剧情变化、线索揭示、任务完成。

上下文规则：

- 默认 `companion` session 不加载 story context。
- `story` session 加载 current scene、objectives、public facts、revealed clues、recent story events。
- hidden facts 第一阶段只用于调试和作者视图，不进入模型上下文，除非后续明确设计单角色“主持人知道但角色不说”的模式。

当前已有 `story_states` 和 `scene_events` 表，可以先复用。第一批不做破坏性迁移，只在 API 和工作台层把 story 能力标成 optional。

## Runtime Architecture

目标边界：

```text
api.py
  -> SessionManager
       -> SessionStore
       -> MessageStore
       -> RuntimeEventStore
       -> CompanionTurnPipeline
       -> ContextAssembler
       -> MemoryStore / MemoryExtractor
       -> SummaryStore
       -> Optional StoryService
```

### `SessionManager`

保留为 runtime facade。

职责：

- 组合服务。
- 暴露 API 需要的用例方法。
- 处理兼容性参数，例如旧的 `role_id`。

不再直接承担：

- SQL 细节。
- story state patch 细节。
- context preview 结构转换。
- 大段 scenario/multi-role dispatch。

### `SessionStore`

新增模块：`python/nanorole_runtime/src/nanorole_runtime/session_store.py`

职责：

- 创建、读取、更新 session row。
- 读取 session 列表。
- 持久化和读取 messages。
- 持久化 session events。
- 处理 `SessionState` 和数据库 row 的转换。

### `CompanionTurnPipeline`

继续作为单角色回合流水线。

目标步骤：

1. record `turn_started`
2. persist user message
3. build `ContextPackage`
4. mark selected memories used
5. stream model output
6. persist assistant message
7. schedule memory extraction
8. schedule summary update
9. write request log
10. record `turn_completed`

Story session 也应走这条 pipeline，只是传入 `story_context`。

### `StoryService`

新增模块：`python/nanorole_runtime/src/nanorole_runtime/story.py`

职责：

- 创建单角色 story state。
- 获取 story state。
- append story event。
- 根据 event 更新 state。
- 构造可进入模型上下文的 sanitized story context。

第一批先把现有 `SessionManager` 里的 `_persist_story_state`, `_apply_story_event_to_state`, `_load_scene_events`, `_visible_story_context` 移入该服务。

### Context API

`GET /v1/sessions/{sessionId}/context-preview` 应返回结构化信息：

```json
{
  "sessionId": "2e8a0df4c7f1463a9f8f48f7b2cdb4ad",
  "mode": "companion",
  "systemPrompt": "You are running an emotional companion character for Nanorole. Stay grounded in the role package.",
  "messages": [],
  "context": {
    "world": "A city of brass towers.",
    "relationship": {},
    "selectedMemories": [],
    "sessionSummary": "The user is planning Nanorole as a single-role studio.",
    "story": null
  }
}
```

保留旧字段 `usedMemories` 和 `usedStory` 一段时间，避免 demo 立即破坏。

## API Direction

保持现有接口兼容：

```json
{
  "role_id": "clockwork-sage"
}
```

新增推荐创建格式：

```json
{
  "mode": "companion",
  "roleId": "clockwork-sage"
}
```

可选 story session：

```json
{
  "mode": "story",
  "roleId": "clockwork-sage",
  "story": {
    "currentScene": "The brass observatory is quiet.",
    "currentPhase": "opening",
    "objectives": ["Find why the clock stopped."]
  }
}
```

兼容现有 `mode: "scenario"`：

- 第一批不删除。
- demo 不再把它作为主入口。
- 后续可以把单角色 scenario package 映射为 `mode: "story"`。

## Workbench Direction

当前页面最大问题不是样式，而是信息架构不清楚。

建议工作台分成四个固定区域：

- Left rail: roles, sessions, create/resume。
- Main: chat transcript 和 composer。
- Right inspector: relationship、memory picks、session summary、world/story state。
- Bottom/debug drawer: raw context preview、events、logs。

页面先不引入重型框架。第一阶段可以继续用 TypeScript 生成 HTML，但必须拆文件：

```text
packages/demo/src/pages/chatPage.ts
packages/demo/src/pages/memoriesPage.ts
packages/demo/src/pages/logsPage.ts
packages/demo/src/pages/shared.ts
packages/demo/src/workbench/client.ts
```

如果后续 UI 继续复杂，再迁移到 Vite/React。当前阶段不做前端框架迁移。

## Migration Strategy

第一批尽量不做破坏性数据库迁移。

允许新增：

- API response 字段。
- 内部 dataclass。
- service/repository 模块。
- demo 页面拆分。

避免第一批做：

- 删除 `scenario` 接口。
- 删除 `session_participants` 表。
- 改写已有表主键。
- 强制迁移旧 story state JSON。

## Testing Strategy

Python:

- Store 层测试 session/message/event CRUD。
- Context package golden tests。
- Single-role turn pipeline tests。
- Relationship and memory context selection tests。
- Optional story context inclusion/exclusion tests。
- API backward compatibility tests。

TypeScript:

- demo server proxy tests。
- chat page smoke tests。
- pages split 后 HTML 包含必要元素。
- context preview inspector client helpers tests。

Manual verification:

- `uv run pytest`
- `corepack yarn test`
- `corepack yarn build`
- Start local demo and create companion session。
- Add memory, preview context, send message, verify event/log output。

## Rollout

### Phase 1: Single-Role Foundation

- 抽 `SessionStore`。
- 抽 `StoryService`，只作为 optional layer。
- 让 `ContextAssembler` 返回结构化 `ContextPackage`。
- 保持所有现有 API 和测试通过。

### Phase 2: Workbench Reshape

- 拆分 `pages.ts`。
- Chat 页改成单角色默认工作台。
- 右侧 inspector 显示 world、relationship、selected memories、summary、optional story。
- Context preview 从 memory 页移到 chat inspector 或 debug drawer。

### Phase 3: Memory And Relationship Quality

- 加强 memory extraction fixtures。
- 加强 relationship update policy。
- 给 memory retrieval 增加可解释分数。
- UI 暴露 memory 使用原因和最近使用时间。

### Phase 4: Optional Single-Role Story

- 新增 story session 创建入口。
- 支持 objective、phase、event、clue 的单角色 story state。
- 支持手动 append event。
- 后续再考虑模型辅助事件抽取，但不能影响普通 companion session。

## Self-Review

- 本设计不要求多人对话、director 或回合制规则。
- 本设计保留现有兼容接口，第一批不做破坏性迁移。
- 必需能力和可选 story layer 已分开。
- 第一批实现重点是边界和可解释性，不是继续增加剧情复杂度。
