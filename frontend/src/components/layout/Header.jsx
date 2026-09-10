import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Avatar, Badge, Button } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'

import { ThemeToggle } from './ThemeToggle'

export function Header({ onToggleMenu, menuOpen }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const [menu, setMenu] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    let active = true
    const load = () =>
      api.notifications
        .unreadCount()
        .then((data) => {
          if (active) setUnread(data.count)
        })
        .catch(() => {})
    load()
    // A minute is often enough for a badge and rare enough that it costs
    // nothing. Polling rather than websockets: shared hosting cannot hold
    // open connections, and this is a badge, not a chat.
    const timer = setInterval(load, 60000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!menu) return undefined
    const onClick = (event) => {
      if (!menuRef.current?.contains(event.target)) setMenu(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [menu])

  return (
    <header className="header">
      <Button
        variant="ghost"
        icon
        className="header__menu"
        onClick={onToggleMenu}
        aria-label="القائمة"
        aria-expanded={menuOpen}
      >
        ☰
      </Button>

      <div className="header__spacer" />

      <ThemeToggle />

      <Link to="/notifications" className="header__bell" aria-label="الإشعارات">
        <span aria-hidden="true">🔔</span>
        {unread > 0 && (
          <Badge tone="urgent" className="header__badge">
            {unread > 99 ? '99+' : unread}
          </Badge>
        )}
      </Link>

      <div className="header__user" ref={menuRef}>
        <button
          type="button"
          className="header__trigger"
          onClick={() => setMenu((open) => !open)}
          aria-expanded={menu}
          aria-haspopup="menu"
        >
          <Avatar name={user?.username} />
          <span className="header__name">
            <strong>{user?.username}</strong>
            <span className="ui-muted">{user?.role}</span>
          </span>
        </button>

        {menu && (
          <div className="header__menu-panel" role="menu">
            <Link to="/settings/account" role="menuitem" onClick={() => setMenu(false)}>
              حسابي
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={async () => {
                setMenu(false)
                await logout()
                navigate('/login', { replace: true })
              }}
            >
              تسجيل الخروج
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
