// 会话状态板的领域类型。

export interface StateBoardField {
  field_id?: string | null
  template_id: string
  tab_id: string
  field_key: string
  label: string
  field_type?: string
  description?: string
  ai_writable?: boolean
  include_in_prompt?: boolean
  sort_order?: number
  default_value?: string
  options?: Record<string, unknown>
  status?: string
}

export interface StateBoardTab {
  tab_id?: string | null
  template_id: string
  tab_key: string
  label: string
  description?: string
  sort_order?: number
  fields: StateBoardField[]
  item_count?: number
}

export interface StateBoardTemplate {
  template_id?: string | null
  name: string
  description?: string
  is_builtin?: boolean
  status?: string
  tabs: StateBoardTab[]
}

export type StateItemStatus = 'active' | 'resolved' | 'closed' | 'expired' | string

export interface StateItem {
  item_id?: string
  conversation_id: string
  category: string
  content?: string
  item_value?: string
  template_id?: string | null
  tab_id?: string | null
  field_id?: string | null
  field_key?: string | null
  item_key?: string | null
  title?: string | null
  confidence?: number
  priority?: number
  source?: string
  status?: StateItemStatus
  user_locked?: boolean
  linked_card_ids?: string[]
  updated_at?: string
}
