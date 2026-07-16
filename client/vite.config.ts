import path from 'path';

import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// In dev, forward the backend routes to the Python server so the client can use
// relative URLs (no CORS). Override the target with VITE_API_BASE_URL if needed.
const backend = process.env.VITE_API_BASE_URL || 'http://localhost:8000';
const proxied = [
	'/extract-videos',
	'/extract-gallery',
	'/proxy-video',
	'/proxy-token',
	'/health',
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
