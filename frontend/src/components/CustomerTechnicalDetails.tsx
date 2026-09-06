import type { ReactNode } from 'react'
import './CustomerTechnicalDetails.css'

interface CustomerTechnicalDetailsProps {
  children: ReactNode
  title?: string
}

function CustomerTechnicalDetails({ children, title = '시연 기술 정보 보기' }: CustomerTechnicalDetailsProps) {
  return <details className="customer-technical-details"><summary>{title}</summary><div className="customer-technical-details__content">{children}</div></details>
}

export default CustomerTechnicalDetails
