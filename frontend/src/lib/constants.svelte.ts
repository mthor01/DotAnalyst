import { get, type Constants } from './api'

const CDN = 'https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react'

/** Hero and item names, shared by every page. Empty until loadConstants resolves. */
export const constants: Constants = $state({ heroes: {}, items: {}, abilities: {} })

export async function loadConstants() {
  Object.assign(constants, await get<Constants>('constants'))
}

export const heroName = (id: number) => constants.heroes[id]?.localized_name ?? `Hero ${id}`

export function heroIcon(id: number): string | undefined {
  const name = constants.heroes[id]?.name.replace('npc_dota_hero_', '')
  return name && `${CDN}/heroes/icons/${name}.png`
}

/** The wide portrait (256x144) the game shows in its top bar. */
export function heroPortrait(id: number): string | undefined {
  const name = constants.heroes[id]?.name.replace('npc_dota_hero_', '')
  return name && `${CDN}/heroes/${name}.png`
}

/** A point put into the attributes is named like a talent, but is spent like a skill point and has an icon. */
export const ATTRIBUTES = 'special_bonus_attributes'

/** What the game calls an ability; for a talent that is what it gives. Without a name, the replay's own, tidied. */
export const abilityName = (name: string) =>
  constants.abilities[name] ?? (name === ATTRIBUTES ? 'Attribute bonus' : name.replace(/^special_bonus_(unique_)?/, '').replaceAll('_', ' '))

export const abilityIcon = (name: string) => `${CDN}/abilities/${name === ATTRIBUTES ? 'attribute_bonus' : name}.png`

/** Icon for an item name as replays give it, without the item_ prefix. */
export const itemIconByName = (name: string) => `${CDN}/items/${name}.png`

export function itemIcon(id: number): string | undefined {
  const name = constants.items[id]
  return name && `${CDN}/items/${name}.png`
}
