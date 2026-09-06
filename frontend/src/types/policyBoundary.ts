export type BoundaryStatus = 'STABLE' | 'AMBIGUOUS' | 'POLICY_BLOCKED'

export interface BoundaryDecision {
  status: BoundaryStatus
  possibleRoutes: string[]
  crossedBoundaryCodes: string[]
  stopReason: string | null
  underwriterRequired: boolean
  restrictionCode?: string | null
  followUpCodes?: string[]
}

export interface PolicyBoundaryCheckState {
  boundaryCheckId: string
  assessmentId: string
  checkedAt: string
  decision: BoundaryDecision
  inputSnapshotId: string
  calibrationVersion: string
  policyVersion: string
  demoOnly: true
}

export interface PolicyBoundaryCheckResponse {
  sessionId: string
  boundaryCheck: PolicyBoundaryCheckState | null
}
