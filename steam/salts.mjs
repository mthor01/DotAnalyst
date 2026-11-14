// Replay salts straight from Valve's Dota 2 game coordinator, through a second Steam account.
//
//   node --env-file=.env steam/salts.mjs <match_id>...
//
// prints one JSON object, {"<match_id>": salt, ...}, with the matches Valve gave a salt for.
// The account is STEAM_ALT_USER and STEAM_ALT_PASSWORD. The first run has to be by hand, to type the Steam Guard
// code; it leaves a login token in data/steam/ that later runs use (it lasts about 200 days and renews itself).
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { createInterface } from 'node:readline/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import SteamUser from 'steam-user'

const DOTA = 570
// k_EMsgGCClientHello, k_EMsgGCClientWelcome, k_EMsgGCMatchDetailsRequest (Valve's gcsystemmsgs and dota_gcmessages_msgid)
const HELLO = 4006
const WELCOME = 4004
const MATCH_DETAILS = 7095
const ANSWER_MS = 5000

/** CMsgGCMatchDetailsRequest: field 1, the match id as a varint. */
export function request(matchId) {
  const bytes = [0x08]
  let n = BigInt(matchId)
  for (; n >= 0x80n; n >>= 7n) bytes.push(Number(n & 0x7fn) | 0x80)
  bytes.push(Number(n))
  return Buffer.from(bytes)
}

/** One field of a protobuf message: a number for a varint or a fixed32, a Buffer for a nested message. */
function field(message, wanted) {
  let i = 0
  const varint = () => {
    for (let value = 0n, shift = 0n; ; shift += 7n) {
      if (i >= message.length) throw new Error('protobuf message ends early')
      const byte = message[i++]
      value |= BigInt(byte & 0x7f) << shift
      if (byte < 0x80) return Number(value)
    }
  }
  while (i < message.length) {
    const tag = varint()
    const type = tag & 7
    let value
    if (type === 0) value = varint()
    else if (type === 1) i += 8
    else if (type === 2) {
      const length = varint()
      value = message.subarray(i, (i += length))
    }
    else if (type === 5) value = message.readUInt32LE((i += 4) - 4)
    else throw new Error(`protobuf wire type ${type}`)
    if (tag >> 3 === wanted) return value
  }
}

/** The replay salt in a CMsgGCMatchDetailsResponse (match = 2, replay_salt = 13 in it); undefined or 0 if it has none. */
export function salt(response) {
  const match = field(response, 2)
  return match && field(match, 13)
}

function fail(message) {
  console.error(message)
  process.exit(1)
}

function main(ids) {
  const user = process.env.STEAM_ALT_USER
  const password = process.env.STEAM_ALT_PASSWORD
  if (!user || !password) fail('STEAM_ALT_USER and STEAM_ALT_PASSWORD are not set')
  if (ids.some((id) => !/^\d+$/.test(id))) fail('usage: node steam/salts.mjs <match_id>...')

  const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'data', 'steam')
  mkdirSync(dir, { recursive: true })
  const tokenFile = join(dir, `refresh_token_${user}`)
  const token = existsSync(tokenFile) && readFileSync(tokenFile, 'utf8').trim()
  const client = new SteamUser({ dataDirectory: dir, renewRefreshTokens: true })

  client.on('refreshToken', (fresh) => writeFileSync(tokenFile, fresh))
  client.on('steamGuard', async (domain, callback) => {
    if (!process.stdin.isTTY) fail('Steam Guard code needed: run `node --env-file=.env steam/salts.mjs` once by hand')
    const prompt = createInterface({ input: process.stdin, output: process.stderr })
    callback((await prompt.question(`Steam Guard code (${domain ? `email at ${domain}` : 'mobile app'}): `)).trim())
    prompt.close()
  })
  client.on('error', (error) => {
    if (token) rmSync(tokenFile) // an expired or revoked token: the next run logs in with the password again
    fail(`Steam login failed: ${error.message}`)
  })

  let hello
  client.on('loggedOn', () => {
    setTimeout(() => fail('no answer from the Dota 2 game coordinator'), 30000 + ids.length * (ANSWER_MS + 500))
    // a new account does not own Dota 2 yet, and the coordinator only talks to owners; asking again is harmless
    client.requestFreeLicense([DOTA], () => client.gamesPlayed(DOTA, true))
  })
  client.on('appLaunched', (appid) => {
    if (appid !== DOTA) return
    const greet = () => client.sendToGC(DOTA, HELLO, {}, Buffer.alloc(0))
    greet()
    hello = setInterval(greet, 2000) // the coordinator often ignores the first hello
  })
  client.on('receivedFromGC', async (appid, type) => {
    if (appid !== DOTA || type !== WELCOME || !hello) return
    clearInterval(hello)
    hello = null // a second welcome must not start the questions again
    const salts = {}
    for (const id of ids) {
      const answer = await new Promise((resolve) => {
        setTimeout(resolve, ANSWER_MS)
        client.sendToGC(DOTA, MATCH_DETAILS, {}, request(id), (_appid, _type, payload) => resolve(payload))
      })
      try {
        const found = answer && salt(answer)
        if (found) salts[id] = found
      } catch (error) {
        console.error(`match ${id}: ${error.message}`)
      }
      await new Promise((resolve) => setTimeout(resolve, 500)) // OpenDota's retriever keeps at least 250 ms between questions
    }
    console.log(JSON.stringify(salts))
    client.logOff()
    setTimeout(() => process.exit(0), 1000)
  })

  client.logOn(token ? { refreshToken: token } : { accountName: user, password })
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv.slice(2))
