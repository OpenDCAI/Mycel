import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'
import './index.css'
import './App.css'
import './styles/motion-tokens.css'
import './styles/motion-presets.css'
import './styles/effects.css'
import { router } from './router.tsx'

const serializeLogArg = (arg: unknown): string => {
  if (typeof arg !== 'object' || arg === null) {
    return String(arg)
  }

  try {
    const seen = new WeakSet<object>()
    // @@@safe-log-serialization - prevent circular references from turning console.log calls into runtime errors
    const json = JSON.stringify(arg, (_key, value) => {
      if (typeof value === 'object' && value !== null) {
        if (seen.has(value)) {
          return '[Circular]'
        }
        seen.add(value)
      }
      return value
    })
    return json ?? String(arg)
  } catch (error) {
    originalLog('[frontend-debug-log] failed to serialize console.log arg:', error)
    return String(arg)
  }
}

// Intercept console.log and send to backend
const originalLog = console.log;
console.log = (...args: unknown[]) => {
  originalLog(...args);
  // Send to backend for logging
  const message = args.map((arg) => serializeLogArg(arg)).join(' ')

  fetch('/api/debug/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, timestamp: new Date().toISOString() }),
  }).catch((error) => {
    originalLog('[frontend-debug-log] failed to send /api/debug/log:', error)
  })
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
    <Toaster position="bottom-right" richColors />
  </StrictMode>,
)
