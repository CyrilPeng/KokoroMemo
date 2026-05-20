export type StateColumn = {
  column_id: string
  column_key: string
  name: string
  description?: string
  required?: boolean
  max_chars?: number
}

export type StateTable = {
  table_id: string
  table_key: string
  name: string
  description?: string
  max_prompt_rows: number
  prompt_priority: number
  columns: StateColumn[]
}

export type StateRow = {
  row_id: string
  table_key: string
  values: Record<string, string>
  priority: number
  confidence: number
  source: string
  updated_at?: string
}

export type ConversationConfig = {
  conversation_id: string
  profile_id: string
  table_template_id?: string | null
  mount_preset_id?: string | null
  memory_write_policy: string
  state_update_policy: string
  injection_policy: string
  retrieval_profile_id?: string
  created_from_default?: boolean
}

export type StateDiagnostic = {
  label: string
  type: 'default' | 'info' | 'success' | 'warning' | 'error'
}
