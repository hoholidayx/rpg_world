import { FlatCompat } from '@eslint/eslintrc'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDirectory = path.dirname(fileURLToPath(import.meta.url))
const compat = new FlatCompat({ baseDirectory: currentDirectory })

const eslintConfig = [
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    ignores: [
      '.next/**',
      'design/**',
      'next-env.d.ts',
      'node_modules/**',
      'out/**',
      'tsconfig.tsbuildinfo',
    ],
  },
]

export default eslintConfig
