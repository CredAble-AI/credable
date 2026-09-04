import type { DemoProfileType } from '../types/customerSession'

export interface DemoProfile {
  type: DemoProfileType
  name: string
  description: string
  context: string
}

export const demoProfiles: DemoProfile[] = [
  {
    type: 'SMALL_BUSINESS',
    name: '소상공인 Demo',
    description: '은행 데이터와 고객 동의 데이터를 연결하는 소상공인 사례입니다.',
    context: '합성 데이터 · 실제 고객정보 없음',
  },
  {
    type: 'STARTUP',
    name: '스타트업 Demo',
    description: '여러 금융 데이터의 연결 과정을 확인하는 스타트업 사례입니다.',
    context: '합성 데이터 · 실제 기업정보 없음',
  },
]

export const findDemoProfile = (type: DemoProfileType) => demoProfiles.find((profile) => profile.type === type)
