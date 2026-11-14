// node --test steam/   (no Steam login: only the two message functions)
import assert from 'node:assert/strict'
import test from 'node:test'
import { request, salt } from './salts.mjs'

test('the request is field 1 with the match id as a varint', () => {
  assert.deepEqual([...request('1')], [0x08, 0x01])
  assert.deepEqual([...request('300')], [0x08, 0xac, 0x02]) // the varint example of the protobuf documentation
  // 9089036898 is above 32 bits: five 7-bit groups, lowest first
  assert.deepEqual([...request('9089036898')], [0x08, 0xe2, 0xe4, 0xfe, 0xed, 0x21])
})

test('the salt is read out of the match inside the response', () => {
  const match = [
    0x18, 0x8f, 0x07, // duration = 911 (varint, skipped)
    0x25, 0x01, 0x02, 0x03, 0x04, // starttime (fixed32, skipped)
    0x32, 0x02, 0xaa, 0xbb, // field 6 as two bytes (length-delimited, skipped)
    0x50, 0xb5, 0x01, // cluster = 181
    0x6d, 0xb2, 0xec, 0xf0, 0x1e, // replay_salt = 519105714 (fixed32, little-endian)
  ]
  const response = Buffer.from([0x08, 0x01, 0x12, match.length, ...match])
  assert.equal(salt(response), 519105714)
})

test('a response without a match, or a match without a salt, has none', () => {
  assert.equal(salt(Buffer.from([0x08, 0x02])), undefined) // result 2: match not found
  assert.equal(salt(Buffer.from([0x08, 0x01, 0x12, 0x03, 0x50, 0xb5, 0x01])), undefined)
})

test('a cut-off response is an error, not a wrong salt', () => {
  assert.throws(() => salt(Buffer.from([0x08, 0x01, 0x12, 0x05, 0x6d, 0xb2, 0xec])))
})
