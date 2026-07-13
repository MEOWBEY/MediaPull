import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// Unit tests target pure client logic ($lib helpers). We reuse the SvelteKit
// Vite plugin so `$lib` / `$app` aliases resolve exactly as they do at runtime.
export default defineConfig({
	plugins: [sveltekit()],
	test: {
		environment: 'jsdom',
		globals: true,
		include: ['tests/**/*.test.ts']
	}
});
