import type { IconAliases, IconProps, IconSet } from 'vuetify'
import { Icon, addIcon } from '@iconify/vue'

import checkboxChecked from '@images/svg/checkbox-checked.svg'
import checkboxIndeterminate from '@images/svg/checkbox-indeterminate.svg'
import checkboxUnchecked from '@images/svg/checkbox-unchecked.svg'
import radioChecked from '@images/svg/radio-checked.svg'
import radioUnchecked from '@images/svg/radio-unchecked.svg'

// --- Custom brand SVGs (icons missing from Iconify library sets) ----------------
// Place SVG files in src/assets/images/iconify-svg/ and register them here.
// Backend component seeds reference these as "custom-<name>" (dash-separated);
// Iconify resolves that to prefix "custom", name "<name>" — matching the addIcon call.
// See .cursor/rules/icons.mdc for the full guide.

const customBrandSvgs = import.meta.glob('@images/iconify-svg/*.svg', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

for (const [path, raw] of Object.entries(customBrandSvgs)) {
  const name = path.split('/').pop()!.replace('.svg', '')
  const parser = new DOMParser()
  const svgEl = parser.parseFromString(raw, 'image/svg+xml').querySelector('svg')
  if (!svgEl) continue
  const vb = (svgEl.getAttribute('viewBox') ?? '0 0 24 24').split(/\s+/).map(Number)

  addIcon(`custom:${name}`, { body: svgEl.innerHTML, left: vb[0], top: vb[1], width: vb[2], height: vb[3] })
}

// --- Vuetify form-control SVG overrides -----------------------------------------

const vuetifyFormSvgs: Record<string, unknown> = {
  'mdi-checkbox-blank-outline': checkboxUnchecked,
  'mdi-checkbox-marked': checkboxChecked,
  'mdi-minus-box': checkboxIndeterminate,
  'mdi-radiobox-marked': radioChecked,
  'mdi-radiobox-blank': radioUnchecked,
}

const aliases: Partial<IconAliases> = {
  calendar: 'tabler-calendar',
  collapse: 'tabler-chevron-up',
  complete: 'tabler-check',
  cancel: 'tabler-x',
  close: 'tabler-x',
  delete: 'tabler-circle-x-filled',
  clear: 'tabler-circle-x',
  success: 'tabler-circle-check',
  info: 'tabler-info-circle',
  warning: 'tabler-alert-triangle',
  error: 'tabler-alert-circle',
  prev: 'tabler-chevron-left',
  ratingEmpty: 'tabler-star',
  ratingFull: 'tabler-star-filled',
  ratingHalf: 'tabler-star-half-filled',
  next: 'tabler-chevron-right',
  delimiter: 'tabler-circle',
  sort: 'tabler-arrow-up',
  expand: 'tabler-chevron-down',
  menu: 'tabler-menu-2',
  subgroup: 'tabler-caret-down',
  dropdown: 'tabler-chevron-down',
  edit: 'tabler-pencil',
  loading: 'tabler-refresh',
  first: 'tabler-player-skip-back',
  last: 'tabler-player-skip-forward',
  unfold: 'tabler-arrows-move-vertical',
  file: 'tabler-paperclip',
  plus: 'tabler-plus',
  minus: 'tabler-minus',
  sortAsc: 'tabler-arrow-up',
  sortDesc: 'tabler-arrow-down',
}

function iconNameToIconify(name: string): string {
  const prefixMap: Record<string, string> = {
    'tabler-': 'tabler:',
    'mdi-': 'mdi:',
    'ph-': 'ph:',
    'fa-': 'fa6-solid:',
    'logos-': 'logos:',
  }

  for (const [prefix, iconifyPrefix] of Object.entries(prefixMap)) {
    if (name.startsWith(prefix)) {
      return iconifyPrefix + name.slice(prefix.length)
    }
  }

  return name
}

export const iconify: IconSet = {
  component: (props: IconProps) => {
    const iconName = typeof props.icon === 'string' ? props.icon : ''

    const customSvg = vuetifyFormSvgs[iconName]
    if (customSvg) return h(customSvg as any)

    const iconifyName = iconNameToIconify(iconName)

    return h(Icon, {
      icon: iconifyName,
      width: '1em',
      height: '1em',
    })
  },
}

export const icons = {
  defaultSet: 'iconify',
  aliases,
  sets: {
    iconify,
  },
}
