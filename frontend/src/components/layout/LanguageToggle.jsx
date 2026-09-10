import { Button } from '@/components/ui'
import { useT } from '@/i18n'

/** Arabic ⇄ English. Switches direction too (see i18n/index.jsx). */
export function LanguageToggle() {
  const { lang, setLang, t } = useT()
  const next = lang === 'ar' ? 'en' : 'ar'
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setLang(next)}
      aria-label={t('common.language')}
      title={t('common.language')}
    >
      {next === 'en' ? 'EN' : 'ع'}
    </Button>
  )
}
