import assert from 'node:assert/strict'
import {test} from 'node:test'
import {normalizeMetadata} from './metadata.ts'

test('normalizes actual Devvit metadata including a string creation date', () => {
  const row = normalizeMetadata(
    'Italia',
    {
      name: 'Italia',
      subscribersCount: 690421,
      description: {markdown: "L'Italia su reddit\n\nLeggi la wiki"},
      createdAt: '2009-11-03T13:00:12.783000+0000',
    },
    'run-1',
  )
  assert.equal(row.subs, 690421)
  assert.equal(row.description, "L'Italia su reddit Leggi la wiki")
  assert.equal(row.created_utc, '2009-11-03T13:00:12.783000+0000')
})

test('missing counts or descriptions never become zeros or empty replacements', () => {
  assert.throws(() =>
    normalizeMetadata(
      'italy',
      {name: 'italy', description: {markdown: 'test'}},
      'run',
    ),
  )
  assert.equal(
    normalizeMetadata('italy', {name: 'italy', subscribersCount: 1}, 'run')
      .description,
    null,
  )
  assert.throws(() =>
    normalizeMetadata(
      'italy',
      {name: 'other', subscribersCount: 1, description: {markdown: ''}},
      'run',
    ),
  )
  assert.throws(() =>
    normalizeMetadata(
      'italy',
      {name: 'italy', subscribersCount: -1, description: {markdown: ''}},
      'run',
    ),
  )
})

test('a returned empty description and zero count are valid', () => {
  const row = normalizeMetadata(
    'empty',
    {name: 'empty', subscribersCount: 0, description: {markdown: ''}},
    'run',
  )
  assert.equal(row.subs, 0)
  assert.equal(row.description, '')
})
