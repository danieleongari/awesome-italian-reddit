export type MetadataInfo = {
  name?: string
  subscribersCount?: number
  description?: {markdown?: string}
  createdAt?: unknown
}

export function normalizeMetadata(
  name: string,
  info: MetadataInfo,
  run: string,
) {
  if (info.name?.toLowerCase() !== name.toLowerCase()) {
    throw Error('Reddit returned a different community')
  }
  if (
    typeof info.subscribersCount !== 'number' ||
    !Number.isSafeInteger(info.subscribersCount) ||
    info.subscribersCount < 0
  ) {
    throw Error('Reddit did not return a subscriber count')
  }
  return {
    run,
    name,
    subs: info.subscribersCount,
    description:
      typeof info.description?.markdown === 'string'
        ? info.description.markdown.replace(/\s+/g, ' ').trim().slice(0, 50)
        : null,
    created_utc: typeof info.createdAt === 'string' ? info.createdAt : null,
    updated_utc: new Date().toISOString(),
  }
}
