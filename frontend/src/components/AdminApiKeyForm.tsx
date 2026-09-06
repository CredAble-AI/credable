import { useState, type FormEvent } from 'react'
import { useAdminAuth } from '../hooks/useAdminAuth'

function AdminApiKeyForm() {
  const { connect } = useAdminAuth()
  const [keyInput, setKeyInput] = useState('')
  const [keyError, setKeyError] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const key = keyInput.trim()
    if (!key) { setKeyError('관리자 Demo API Key를 입력해주세요.'); return }
    setKeyError(''); setKeyInput(''); connect(key)
  }

  return <section className="admin-auth" aria-labelledby="admin-auth-title"><div><span aria-hidden="true">⌁</span><h2 id="admin-auth-title">관리자 Demo API Key가 필요합니다</h2><p>입력한 키는 현재 브라우저 메모리에만 보관하며 새로고침하면 삭제됩니다. 저장소, URL, localStorage와 로그에는 저장하지 않습니다.</p></div><form onSubmit={submit}><label htmlFor="admin-api-key">관리자 Demo API Key</label><input id="admin-api-key" type="password" value={keyInput} onChange={(event) => { setKeyInput(event.target.value); setKeyError('') }} autoComplete="off" spellCheck={false} aria-invalid={Boolean(keyError)} aria-describedby={keyError ? 'admin-key-error' : undefined} required />{keyError && <p id="admin-key-error" className="admin-key-error" role="alert">{keyError}</p>}<button className="button button--primary" type="submit">관리자 화면 확인</button></form></section>
}

export default AdminApiKeyForm
