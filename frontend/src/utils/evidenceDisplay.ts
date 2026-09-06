/** Server-owned evidence vocabulary rendered for customers. */
export const evidenceDataCategoryLabels: Record<string, string> = {
  BUSINESS_IDENTITY: '사업자 식별 정보',
  MONTHLY_SALES: '월별 매출',
  MONTHLY_DEPOSITS: '월별 입금',
  MONTHLY_WITHDRAWALS: '월별 출금',
  PERIOD_TOTALS: '대상 기간 합계',
  SETTLEMENT_PROVIDER_IDENTITY: '정산기관 식별 정보',
  MONTHLY_SETTLEMENTS: '월별 정산액',
  SETTLEMENT_DEPOSITS: '정산대금 입금 내역',
  CORPORATE_ACCOUNT_IDENTITY: '법인 계좌 식별 정보',
  COUNTERPARTY_IDENTITY: '거래 상대방 식별 정보',
  CONTRACT_AMOUNTS: '계약 금액',
  ORDER_AMOUNTS: '주문 금액',
}

export const evidenceDataCategoryLabel = (code: string) => evidenceDataCategoryLabels[code] ?? code
