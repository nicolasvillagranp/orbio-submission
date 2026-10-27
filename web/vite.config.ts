/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Date tests assume the team's time zone (Spain), including its clock changes.
  test: { env: { TZ: 'Europe/Madrid' } },
})
