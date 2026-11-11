import { get, type Constants } from './api'

const CDN = 'https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react'

/** Hero and item names, shared by every page. Empty until loadConstants resolves. */
export const constants: Constants = $state({ heroes: {}, items: {} })

export async function loadConstants() {
  Object.assign(constants, await get<Constants>('constants'))
}

export const heroName = (id: number) => constants.heroes[id]?.localized_name ?? `Hero ${id}`

export function heroIcon(id: number): string | undefined {
  const name = constants.heroes[id]?.name.replace('npc_dota_hero_', '')
  return name && `${CDN}/heroes/icons/${name}.png`
}

/** Icon for an item name as replays give it, without the item_ prefix. */
export const itemIconByName = (name: string) => `${CDN}/items/${name}.png`

export function itemIcon(id: number): string | undefined {
  const name = constants.items[id]
  return name && `${CDN}/items/${name}.png`
}
