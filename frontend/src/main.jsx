import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { reloadForNewBuild } from './lib/staleBuild'

// Vite fires this when a script or stylesheet for a lazily loaded screen
// cannot be fetched, which after an update means this tab is on the old build.
// Reload once to pick up the new one (see lib/staleBuild.js).
window.addEventListener('vite:preloadError', (event) => {
  if (reloadForNewBuild()) event.preventDefault()
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
