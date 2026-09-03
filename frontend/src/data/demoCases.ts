import type { DemoCaseType } from '../types/case'

export interface DemoCaseOption {
  type: DemoCaseType
  name: string
  currentDecision: 'DECLINED' | 'HELD'
  tenureMonths: number
  productType: string
  reasons: string[]
  description: string
}

export const demoCases: DemoCaseOption[] = [
  { type: 'BORDERLINE', name: 'Borderline', currentDecision: 'HELD', tenureMonths: 9, productType: '소액 운전자금', reasons: ['금융이력 부족', '최근 실적 미반영'], description: '추가 Evidence로 불확실성을 줄일 수 있는 Case' },
  { type: 'NO_DATA', name: 'No Data', currentDecision: 'HELD', tenureMonths: 14, productType: '소액 운전자금', reasons: ['필요한 Evidence 일부 부족'], description: '데이터 부족을 나쁜 신용으로 판단하지 않는 Case' },
  { type: 'SUSPICIOUS', name: 'Suspicious', currentDecision: 'HELD', tenureMonths: 20, productType: '소액 운전자금', reasons: ['매출 급증', '중복 및 출처 이상'], description: '자동 부결이 아니라 품질 검토와 심사역 확인이 필요한 Case' },
  { type: 'HARD_STOP', name: 'Hard Stop', currentDecision: 'DECLINED', tenureMonths: 24, productType: '소액 운전자금', reasons: ['정책상 제외 또는 컴플라이언스 Hard Stop'], description: 'Second-Look 대상이 아니며 기존 결정을 유지하는 Case' },
]
