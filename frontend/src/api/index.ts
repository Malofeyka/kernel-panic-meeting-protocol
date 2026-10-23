import { httpApi, type ApiClient } from './client'
import { mockApi } from './mock'

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1'

export const api: ApiClient = USE_MOCKS ? mockApi : httpApi

export { ApiError, isAbortError } from './errors'
export type * from './types'
