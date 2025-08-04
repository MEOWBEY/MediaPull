import { env } from '$env/dynamic/private';

type LogLevel = 'info' | 'error' | 'warn' | 'debug' | 'success';

interface ProgressDetails {
	[key: string]: unknown;
}

class Logger {
	private log(level: LogLevel, message: string, ...args: unknown[]): void {
		const timestamp = new Date().toLocaleTimeString();

		switch (level) {
			case 'error':
				console.error(`[${timestamp}] ERROR ${message}`, ...args);
				break;
			case 'warn':
				console.warn(`[${timestamp}] WARN ${message}`, ...args);
				break;
			case 'debug':
				if (env.DEBUG === 'true') {
					console.debug(`[${timestamp}] DEBUG ${message}`, ...args);
				}
				break;
			case 'success':
				console.log(`[${timestamp}] SUCCESS ${message}`, ...args);
				break;
			case 'info':
			default:
				console.info(`[${timestamp}] INFO ${message}`, ...args);
				break;
		}
	}

	info(message: string, ...args: unknown[]): void {
		this.log('info', message, ...args);
	}

	success(message: string, ...args: unknown[]): void {
		this.log('success', message, ...args);
	}

	error(message: string, ...args: unknown[]): void {
		this.log('error', message, ...args);
	}

	warn(message: string, ...args: unknown[]): void {
		this.log('warn', message, ...args);
	}

	debug(message: string, ...args: unknown[]): void {
		this.log('debug', message, ...args);
	}

	progress(operation: string, percent: number, details: ProgressDetails = {}): void {
		const timestamp = new Date().toLocaleTimeString();
		const formattedPercent = Math.max(0, Math.min(100, percent)).toFixed(1);
		console.log(`[${timestamp}] PROGRESS: ${operation} - ${formattedPercent}%`, details);
	}

	trace(message: string, ...args: unknown[]): void {
		if (env.DEBUG === 'true') {
			console.trace(`TRACE: ${message}`, ...args);
		}
	}
}

export const logger = new Logger();
