import type { NextConfig } from 'next'

const playApiOrigin = process.env.RPG_WORLD_PLAY_API_ORIGIN ?? 'http://127.0.0.1:8000'

const nextConfig: NextConfig = {
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
