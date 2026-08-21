import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'


test('Docker builder satisfies the frontend Node runtime contract', async () => {
  const [dockerfile, packageJson] = await Promise.all([
    readFile(new URL('../Dockerfile', import.meta.url), 'utf8'),
    readFile(new URL('../package.json', import.meta.url), 'utf8').then(JSON.parse),
  ])

  assert.match(dockerfile, /^FROM node:22-alpine AS builder$/m)
  assert.equal(packageJson.engines.node, '>=22.12.0')
})
