// Domain types for memory cards, libraries, inbox candidates, and characters.
// These mirror the backend SQLite schemas (cards / inbox / characters tables).

export type CardType =
  | 'preference'
  | 'boundary'
  | 'relationship'
  | 'event'
  | 'promise'
  | 'correction'
  | 'world_state'
  | 'summary'

export type CardScope = 'global' | 'character' | 'conversation'

export type CardStatus = 'pending_review' | 'approved' | 'rejected' | 'archived'

export interface MemoryCard {
  card_id: string
  library_id: string
  user_id: string
  character_id?: string | null
  conversation_id?: string | null
  scope: CardScope
  card_type: CardType
  memory_type?: CardType  // legacy alias rendered by some endpoints
  title?: string | null
  content: string
  summary?: string | null
  importance: number
  confidence: number
  status: CardStatus
  is_pinned?: boolean | number
  created_at?: string
  updated_at?: string
}

export interface MemoryLibrary {
  library_id: string
  name: string
  description?: string
  card_count?: number
  created_at?: string
  updated_at?: string
}

export type InboxStatus = 'pending' | 'approved' | 'rejected'
export type RiskLevel = 'low' | 'medium' | 'high'

export interface InboxItem {
  inbox_id: string
  library_id: string
  candidate_type: string
  payload_json: string
  user_id: string
  character_id?: string | null
  conversation_id?: string | null
  suggested_action: string
  risk_level: RiskLevel | string
  reason?: string | null
  status: InboxStatus | string
  reviewed_at?: string | null
  review_note?: string | null
  created_at?: string
}

export interface DiscoveredCharacter {
  character_id: string
  conversation_count: number
  first_seen_at?: string | null
  last_seen_at?: string | null
  template_id?: string | null
  library_ids?: string[] | null
  write_library_id?: string | null
  auto_apply?: boolean | null
}

export interface CharacterRow {
  character_id: string
  user_id: string
  display_name?: string | null
  system_prompt_hash?: string | null
  template_id?: string | null
  library_ids?: string[] | null
  write_library_id?: string | null
  auto_apply?: boolean | null
  created_at?: string
  updated_at?: string
}
