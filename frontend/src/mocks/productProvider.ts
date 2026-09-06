import type { ProductProvider } from '../api/productClient'
import type { AnnualRateRange, MoneyAmount, ProductComparisonItem, ProductComparisonResult, ProductConditionStatus, ProductRequest, TermRangeMonths } from '../types/product'

const wait = (signal: AbortSignal, milliseconds = 650) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})
const money = (amount: string): MoneyAmount => ({ amount, currency: 'KRW' })
const rate = (minPercent: string, maxPercent: string): AnnualRateRange => ({ minPercent, maxPercent })
const term = (minMonths: number, maxMonths: number): TermRangeMonths => ({ minMonths, maxMonths })
const officialSource = { sourceName: 'CredAble 도입 은행 Demo 카탈로그', sourceUrl: null, effectiveDate: '2026-09-01' }

const item = (
  productId: string, productName: string, eligibilitySummary: string,
  publicAmount: string, publicRate: AnnualRateRange, months: TermRangeMonths, repaymentMethods: string[],
  conditionStatus: ProductConditionStatus | null,
  conditionReasonCode: string | null = null,
): ProductComparisonItem => ({
  productId, productName, eligibilitySummary,
  publicConditions: { maxAmount: money(publicAmount), annualRateRange: publicRate, termRangeMonths: months, repaymentMethods },
  conditionStatus, conditionReasonCode,
  officialSource, productVersion: 'demo-product-v1', applicationUrl: null, applicationReference: null,
  finalApprovalRequired: true, demoOnly: true,
})

const fixture = (request: ProductRequest): ProductComparisonResult => {
  if (request.profileType === 'startup') return {
    sessionId: request.sessionId, products: [], status: 'CATALOG_UNAVAILABLE',
    sortableFields: [], nullPlacement: 'LAST', initialOrder: 'CATALOG_SOURCE',
    canViewProducts: false, cannotProceedReason: '기준평가 단계에서 상품 조건 조회를 진행할 수 없는 상태로 확인되었습니다.',
    resultAt: '2026-09-04T11:20:00+09:00', catalogSnapshotId: null, demoOnly: true,
  }
  const alpha = item('demo-working-capital', '사업 운영자금 플러스', '음식업 개인사업자를 위한 합성 운전자금 상품', '50000000', rate('4.20', '8.90'), term(12, 60), ['원리금균등분할상환', '만기일시상환'],
    'PUBLIC_ONLY')
  const bridge = item('demo-daily-bridge', '데일리 브릿지론', '일상적인 사업자금 수요를 위한 합성 상품', '30000000', rate('4.80', '9.50'), term(6, 36), ['원금균등분할상환'], 'PUBLIC_ONLY')
  const steady = item('demo-steady-business', '스테디 비즈니스론', '업력 조건을 확인하는 합성 사업자 상품', '70000000', rate('4.50', '9.20'), term(12, 72), ['원리금균등분할상환'], 'INSUFFICIENT_DATA', 'DEMO_PRODUCT_DATA_INSUFFICIENT')
  const balance = item('demo-balance-partner', '밸런스 파트너론', '사업 운영 계획을 확인하는 합성 사업자 상품', '40000000', rate('4.60', '9.10'), term(12, 48), ['원금균등분할상환'], 'QUERY_FAILED', 'DEMO_PRODUCT_CONDITION_UNAVAILABLE')
  return {
    sessionId: request.sessionId,
    products: [alpha, bridge, steady, balance].map((product) => ({ product, applicationLinkAvailable: false, applicationUrl: null })),
    status: 'PARTIAL',
    sortableFields: ['PUBLIC_MAX_AMOUNT', 'PUBLIC_MIN_ANNUAL_RATE'],
    nullPlacement: 'LAST', initialOrder: 'CATALOG_SOURCE', canViewProducts: true, cannotProceedReason: null,
    resultAt: '2026-09-04T11:20:00+09:00', catalogSnapshotId: 'demo-catalog-snapshot-1', demoOnly: true,
  }
}

export const mockProductProvider: ProductProvider = {
  async get(request, signal) { await wait(signal); return fixture(request) },
  async refresh(request, signal) { await wait(signal, 900); return fixture(request) },
}
