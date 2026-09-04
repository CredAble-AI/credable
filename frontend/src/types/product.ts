import type { DemoProfileType } from './customerSession'

export type ComparisonStatus = 'CATALOG_UNAVAILABLE' | 'PUBLIC_ONLY' | 'AVAILABLE' | 'PARTIAL'
export type ComparisonSortField = 'PUBLIC_MAX_AMOUNT' | 'PUBLIC_MIN_ANNUAL_RATE' | 'PERSONALIZED_MAX_AMOUNT' | 'PERSONALIZED_MIN_ANNUAL_RATE'
export type ProductConditionStatus = 'PUBLIC_ONLY' | 'PERSONALIZED_AVAILABLE' | 'INELIGIBLE' | 'INSUFFICIENT_DATA' | 'POLICY_NOT_CONFIGURED' | 'QUERY_FAILED'
export type ProductSortDirection = 'NONE' | 'ASC' | 'DESC'

export interface MoneyAmount { amount: string; currency: string }
export interface AnnualRateRange { minPercent: string; maxPercent: string }
export interface TermRangeMonths { minMonths: number; maxMonths: number }
export interface ProductOfficialSource { sourceName: string; sourceUrl: string | null; effectiveDate: string }

export interface PublicProductConditions {
  maxAmount: MoneyAmount | null
  annualRateRange: AnnualRateRange | null
  termRangeMonths: TermRangeMonths | null
  repaymentMethods: string[]
}
export interface PersonalizedProductConditions {
  maxAmount: MoneyAmount | null
  annualRateRange: AnnualRateRange | null
  termRangeMonths: TermRangeMonths | null
  policyVersion: string
  queriedAt: string
}
export interface ProductComparisonItem {
  productId: string
  productName: string
  eligibilitySummary: string
  publicConditions: PublicProductConditions
  personalizedConditions: PersonalizedProductConditions | null
  conditionStatus: ProductConditionStatus | null
  conditionReasonCode: string | null
  officialSource: ProductOfficialSource
  productVersion: string
  applicationUrl: string | null
  applicationReference: string | null
  finalApprovalRequired: true
  demoOnly: true
}
export interface ProductComparisonResponse {
  sessionId: string
  status: ComparisonStatus
  items: ProductComparisonItem[]
  assembledAt: string
  catalogSnapshotId: string | null
  conditionQueryId: string | null
  reasonCode: string | null
  sortableFields: ComparisonSortField[]
  nullPlacement: 'LAST'
  initialOrder: 'CATALOG_SOURCE'
  demoOnly: true
}

export interface ProductRequest { sessionId: string; profileType: DemoProfileType }
export interface ProductView {
  product: ProductComparisonItem
  /** Provider-owned navigation capability; the component never infers this from condition status. */
  applicationLinkAvailable: boolean
  applicationUrl: string | null
}
export interface ProductComparisonResult {
  sessionId: string
  products: ProductView[]
  status: ComparisonStatus
  sortableFields: ComparisonSortField[]
  nullPlacement: 'LAST'
  initialOrder: 'CATALOG_SOURCE'
  canViewProducts: boolean
  cannotProceedReason: string | null
  resultAt: string | null
  catalogSnapshotId: string | null
  demoOnly: true
}
