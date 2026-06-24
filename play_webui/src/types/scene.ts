export type Scene = {
  attrs: Record<string, string>
  time?: string | null
  location?: string | null
  presentCharacters?: string[]
  mood?: string | null
}
