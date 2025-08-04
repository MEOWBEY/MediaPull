import puppeteer, { Browser, Page, Dialog } from 'puppeteer-core';
import chromium from '@sparticuz/chromium';
import { logger } from './logger.js';
import { env } from '$env/dynamic/private';
import { platform } from 'os';
import { existsSync } from 'fs';

export interface VideoInfo {
	videoSrc: string;
	cookies: unknown[];
	userAgent: string;
	requestHeaders: Record<string, string>;
	filename?: string;
	size?: string;
}

interface BrowserConfig {
	executablePath: string;
	headless: boolean;
	args: string[];
	timeout: number;
	defaultViewport?: { width: number; height: number } | null;
}

interface VideoElement {
	src: string;
	duration: number;
	videoWidth: number;
	videoHeight: number;
	readyState: number;
}

type PlatformType = 'win32' | 'darwin' | 'linux';

class PuppeteerService {
	private readonly config = {
		isProduction: env.VERCEL === '1' || env.NODE_ENV === 'production',
		timeout: this.parseTimeout(env.BROWSER_TIMEOUT, 600000), // 10 minutes default
		launchTimeout: this.parseTimeout(env.BROWSER_LAUNCH_TIMEOUT, 120000), // 2 minutes default
		selectorTimeout: 120000, // 2 minutes for selectors
		dialogTimeout: 120000, // 2 minutes for dialog
		userAgent:
			env.USER_AGENT ||
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
	};

	private parseTimeout(value: string | undefined, defaultValue: number): number {
		return value ? parseInt(value, 10) || defaultValue : defaultValue;
	}

	private async getExecutablePath(): Promise<string> {
		if (this.config.isProduction) {
			return await chromium.executablePath();
		}

		if (env.CHROME_EXECUTABLE_PATH && existsSync(env.CHROME_EXECUTABLE_PATH)) {
			return env.CHROME_EXECUTABLE_PATH;
		}

		return this.findSystemChrome();
	}

	private findSystemChrome(): string {
		const currentPlatform = platform() as PlatformType;
		const paths = this.getChromePaths(currentPlatform);

		for (const path of paths) {
			if (path && existsSync(path)) {
				logger.debug(`Found Chrome at: ${path}`);
				return path;
			}
		}

		throw new Error('Chrome not found. Install Chrome or set CHROME_EXECUTABLE_PATH in .env');
	}

	private getChromePaths(platformType: PlatformType): string[] {
		const pathMap: Record<PlatformType, string[]> = {
			win32: this.getWindowsChromePaths(),
			darwin: ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
			linux: [
				'/usr/bin/google-chrome-stable',
				'/usr/bin/google-chrome',
				'/usr/bin/chromium-browser',
				'/usr/bin/chromium',
				'/snap/bin/chromium'
			]
		};

		return pathMap[platformType] || [];
	}

	private getWindowsChromePaths(): string[] {
		const programFiles = env.PROGRAMFILES || 'C:\\Program Files';
		const programFilesX86 = env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)';
		const localAppData = env.LOCALAPPDATA || '';

