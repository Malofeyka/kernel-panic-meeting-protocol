/**
 * Зеркало Pydantic-схем бэкенда. При изменении контракта правим вместе:
 * - backend/app/schemas/api_contract.py, protocol.py, transcription.py
 * - docs/api/openapi.json, docs/api/frontend_integration.md
 */

export type ProcessingStep =
  | 'idle'
  | 'uploading'
  | 'transcribing'
  | 'extracting'
  | 'cross_checking'
  | 'ready'
  | 'refining'
  | 'failed'

// --- protocol.py ---

export type ItemOrigin = 'ai' | 'manual'

export type ActionItemStatus =
  'valid' | 'missing_date' | 'missing_assignee' | 'missing_assignee_and_date'

export interface Decision {
  /** Новое решение можно отправить без id — сервер присвоит */
  id?: string
  text: string
  quote: string | null
  source_start: number | null
  source_end: number | null
  origin: ItemOrigin
}

export interface ActionItem {
  id?: string
  task: string
  /** Фамилия И.О. или организация */
  assignee: string | null
  assignee_role: string | null
  /** Как исполнитель прозвучал в речи */
  assignee_raw: string | null
  /** ДД.ММ.ГГГГ */
  due_date: string | null
  /** Как срок прозвучал в речи */
  due_date_raw: string | null
  is_recurring: boolean
  /** Вычисляет сервер, клиент только отображает */
  status: ActionItemStatus
  quote: string | null
  source_start: number | null
  source_end: number | null
  origin: ItemOrigin
}

export interface AgendaItem {
  item_number: number
  topic: string
  reporter: string | null
  decisions: Decision[]
  action_items: ActionItem[]
}

export type Severity = 'high' | 'medium' | 'low'

export interface GapIssue {
  type: string
  severity: Severity
  description: string
  agenda_item_number: number | null
  action_item_id: string | null
  context_quote: string | null
  source_start: number | null
}

export interface Contradiction {
  id: string
  scope: 'meeting' | 'archive'
  description: string
  action_item_ids: string[]
  quotes: string[]
  archive_reference: string | null
}

export interface Risk {
  id: string
  type: string
  severity: Severity
  description: string
  action_item_ids: string[]
  archive_reference: string | null
}

export interface AnalyticsReport {
  gaps: GapIssue[]
  contradictions: Contradiction[]
  risks: Risk[]
}

export interface RevisionCycleState {
  current_cycle: number
  max_cycles: number
  is_escalated_to_manual: boolean
}

export interface Attendee {
  full_name: string
  /** Фамилия И.О.; пустая строка — сервер вычислит */
  short_name: string
  position: string | null
}

export interface ProtocolMetadata {
  meeting_title: string
  /** ДД.ММ.ГГГГ */
  meeting_date: string
  protocol_number: string | null
  chairperson: string | null
  secretary: string | null
  attendees: Attendee[]
}

export interface ProtocolDraft {
  session_id: string
  metadata: ProtocolMetadata
  agenda_items: AgendaItem[]
  analytics: AnalyticsReport
  revision_cycle: RevisionCycleState
}

// --- transcription.py ---

export interface TranscriptionSegment {
  /** секунды */
  start: number
  end: number
  text: string
}

export interface MeetingTranscription {
  model: string
  source: string
  text: string
  segments: TranscriptionSegment[]
}

// --- api_contract.py ---

export interface SessionCreateRequest {
  meeting_title?: string | null
  /** ДД.ММ.ГГГГ */
  meeting_date?: string | null
  protocol_number?: string | null
  chairperson?: string | null
  secretary?: string | null
}

export interface SessionCreateResponse {
  session_id: string
  status: ProcessingStep
  created_at: string
}

export interface SessionSummary {
  session_id: string
  meeting_title: string
  meeting_date: string
  status: ProcessingStep
  created_at: string
  updated_at: string
}

export interface UploadedFilesInfo {
  audio: string | null
  transcript: string | null
  agenda: string | null
  attendees: string | null
  template: string | null
  archive: string[]
}

export interface ExportInfo {
  file_name: string
  download_url: string
  warnings: string[]
  generated_at: string
}

export interface SessionDetails {
  session_id: string
  meeting_title: string
  meeting_date: string
  status: ProcessingStep
  progress_percent: number
  current_step_description: string
  error_message: string | null
  /** Проект сформирован — можно открывать редактор */
  has_draft: boolean
  has_transcript: boolean
  files: UploadedFilesInfo
  export: ExportInfo | null
  /** Замечания разбора повестки, участников, архива */
  input_warnings: string[]
  created_at: string
  updated_at: string
}

export interface SessionStatusResponse {
  session_id: string
  status: ProcessingStep
  progress_percent: number
  current_step_description: string
  error_message: string | null
  updated_at: string
}

export type RefineAction = 'ai_regenerate' | 'manual_save'

export interface RefineRequest {
  action: RefineAction
  user_feedback?: string | null
  updated_metadata?: ProtocolMetadata | null
  updated_agenda_items?: AgendaItem[] | null
}

export interface RefineResponse {
  session_id: string
  /** refining — ИИ-правка идёт в фоне, опрашивать /status */
  status: ProcessingStep
  updated_draft: ProtocolDraft
  revision_cycle: RevisionCycleState
  message: string
}

export interface ExportResponse extends ExportInfo {
  session_id: string
}

export interface HealthResponse {
  status: string
  service: string
  isolated_mode: boolean
  max_revision_cycles: number
}

/** Комплект файлов для POST /api/sessions/{id}/upload. Нужна запись или стенограмма */
export interface SessionFiles {
  audio?: File | null
  transcript?: File | null
  agenda?: File | null
  attendees?: File | null
  template?: File | null
  archive?: File[]
}

export interface UploadProgress {
  loaded: number
  total: number
}
