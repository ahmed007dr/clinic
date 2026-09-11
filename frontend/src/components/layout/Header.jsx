import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Avatar, Badge, Button, Select } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { useT } from '@/i18n'

import { LanguageToggle } from './LanguageToggle'
import { ThemeToggle } from './ThemeToggle'

export function Header({ onToggleMenu, menuOpen }) {
  const { user, logout } = useAuth()
  const { t } = useT()
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
        aria-label={t('header.menu')}
        aria-expanded={menuOpen}
      >
        ☰
      </Button>

      <div className="header__spacer" />

      <BranchSwitcher />

      <LanguageToggle />
      <ThemeToggle />

      <Link to="/notifications" className="header__bell" aria-label={t('header.notifications')}>
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
              {t('header.account')}
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
              {t('header.logout')}
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

/**
 * For a doctor the Owner linked to several clinics: which one every screen is
 * showing. The server keeps the choice in the session and re-checks it on
 * each request (accounts/roles.py `current_branch_id`); the page reloads so
 * nothing from the previous clinic stays on screen.
 */
function BranchSwitcher() {
  const { user } = useAuth()
  const { t } = useT()
  const [saving, setSaving] = useState(false)
  const branches = user?.branches ?? []
  if (branches.length < 2) return null

  const onChange = async (event) => {
    setSaving(true)
    try {
      await api.auth.setBranch(event.target.value)
      window.location.reload()
    } catch {
      setSaving(false)
    }
  }

  return (
    <Select
      aria-label={t('header.branch')}
      title={t('header.branch')}
      value={user.active_branch?.uuid ?? ''}
      onChange={onChange}
      disabled={saving}
      options={branches.map((branch) => ({ value: branch.uuid, label: branch.name }))}
      style={{ width: 'auto' }}
    />
  )
}
