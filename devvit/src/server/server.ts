import type {IncomingMessage, ServerResponse} from 'node:http'
import {reddit, scheduler} from '@devvit/web/server'
import {normalizeMetadata} from './metadata.ts'
import {subredditNames} from './subreddits.ts'

const batchSize = 10
const delayMs = 10_000

async function scheduleBatch(run: string, offset: number): Promise<void> {
  await scheduler.runJob({
    name: 'metadata-batch',
    runAt: new Date(Date.now() + delayMs),
    data: {run, offset},
  })
}

/** Only reads community metadata. No posting, voting or subscriptions. */
export async function onReq(
  req: IncomingMessage,
  rsp: ServerResponse,
): Promise<void> {
  try {
    if (req.method !== 'POST') throw Error('Unknown endpoint')
    if (req.url === '/internal/start-refresh') {
      for (const job of await scheduler.listJobs()) {
        if (job.name === 'metadata-batch') await scheduler.cancelJob(job.id)
      }
      const run = new Date().toISOString()
      console.log(
        'SUBREDDIT_REFRESH_START ' +
          JSON.stringify({run, total: subredditNames.length}),
      )
      await scheduleBatch(run, 0)
    } else if (req.url === '/internal/metadata-batch') {
      let body = ''
      for await (const chunk of req) body += chunk
      const {data} = JSON.parse(body) as {data: {run: string; offset: number}}
      if (
        !data ||
        !Number.isInteger(data.offset) ||
        data.offset < 0 ||
        typeof data.run !== 'string'
      ) {
        throw Error('Invalid batch')
      }
      const names = subredditNames.slice(data.offset, data.offset + batchSize)
      for (const name of names) {
        try {
          const info = await reddit.getSubredditInfoByName(name)
          const record = normalizeMetadata(name, info, data.run)
          console.log(`SUBREDDIT_METADATA ${JSON.stringify(record)}`)
        } catch (error) {
          console.error(
            'SUBREDDIT_METADATA_ERROR ' +
              JSON.stringify({
                run: data.run,
                name,
                error: error instanceof Error ? error.message : String(error),
              }),
          )
        }
      }
      const offset = data.offset + names.length
      if (offset < subredditNames.length) await scheduleBatch(data.run, offset)
      else
        console.log(
          'SUBREDDIT_REFRESH_DONE ' +
            JSON.stringify({run: data.run, total: offset}),
        )
    } else {
      rsp.writeHead(404, {'Content-Type': 'application/json'})
      rsp.end(JSON.stringify({error: 'not found'}))
      return
    }
    rsp.writeHead(200, {'Content-Type': 'application/json'})
    rsp.end('{}')
  } catch (error) {
    console.error(`SUBREDDIT_REFRESH_ERROR ${String(error)}`)
    rsp.writeHead(500, {'Content-Type': 'application/json'})
    rsp.end(JSON.stringify({error: 'Metadata refresh failed'}))
  }
}
