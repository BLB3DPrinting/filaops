import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { handlePreloadError } from './lib/staleBuild'

// Vite fires this when a lazily loaded screen fails to load. When the cause
// is a file that is gone, this tab is on the old build: reload once to pick up
// the new one. Any other failure is left to the error screen
// (see lib/staleBuild.js).
window.addEventListener('vite:preloadError', (event) => handlePreloadError(event))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
