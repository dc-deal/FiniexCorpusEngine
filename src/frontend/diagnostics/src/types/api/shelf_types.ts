import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Every work of both knowledge bases, how far it is converted and why pages did not pass (`GET /api/shelf`). */
export type Shelf = Schemas['Shelf']
export type ShelfRow = Schemas['ShelfRow']
