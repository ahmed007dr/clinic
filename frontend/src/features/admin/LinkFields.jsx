import { Input } from '@/components/ui'

const HINTS = {
  whatsapp: 'الرقم مع كود الدولة، مثل 201001234567',
  facebook: 'facebook.com/…',
  instagram: 'instagram.com/…',
  tiktok: 'tiktok.com/@…',
  youtube: 'youtube.com/@…',
  x: 'x.com/…',
  website: 'www.…',
  maps: 'رابط الموقع من خرائط جوجل',
}

/**
 * One input per kind of link — the clinic's on the Print design screen, a
 * doctor's on their account page. Empty ones are simply not shown anywhere;
 * the server accepts only web addresses and a WhatsApp number
 * (branches/printing.py `clean_links`).
 */
export function LinkFields({ kinds, value, onChange, disabled }) {
  const set = (key) => (event) => onChange({ ...value, [key]: event.target.value })
  return (
    <div className="form-grid">
      {(kinds ?? []).map((kind) => (
        <Input
          key={kind.key}
          id={`link-${kind.key}`}
          label={kind.label}
          dir="ltr"
          placeholder={HINTS[kind.key]}
          value={value?.[kind.key] ?? ''}
          onChange={set(kind.key)}
          disabled={disabled}
        />
      ))}
    </div>
  )
}
