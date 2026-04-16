// Polyfill localStorage for Node 22+ where the built-in localStorage
// doesn't implement the full Storage interface (missing .clear(), etc.)
const store: Record<string, string> = {}

const localStorageMock: Storage = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = String(value)
  },
  removeItem: (key: string) => {
    delete store[key]
  },
  clear: () => {
    Object.keys(store).forEach(key => delete store[key])
  },
  get length() {
    return Object.keys(store).length
  },
  key: (index: number) => Object.keys(store)[index] ?? null,
}

Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageMock,
  writable: true,
})
