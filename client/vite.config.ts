import path from 'path';

import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Dev-only: forward API routes to the Python FastAPI server so the SPA can use
// same-origin relative URLs (no CORS). Target defaults to localhost:8000;
// override with VITE_API_BASE_URL if the backend runs elsewhere. Keep this list
// in sync with every public backend path the client calls (new routes won't
// proxy until added here). Production static builds set VITE_API_BASE_URL to
// the real API origin instead of relying on this proxy.
const backend = process.env.VITE_API_BASE_URL || 'http://localhost:8000';
const proxied = [
	'/extract-videos',
	'/extract-gallery',
	'/proxy-video',
	'/proxy-token',
	'/health',
	'/split-audio',
	'/transcribe'
];

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		// Bind on all interfaces so IPv4 `localhost` works on Windows
		// (Vite otherwise binds IPv6 `::1` only -> ERR_CONNECTION_REFUSED in Chrome).
		// Also lets you open the dev URL on your phone over the LAN for mobile testing.
		host: true,
		port: 5173,
		proxy: Object.fromEntries(
			proxied.map((route) => [route, { target: backend, changeOrigin: true }])
		)
	},
	resolve: {
		alias: {
			$lib: path.resolve('./src/lib')
		}
	}
});