		return [
			`${programFiles}\\Google\\Chrome\\Application\\chrome.exe`,
			`${programFilesX86}\\Google\\Chrome\\Application\\chrome.exe`,
			`${localAppData}\\Google\\Chrome\\Application\\chrome.exe`
		].filter(Boolean);
	}

	private getBrowserArgs(): string[] {
		const baseArgs = [
			'--no-sandbox',
			'--disable-setuid-sandbox',
			'--disable-dev-shm-usage',
			'--disable-gpu',
			'--disable-web-security',
			'--disable-features=VizDisplayCompositor',
			'--disable-background-timer-throttling',
			'--disable-backgrounding-occluded-windows',
			'--disable-renderer-backgrounding',
			'--disable-blink-features=AutomationControlled',
			'--disable-extensions-file-access-check',
			'--disable-extensions-http-throttling'
		];

		if (this.config.isProduction) {
			baseArgs.push(...chromium.args, '--single-process', '--no-zygote');
		}

		if (env.HEADLESS !== 'false') {
			baseArgs.push('--headless=new');
		}

		return baseArgs;
	}

	private async createBrowserConfig(): Promise<BrowserConfig> {
		return {
			executablePath: await this.getExecutablePath(),
			headless: env.HEADLESS !== 'false',
			args: this.getBrowserArgs(),
			timeout: this.config.launchTimeout,
			defaultViewport: this.config.isProduction ? { width: 1280, height: 1024 } : null
		};
	}

	private async launchBrowser(): Promise<Browser> {
		try {
			const config = await this.createBrowserConfig();
			logger.info(`Launching browser with ${this.config.timeout / 1000}s timeout`);

			const browser = await puppeteer.launch({
				...config,
				ignoreDefaultArgs: ['--disable-extensions']
			});

			logger.success('Browser launched successfully');
			return browser;
		} catch (error) {
			const errorMessage = error instanceof Error ? error.message : 'Unknown error';
			logger.error('Browser launch failed:', errorMessage);
			throw new Error(`Browser launch failed: ${errorMessage}`);
		}
	}

	private async setupPage(browser: Browser): Promise<Page> {
		const page = await browser.newPage();

		await Promise.all([
			page.setUserAgent(this.config.userAgent),
			page.setViewport({ width: 1920, height: 1080 }),
			page.setExtraHTTPHeaders({
				'Accept-Language': 'en-US,en;q=0.9',
				'Accept-Encoding': 'gzip, deflate, br',
				Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
			})
		]);

		page.setDefaultTimeout(this.config.selectorTimeout);
		page.setDefaultNavigationTimeout(this.config.timeout);

		await this.setupRequestBlocking(page);
		return page;
	}

	private async setupRequestBlocking(page: Page): Promise<void> {
		await page.setRequestInterception(true);

		page.on('request', (request) => {
			const url = request.url();
			const resourceType = request.resourceType();

			const shouldBlock = this.shouldBlockResource(url, resourceType);
			if (shouldBlock) {
				request.abort();
			} else {
				request.continue();
			}
		});
	}

	private shouldBlockResource(url: string, resourceType: string): boolean {
		const blockedPatterns = ['ads', 'analytics', 'tracking', 'facebook', 'google-analytics'];
		const blockedTypes = ['stylesheet', 'font'];

		if (resourceType === 'image' && !url.includes('video')) {
			return true;
		}

		return (
			blockedPatterns.some((pattern) => url.includes(pattern)) ||
			blockedTypes.includes(resourceType)
		);
	}

	private async navigateToSite(page: Page): Promise<void> {
		logger.info(`Navigating with ${this.config.timeout / 1000}s timeout`);
		await page.goto('https://online-video-cutter.com/', {
			waitUntil: 'networkidle0',
			timeout: this.config.timeout
		});
	}

	private async handleUrlSubmission(page: Page, videoUrl: string): Promise<void> {
		const dialogPromise = this.setupDialogHandler(page, videoUrl);

		await this.clickDropdownMenu(page);
		await this.selectUrlOption(page);

		await Promise.race([
			dialogPromise,
			new Promise<never>((_, reject) =>
				setTimeout(
					() => reject(new Error('Dialog timeout after 120 seconds')),
					this.config.dialogTimeout
				)
			)
		]);
	}

	private setupDialogHandler(page: Page, videoUrl: string): Promise<void> {
		return new Promise<void>((resolve) => {
			let handled = false;
			page.on('dialog', async (dialog: Dialog) => {
				if (!handled) {
					await dialog.accept(videoUrl);
					handled = true;
					logger.progress('video-processing', 50, { message: 'URL submitted' });
					resolve();
				}
			});
		});
	}

	private async clickDropdownMenu(page: Page): Promise<void> {
		await page.waitForSelector('.el-dropdown__icon.el-icon-arrow-down', {
			visible: true,
			timeout: this.config.selectorTimeout
		});
		await page.click('.el-dropdown__icon.el-icon-arrow-down');
		logger.progress('video-processing', 40, { message: 'Dropdown opened' });
	}

	private async selectUrlOption(page: Page): Promise<void> {
		await page.waitForSelector('.el-dropdown-menu__item.url', {
			visible: true,
			timeout: this.config.selectorTimeout
		});
		await page.click('.el-dropdown-menu__item.url');
		logger.progress('video-processing', 60, { message: 'URL option selected' });
	}

	private async extractVideoInfo(page: Page): Promise<VideoInfo> {
		logger.info(`Waiting for video with ${this.config.timeout / 1000}s timeout`);

		await page.waitForSelector('video[src^="https://"], video[src^="blob:"]', {
			timeout: this.config.timeout
		});

		const [videoInfo, cookies, userAgent] = await Promise.all([
			page.evaluate((): VideoElement => {
				const video = document.querySelector('video') as HTMLVideoElement;
				if (!video?.src) throw new Error('Video not found');

				return {
					src: video.src,
					duration: video.duration || 0,
					videoWidth: video.videoWidth || 0,
					videoHeight: video.videoHeight || 0,
					readyState: video.readyState
				};
			}),
			page.cookies(),
			page.evaluate(() => navigator.userAgent)
		]);

		return {
			videoSrc: videoInfo.src,
			cookies,
			userAgent,
			requestHeaders: {
				referer: 'https://online-video-cutter.com/',
				origin: 'https://online-video-cutter.com',
				'user-agent': userAgent
			}
		};
	}

	private async cleanup(browser: Browser | null, page: Page | null): Promise<void> {
		const cleanupTasks: Promise<unknown>[] = [];

		if (page) {
			cleanupTasks.push(
				page.close().catch((error: unknown) => {
					const errorMessage = error instanceof Error ? error.message : 'Unknown error';
					logger.warn('Page cleanup failed:', errorMessage);
				})
			);
		}

		if (browser) {
			cleanupTasks.push(
				browser.close().catch((error: unknown) => {
					const errorMessage = error instanceof Error ? error.message : 'Unknown error';
					logger.warn('Browser cleanup failed:', errorMessage);
				})
			);
		}

		await Promise.all(cleanupTasks);
		logger.info('Cleanup completed');
	}

	async getProcessedVideoInfo(userVideoUrl: string): Promise<VideoInfo> {
		const startTime = Date.now();

		try {
			logger.progress('video-processing', 5, { message: 'Starting processing' });

			const processPromise = this.processVideo(userVideoUrl);
			const timeoutPromise = new Promise<never>((_, reject) =>
				setTimeout(
					() => reject(new Error(`Processing timeout after ${this.config.timeout / 1000} seconds`)),
					this.config.timeout
				)
			);

			const result = await Promise.race([processPromise, timeoutPromise]);

			const duration = Date.now() - startTime;
			logger.success(`Video processed successfully in ${duration}ms`);

			return result;
		} catch (error) {
			const duration = Date.now() - startTime;
			const errorMessage = error instanceof Error ? error.message : 'Unknown error';
			logger.error(`Video processing failed after ${duration}ms:`, errorMessage);
			throw new Error(`Failed to process video: ${errorMessage}`);
		} finally {
			await this.cleanup(null, null);
		}
	}

	private async processVideo(userVideoUrl: string): Promise<VideoInfo> {
		const browser = await this.launchBrowser();
		const page = await this.setupPage(browser);

		logger.progress('video-processing', 10, { message: 'Navigating to site' });
		await this.navigateToSite(page);

		logger.progress('video-processing', 25, { message: 'Site loaded' });
		await this.handleUrlSubmission(page, userVideoUrl);

		logger.progress('video-processing', 70, { message: 'Processing video' });
		const videoInfo = await this.extractVideoInfo(page);

		logger.progress('video-processing', 100, { message: 'Processing completed' });
		return videoInfo;
	}
}

export const puppeteerService = new PuppeteerService();
