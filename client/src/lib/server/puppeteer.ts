import puppeteer from 'puppeteer-core';
import chromium from '@sparticuz/chromium';
import { logger } from './logger.js';
import { env } from '$env/dynamic/private';
import { platform } from 'os';
import { existsSync } from 'fs';

export interface VideoInfo {
	videoSrc: string;
	cookies: any[];
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
	defaultViewport?: any;
}

class PuppeteerService {
	private readonly isProduction =
		env.VERCEL === '1' || env.NODE_ENV === 'production';
	private readonly timeout = parseInt(env.BROWSER_TIMEOUT || '600000'); // 10 minutes default
	private readonly launchTimeout = parseInt(env.BROWSER_LAUNCH_TIMEOUT || '120000'); // 2 minute default
	private readonly selectorTimeout = 120000; // 2 minute for selectors
	private readonly dialogTimeout = 120000; // 120 seconds for dialog

	private async getExecutablePath(): Promise<string> {
		if (this.isProduction) {
			return await chromium.executablePath();
		}

		if (env.CHROME_EXECUTABLE_PATH) {
			return env.CHROME_EXECUTABLE_PATH;
		}

		return this.findSystemChrome();
	}

	private findSystemChrome(): string {
		const currentPlatform = platform();
		const paths = this.getChromePaths(currentPlatform);

		for (const path of paths) {
			if (path && existsSync(path)) {
				return path;
			}
		}

		throw new Error(`Chrome not found. Install Chrome or set CHROME_EXECUTABLE_PATH in .env`);
	}

	private getChromePaths(platform: string): string[] {
		const pathMap: Record<string, string[]> = {
			win32: [
				'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
				'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
				`${env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`,
				`${env.PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe`,
				`${env['PROGRAMFILES(X86)']}\\Google\\Chrome\\Application\\chrome.exe`
			],
			darwin: ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
			linux: [
				'/usr/bin/google-chrome-stable',
				'/usr/bin/google-chrome',
				'/usr/bin/chromium-browser',
				'/usr/bin/chromium',
				'/snap/bin/chromium'
			]
		};

		return pathMap[platform] || [];
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

		if (this.isProduction) {
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
			timeout: this.launchTimeout,
			defaultViewport: this.isProduction ? chromium.defaultViewport : null
		};
	}

	private async launchBrowser() {
		try {
			const config = await this.createBrowserConfig();
			logger.info(`Launching browser with ${this.timeout / 1000}s timeout`);

			const browser = await puppeteer.launch({
				...config,
				ignoreHTTPSErrors: true,
				ignoreDefaultArgs: ['--disable-extensions']
			});

			logger.success('Browser launched successfully');
			return browser;
		} catch (error: any) {
			logger.error('Browser launch failed:', error.message);
			throw new Error(`Browser launch failed: ${error.message}`);
		}
	}

	private async setupPage(browser: any) {
		const page = await browser.newPage();

		const userAgent =
			env.USER_AGENT ||
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

		await Promise.all([
			page.setUserAgent(userAgent),
			page.setViewport({ width: 1920, height: 1080 }),
			page.setExtraHTTPHeaders({
				'Accept-Language': 'en-US,en;q=0.9',
				'Accept-Encoding': 'gzip, deflate, br',
				Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
			})
		]);

		// Set page timeout
		page.setDefaultTimeout(this.selectorTimeout);
		page.setDefaultNavigationTimeout(this.timeout);

		await this.setupRequestBlocking(page);
		return page;
	}

	private async setupRequestBlocking(page: any): Promise<void> {
		await page.setRequestInterception(true);

		page.on('request', (request: any) => {
			const url = request.url();
			const resourceType = request.resourceType();

			const shouldBlock = this.shouldBlockResource(url, resourceType);
			shouldBlock ? request.abort() : request.continue();
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

	private async navigateToSite(page: any): Promise<void> {
		logger.info(`Navigating with ${this.timeout / 1000}s timeout`);
		await page.goto('https://online-video-cutter.com/', {
			waitUntil: 'networkidle0',
			timeout: this.timeout
		});
	}

	private async handleUrlSubmission(page: any, videoUrl: string): Promise<void> {
		const dialogPromise = this.setupDialogHandler(page, videoUrl);

		await this.clickDropdownMenu(page);
		await this.selectUrlOption(page);

		await Promise.race([
			dialogPromise,
			new Promise((_, reject) =>
				setTimeout(() => reject(new Error('Dialog timeout after 120 seconds')), this.dialogTimeout)
			)
		]);
	}

	private setupDialogHandler(page: any, videoUrl: string): Promise<void> {
		return new Promise((resolve) => {
			let handled = false;
			page.on('dialog', async (dialog: any) => {
				if (!handled) {
					await dialog.accept(videoUrl);
					handled = true;
					logger.progress('video-processing', 50, { message: 'URL submitted' });
					resolve();
				}
			});
		});
	}

	private async clickDropdownMenu(page: any): Promise<void> {
		await page.waitForSelector('.el-dropdown__icon.el-icon-arrow-down', {
			visible: true,
			timeout: this.selectorTimeout
		});
		await page.click('.el-dropdown__icon.el-icon-arrow-down');
		logger.progress('video-processing', 40, { message: 'Dropdown opened' });
	}

	private async selectUrlOption(page: any): Promise<void> {
		await page.waitForSelector('.el-dropdown-menu__item.url', {
			visible: true,
			timeout: this.selectorTimeout
		});
		await page.click('.el-dropdown-menu__item.url');
		logger.progress('video-processing', 60, { message: 'URL option selected' });
	}

	private async extractVideoInfo(page: any): Promise<VideoInfo> {
		logger.info(`Waiting for video with ${this.timeout / 1000}s timeout`);

		await page.waitForSelector('video[src^="https://"], video[src^="blob:"]', {
			timeout: this.timeout
		});

		const [videoInfo, cookies, userAgent] = await Promise.all([
			page.evaluate(() => {
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

	private async cleanup(browser: any, page: any): Promise<void> {
		const cleanupTasks = [];

		if (page) {
			cleanupTasks.push(page.close().catch((e: any) => logger.warn('Page cleanup failed:', e)));
		}

		if (browser) {
			cleanupTasks.push(
				browser.close().catch((e: any) => logger.warn('Browser cleanup failed:', e))
			);
		}

		await Promise.all(cleanupTasks);
		logger.info('Cleanup completed');
	}

	async getProcessedVideoInfo(userVideoUrl: string): Promise<VideoInfo> {
		let browser: any = null;
		let page: any = null;
		const startTime = Date.now();

		try {
			logger.progress('video-processing', 5, { message: 'Starting processing' });

			// Overall timeout wrapper
			const processPromise = this.processVideo(userVideoUrl);
			const timeoutPromise = new Promise((_, reject) =>
				setTimeout(
					() => reject(new Error(`Processing timeout after ${this.timeout / 1000} seconds`)),
					this.timeout
				)
			);

			const result = await Promise.race([processPromise, timeoutPromise]);

			const duration = Date.now() - startTime;
			logger.success(`Video processed successfully in ${duration}ms`);

			return result as VideoInfo;
		} catch (error: any) {
			const duration = Date.now() - startTime;
			logger.error(`Video processing failed after ${duration}ms:`, error.message);
			throw new Error(`Failed to process video: ${error.message}`);
		} finally {
			await this.cleanup(browser, page);
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
