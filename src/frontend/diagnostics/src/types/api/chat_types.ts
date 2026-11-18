import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Whether the chat answers here, and its example questions (`GET /api/chat`). */
export type ChatInfo = Schemas['ChatInfo']
/** One turn of the chat as the turn log keeps it (`POST /api/chat`); the fields the view reads are typed. */
export type ChatResult = Schemas['ChatResult']
export type ServerTurn = Schemas['ServerTurn']
export type SecurityCheck = Schemas['SecurityCheck']
