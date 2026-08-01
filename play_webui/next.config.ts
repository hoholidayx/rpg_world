import type { NextConfig } from 'next'
import { PLAY_STREAM_PROXY_TIMEOUT_MS } from './src/lib/stream/streamTimeout'

const playApiOrigin = process.env.RPG_WORLD_PLAY_API_ORIGIN ?? 'http://127.0.0.1:8001'

const nextConfig: NextConfig = {
  experimental: {
    proxyTimeout: PLAY_STREAM_PROXY_TIMEOUT_MS,
  },
  async rewrites() {
    return [
      {
        source: '/play-api/v1/:path*',
        destination: `${playApiOrigin}/play-api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
