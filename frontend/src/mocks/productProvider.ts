import type { ProductProvider } from '../api/productClient'
import type { AnnualRateRange, BankProduct, MoneyAmount, ProductComparisonResult, ProductCondition, ProductConditionStatus, ProductRequest, TermRangeMonths } from '../types/product'

const wait = (signal: AbortSignal, milliseconds = 650) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})
const money = (amount: string): MoneyAmount => ({ amount, currency: 'KRW' })
const rate = (minPercent: string, maxPercent: string): AnnualRateRange => ({ minPercent, maxPercent })
const term = (minMonths: number, maxMonths: number): TermRangeMonths => ({ minMonths, maxMonths })
const product = (productId: string, productName: string, eligibilitySummary: string, publicAmount: string, publicRate: AnnualRateRange, months: TermRangeMonths, repaymentMethods: string[]): BankProduct => ({
  productId, productName, eligibilitySummary, publicMaxAmount: money(publicAmount), annualRateRange: publicRate, termRangeMonths: months, repaymentMethods,
  officialSource: { sourceName: 'CredAble 도입 은행 Demo 카탈로그', sourceUrl: null, effectiveDate: '2026-09-01' }, productVersion: 'demo-product-v1', applicationUrl: null, applicationReference: null, demoOnly: true,
})
const condition = (productId: string, status: ProductConditionStatus, values: Partial<ProductCondition> = {}): ProductCondition => ({
  productId, status, personalizedMaxAmount: null, personalizedAnnualRateRange: null, personalizedTermRangeMonths: null, policyVersion: null,
  queriedAt: '2026-09-04T11:20:00+09:00', reasonCode: null, finalApprovalRequired: true, demoOnly: true, ...values,
})

const fixture = (request: ProductRequest): ProductComparisonResult => {
  if (request.profileType === 'STARTUP') return {
    sessionId: request.sessionId, products: [], catalogStatus: 'AVAILABLE', queryStatus: 'NOT_QUERIED',
    availableSortOptions: [{ field: 'ORIGINAL', label: '기본 순서', directions: ['NONE'] }], defaultSort: { field: 'ORIGINAL', direction: 'NONE' }, nullPlacement: 'LAST',
    canViewProducts: false, cannotProceedReason: '보완 평가 단계에서 상품 조건 조회를 진행할 수 없는 상태로 확인되었습니다.', resultAt: null,
    sourceName: 'CredAble Mock provider', catalogVersion: 'demo-catalog-v1', demoOnly: true,
  }
  const alpha = product('demo-working-capital', '사업 운영자금 플러스', '음식업 개인사업자를 위한 합성 운전자금 상품', '50000000', rate('4.20', '8.90'), term(12, 60), ['원리금균등분할상환', '만기일시상환'])
  const bridge = product('demo-daily-bridge', '데일리 브릿지론', '일상적인 사업자금 수요를 위한 합성 상품', '30000000', rate('4.80', '9.50'), term(6, 36), ['원금균등분할상환'])
  const steady = product('demo-steady-business', '스테디 비즈니스론', '업력 조건을 확인하는 합성 사업자 상품', '70000000', rate('4.50', '9.20'), term(12, 72), ['원리금균등분할상환'])
  const balance = product('demo-balance-partner', '밸런스 파트너론', '사업 운영 계획을 확인하는 합성 사업자 상품', '40000000', rate('4.60', '9.10'), term(12, 48), ['원금균등분할상환'])
  return {
    sessionId: request.sessionId,
    products: [
      { product: alpha, condition: condition(alpha.productId, 'PERSONALIZED_AVAILABLE', { personalizedMaxAmount: money('24000000'), personalizedAnnualRateRange: rate('5.10', '7.30'), personalizedTermRangeMonths: term(12, 48), policyVersion: 'demo-policy-v1' }), sortValues: { PERSONALIZED_LIMIT: 24000000, PERSONALIZED_RATE: 5.1 } },
      { product: bridge, condition: condition(bridge.productId, 'PUBLIC_ONLY'), sortValues: { PERSONALIZED_LIMIT: null, PERSONALIZED_RATE: null } },
      { product: steady, condition: condition(steady.productId, 'INSUFFICIENT_DATA', { reasonCode: 'DEMO_PRODUCT_DATA_INSUFFICIENT' }), sortValues: { PERSONALIZED_LIMIT: null, PERSONALIZED_RATE: null } },
      { product: balance, condition: condition(balance.productId, 'QUERY_FAILED', { reasonCode: 'DEMO_PRODUCT_CONDITION_UNAVAILABLE' }), sortValues: { PERSONALIZED_LIMIT: null, PERSONALIZED_RATE: null } },
    ],
    catalogStatus: 'AVAILABLE', queryStatus: 'PARTIAL', availableSortOptions: [
      { field: 'ORIGINAL', label: '기본 순서', directions: ['NONE'] },
      { field: 'PERSONALIZED_LIMIT', label: '조회 한도', directions: ['ASC', 'DESC'] },
      { field: 'PERSONALIZED_RATE', label: '조회 금리', directions: ['ASC', 'DESC'] },
    ], defaultSort: { field: 'ORIGINAL', direction: 'NONE' }, nullPlacement: 'LAST', canViewProducts: true, cannotProceedReason: null,
    resultAt: '2026-09-04T11:20:00+09:00', sourceName: 'CredAble Mock provider', catalogVersion: 'demo-catalog-v1', demoOnly: true,
  }
}

export const mockProductProvider: ProductProvider = {
  async get(request, signal) { await wait(signal); return fixture(request) },
  async refresh(request, signal) { await wait(signal, 900); return fixture(request) },
}
