import { env } from '$env/dynamic/private';
interface LogData {
	level: 'info' | 'error' | 'warn' | 'debug' | 'success';
	message: string;
	args?: any[];
	timestamp: string;
}

interface ProgressData {
	operation: string;
	percent: number;
	details: Record<string, any>;
	timestamp: string;
}

class Logger {
	private log(level: LogData['level'], message: string, ...args: any[]) {
		const timestamp = new Date().toLocaleTimeString();

		// Use appropriate console methods based on log level
		switch (level) {
			case 'error':
				console.error(`[${timestamp}] ❌ ${message}`, ...args);
				break;
			case 'warn':
				console.warn(`[${timestamp}] ⚠️  ${message}`, ...args);
				break;
			case 'debug':
				if (env.DEBUG === 'true') {
					console.debug(`[${timestamp}] 🔍 ${message}`, ...args);
				}
				break;
			case 'success':
				console.log(`[${timestamp}] ✅ ${message}`, ...args);
				break;
			case 'info':
			default:
				console.info(`[${timestamp}] ℹ️  ${message}`, ...args);
				break;
		}
	}

	info(message: string, ...args: any[]) {
		this.log('info', message, ...args);
	}

	success(message: string, ...args: any[]) {
		this.log('success', message, ...args);
	}

	error(message: string, ...args: any[]) {
		this.log('error', message, ...args);
	}

	warn(message: string, ...args: any[]) {
		this.log('warn', message, ...args);
	}

	debug(message: string, ...args: any[]) {
		this.log('debug', message, ...args);
	}

	progress(operation: string, percent: number, details: Record<string, any> = {}) {
		const timestamp = new Date().toLocaleTimeString();
		console.log(`[${timestamp}] 🔄 Progress: ${operation} - ${percent.toFixed(1)}%`, details);
		// No socket emission - just console logging
	}

	// Additional utility methods
	table(data: any) {
		console.table(data);
	}

	group(label: string) {
		console.group(`🔗 ${label}`);
	}

	groupEnd() {
		console.groupEnd();
	}

	time(label: string) {
		console.time(`⏱️  ${label}`);
	}

	timeEnd(label: string) {
		console.timeEnd(`⏱️  ${label}`);
	}

	clear() {
		console.clear();
	}

	// Trace for debugging
	trace(message: string, ...args: any[]) {
		if (env.DEBUG === 'true') {
			console.trace(`🔍 TRACE: ${message}`, ...args);
		}
	}
}

export const logger = new Logger();
