import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The view's name, as the app config holds it (`GET /api/app`, decision 149.c). */
export type AppInfo = Schemas['AppInfo']
