import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { AdminView } from './components/AdminView'
import { ChatView } from './components/ChatView'
import { LevelOnboarding, ProfileDialog } from './components/LevelPicker'
import { Login } from './components/Login'
import {
  ADMIN_UNAUTHORIZED_EVENT,
  clearAdminToken,
  clearSession,
  getAdminToken,
  getMe,
  getStoredUser,
  getToken,
  setAdminToken,
  type User,
} from './lib/api'
import { IS_ANONYMOUS, startAnonymous } from './lib/auth'
import { levelLabel } from './lib/levels'

type View = 'chat' | 'admin'

function App() {
  return IS_ANONYMOUS ? <AnonymousApp /> : <LocalApp />
}

/** VITE_AUTH_MODE=local: 개발용 로그인(dev-login). 기존 동작 그대로. */
function LocalApp() {
  const [user, setUser] = useState<User | null>(() => (getToken() ? getStoredUser() : null))
  // 저장된 사용자 정보는 예전 것일 수 있어 서버 프로필로 한 번 확인한다(설명 수준 포함)
  const [checked, setChecked] = useState(false)
  const [view, setView] = useState<View>('chat')
  const [profileOpen, setProfileOpen] = useState(false)

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
    setView('chat')
    setProfileOpen(false)
  }, [])

  useEffect(() => {
    if (!getToken()) return
    getMe()
      .then(setUser)
      .catch((e) => {
        if (e?.status === 401 || e?.status === 404) logout()
      })
      .finally(() => setChecked(true))
  }, [logout])

  const onLogin = (u: User) => {
    setUser(u)
    setChecked(true)
  }

  if (!user) return <Login onLogin={onLogin} />
  if (!user.level) {
    if (!checked) return <main className="login muted">불러오는 중…</main>
    return <LevelOnboarding user={user} onDone={setUser} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">ETF Agent</strong>
        <span className="sample-tag">샘플 데이터</span>
        <nav>
          <button
            type="button"
            className={view === 'chat' ? 'tab on' : 'tab'}
            onClick={() => setView('chat')}
          >
            채팅
          </button>
          {user.role === 'admin' && (
            <button
              type="button"
              className={view === 'admin' ? 'tab on' : 'tab'}
              onClick={() => setView('admin')}
            >
              운영
            </button>
          )}
        </nav>
        <span className="spacer" />
        <button
          type="button"
          className="ghost profile-button"
          onClick={() => setProfileOpen(true)}
          title="프로필 수정"
        >
          <span className="user-email">{user.email}</span>
          <span className="level-badge">{levelLabel(user.level)}</span>
        </button>
        <button type="button" className="ghost" onClick={logout}>
          로그아웃
        </button>
      </header>
      {view === 'admin' && user.role === 'admin' ? (
        <AdminView />
      ) : (
        <ChatView onAuthError={logout} />
      )}
      {profileOpen && (
        <ProfileDialog user={user} onClose={() => setProfileOpen(false)} onSaved={setUser} />
      )}
    </div>
  )
}

const isAdminHash = () => window.location.hash === '#admin'

/**
 * VITE_AUTH_MODE=anonymous: 로그인 없는 접근(공개 URL).
 * 저장된 토큰이 없으면 이 브라우저용 익명 사용자를 받아 바로 채팅을 연다. 수준은 채팅 화면에서 고른다.
 * 운영 화면은 메뉴에 없고, 주소 끝에 #admin을 붙여 운영 토큰을 넣은 팀원만 쓴다.
 */
function AnonymousApp() {
  const [ready, setReady] = useState(() => Boolean(getToken()))
  const [error, setError] = useState<string | null>(null)
  const [adminOpen, setAdminOpen] = useState(isAdminHash)
  const starting = useRef(false)

  // 토큰이 없으면 익명 사용자를 받는다. ref로 한 번만 부른다(개발 모드 StrictMode의 이중 실행에도 1명만 생김).
  useEffect(() => {
    if (ready || error || starting.current) return
    starting.current = true
    startAnonymous()
      .then(() => setReady(true))
      .catch((e) => setError(e instanceof Error ? e.message : '접속하지 못했습니다'))
      .finally(() => {
        starting.current = false
      })
  }, [ready, error])

  useEffect(() => {
    const onHash = () => setAdminOpen(isAdminHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // 토큰이 만료·무효가 되면(401) 새 익명 사용자를 받는다. 이전 대화는 더 이상 보이지 않는다.
  const renew = useCallback(() => {
    clearSession()
    setReady(false)
  }, [])

  if (error)
    return (
      <main className="login">
        <div className="card">
          <h1>ETF Agent</h1>
          <p className="muted">{error}</p>
          <button type="button" onClick={() => setError(null)}>
            다시 시도
          </button>
        </div>
      </main>
    )
  if (!ready) return <main className="login muted">불러오는 중…</main>

  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">ETF Agent</strong>
        <span className="sample-tag">샘플 데이터</span>
        {adminOpen && (
          <nav>
            <button
              type="button"
              className="tab"
              onClick={() => {
                window.location.hash = ''
              }}
            >
              채팅으로
            </button>
          </nav>
        )}
        <span className="spacer" />
      </header>
      {adminOpen ? <AdminGate /> : <ChatView onAuthError={renew} chooseLevel />}
    </div>
  )
}

/**
 * 익명 모드의 운영 화면 입구: 운영 토큰(ADMIN_TOKEN)을 받아 이 탭에만 기억한다.
 * 운영 API가 토큰을 거절(401)하면 토큰 입력 화면으로 돌아간다. 익명 대화 토큰은 건드리지 않는다.
 */
function AdminGate() {
  const [token, setToken] = useState<string | null>(getAdminToken)
  const [input, setInput] = useState('')
  const [rejected, setRejected] = useState(false)

  useEffect(() => {
    const onRejected = () => {
      setToken(null)
      setRejected(true)
    }
    window.addEventListener(ADMIN_UNAUTHORIZED_EVENT, onRejected)
    return () => window.removeEventListener(ADMIN_UNAUTHORIZED_EVENT, onRejected)
  }, [])

  function submit(e: FormEvent) {
    e.preventDefault()
    const t = input.trim()
    if (!t) return
    setAdminToken(t)
    setToken(t)
    setInput('')
    setRejected(false)
  }

  if (!token)
    return (
      <form className="admin-gate" onSubmit={submit}>
        <h2>운영 화면</h2>
        {rejected && (
          <p className="error" role="alert">
            운영 토큰이 맞지 않습니다. 다시 넣어 주세요.
          </p>
        )}
        <p className="muted small">
          팀원용입니다. 운영 토큰을 넣으면 이 탭을 닫을 때까지 기억합니다.
        </p>
        <input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="운영 토큰"
          aria-label="운영 토큰"
          autoComplete="off"
        />
        <button type="submit" disabled={!input.trim()}>
          열기
        </button>
      </form>
    )

  return (
    <>
      <div className="admin-gate-bar">
        <button
          type="button"
          className="ghost"
          onClick={() => {
            clearAdminToken()
            setToken(null)
          }}
        >
          운영 토큰 지우기
        </button>
        <span className="muted small">토큰이 맞지 않으면 입력 화면으로 돌아갑니다.</span>
      </div>
      <AdminView />
    </>
  )
}

export default App
