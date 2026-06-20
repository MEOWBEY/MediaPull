import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// Pure client-rendered SPA (ssr=false): emit static assets with an
		// index.html fallback so client-side routing works. No Node server.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
