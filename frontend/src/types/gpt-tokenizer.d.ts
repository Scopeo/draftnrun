declare module 'gpt-tokenizer' {
  export function encode(text: string): number[]
  export function decode(tokens: number[]): string
}
