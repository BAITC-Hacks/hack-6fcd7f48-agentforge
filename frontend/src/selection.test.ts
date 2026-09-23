import assert from 'node:assert/strict'
import test from 'node:test'
import { initialView } from './selection.ts'

test('URL view is active only when its required gid or cluster is present', () => {
  assert.equal(initialView('node', null, null), 'overview')
  assert.equal(initialView('cluster', null, null), 'overview')
  assert.equal(initialView('node', '100000000000000001', null), 'node')
  assert.equal(initialView('cluster', null, 2), 'cluster')
  assert.equal(initialView('other', '100000000000000001', 2), 'overview')
})
