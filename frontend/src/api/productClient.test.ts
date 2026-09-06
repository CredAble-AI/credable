import { describe, expect, it, vi } from 'vitest'
import type { ProductCatalogResponse, ProductComparisonResponse, ProductConditionQueryResponse, ProductRequest } from '../types/product'
import { liveProductProvider } from './productClient'

const request: ProductRequest = { sessionId: 'ses_demo', profileType: 'small-business' }
const catalog = { sessionId: 'ses_demo', catalog: { status: 'AVAILABLE', catalogSnapshotId: 'pcs_demo', products: [], retrievedAt: '2026-09-06T06:00:00+09:00', catalogVersion: 'demo-v1', reasonCode: null, demoOnly: true } } satisfies ProductCatalogResponse
const conditions = { sessionId: 'ses_demo', query: { queryId: 'pcq_demo', status: 'COMPLETED', conditions: [], queriedAt: '2026-09-06T06:01:00+09:00', catalogSnapshotId: 'pcs_demo', assessmentId: 'asm_demo', dataSnapshotId: 'dss_demo', reasonCode: null, demoOnly: true } } satisfies ProductConditionQueryResponse
const comparison = { sessionId: 'ses_demo', status: 'PUBLIC_ONLY', items: [], assembledAt: '2026-09-06T06:02:00+09:00', catalogSnapshotId: 'pcs_demo', conditionQueryId: 'pcq_demo', reasonCode: null, sortableFields: [], nullPlacement: 'LAST', initialOrder: 'CATALOG_SOURCE', demoOnly: true } satisfies ProductComparisonResponse

describe('liveProductProvider', () => {
  it('restores an existing comparison with a single GET', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => comparison })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveProductProvider.get(request, signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/comparison', { method: 'GET', signal })
  })

  it('refreshes the catalog, queries conditions, and then loads the combined response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => catalog })
      .mockResolvedValueOnce({ ok: true, json: async () => conditions })
      .mockResolvedValueOnce({ ok: true, json: async () => comparison })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    const result = await liveProductProvider.refresh(request, signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/products/refresh', { method: 'POST', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/product-conditions/query', { method: 'POST', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/v1/sessions/ses_demo/comparison', { method: 'GET', signal })
    expect(result.catalogSnapshotId).toBe('pcs_demo')
  })
})
