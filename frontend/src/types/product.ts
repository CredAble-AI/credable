import type { DemoProfileType } from './customerSession'

export type ProductCatalogStatus = 'NOT_LOADED' | 'CATALOG_NOT_CONFIGURED' | 'AVAILABLE' | 'FAILED'
export type ProductConditionQueryStatus = 'NOT_QUERIED' | 'CATALOG_UNAVAILABLE' | 'COMPLETED' | 'PARTIAL' | 'FAILED'
export type ProductConditionStatus = 'PUBLIC_ONLY' | 'PERSONALIZED_AVAILABLE' | 'INELIGIBLE' | 'INSUFFICIENT_DATA' | 'POLICY_NOT_CONFIGURED' | 'QUERY_FAILED'
export type ProductSortField = 'ORIGINAL' | 'PERSONALIZED_LIMIT' | 'PERSONALIZED_RATE'
export type ProductSortDirection = 'NONE' | 'ASC' | 'DESC'

export interface MoneyAmount { amount: string; currency: string }
export interface AnnualRateRange { minPercent: string; maxPercent: string }
export interface TermRangeMonths { minMonths: number; maxMonths: number }
export interface BankProduct {
  productId: string; productName: string; eligibilitySummary: string
  publicMaxAmount: MoneyAmount | null; annualRateRange: AnnualRateRange | null
  termRangeMonths: TermRangeMonths | null; repaymentMethods: string[]
  officialSource: { sourceName: string; sourceUrl: string | null; effectiveDate: string }
  productVersion: string; applicationUrl: string | null; applicationReference: string | null; demoOnly: true
}
export interface ProductCondition {
  productId: string; status: ProductConditionStatus
  personalizedMaxAmount: MoneyAmount | null; personalizedAnnualRateRange: AnnualRateRange | null
  personalizedTermRangeMonths: TermRangeMonths | null; policyVersion: string | null
  queriedAt: string; reasonCode: string | null; finalApprovalRequired: true; demoOnly: true
}
export interface ProductCatalogResponse {
  sessionId: string
  catalog: { status: ProductCatalogStatus; catalogSnapshotId: string | null; products: BankProduct[]; retrievedAt: string | null; catalogVersion: string | null; reasonCode: string | null; demoOnly: true }
}
export interface ProductConditionQueryResponse {
  sessionId: string
  query: { queryId: string | null; status: ProductConditionQueryStatus; conditions: ProductCondition[]; queriedAt: string | null; catalogSnapshotId: string | null; assessmentId: string | null; dataSnapshotId: string | null; reasonCode: string | null; demoOnly: true }
}
export interface ProductRequest { sessionId: string; profileType: DemoProfileType }
export interface ProductView { product: BankProduct; condition: ProductCondition; sortValues?: Partial<Record<'PERSONALIZED_LIMIT' | 'PERSONALIZED_RATE', number | null>> }
export interface SortOption { field: ProductSortField; label: string; directions: ProductSortDirection[] }
export interface ProductComparisonResult {
  sessionId: string; products: ProductView[]; catalogStatus: ProductCatalogStatus; queryStatus: ProductConditionQueryStatus
  availableSortOptions: SortOption[]; defaultSort: { field: ProductSortField; direction: ProductSortDirection }
  nullPlacement: 'LAST'; canViewProducts: boolean; cannotProceedReason: string | null
  resultAt: string | null; sourceName: string | null; catalogVersion: string | null; demoOnly: true
}
