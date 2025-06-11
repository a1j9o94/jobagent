import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

import { logger } from './utils/logger';
import { RedisManager } from './utils/redis';
import { ApplicationProcessor } from './application-processor';

class JobApplicationService {
    private redis: RedisManager;
    private processor: ApplicationProcessor;
    private isShuttingDown: boolean = false;
    private heartbeatInterval?: NodeJS.Timeout;

    constructor() {
        this.redis = new RedisManager();
        this.processor = new ApplicationProcessor(this.redis);
    }

    async start(): Promise<void> {
        logger.info('Starting Job Application Service...');

        try {
            // Connect to Redis
            await this.redis.connect();
            logger.info('Connected to Redis');

            // Initialize the application processor
            await this.processor.initialize();
            logger.info('Application processor initialized');

            // Set up graceful shutdown
            this.setupGracefulShutdown();

            // Start heartbeat publishing
            this.startHeartbeat();

            // Start processing job applications
            await this.processor.startProcessing();

        } catch (error) {
            logger.error('Failed to start service:', error);
            await this.shutdown();
            process.exit(1);
        }
    }

    private startHeartbeat(): void {
        logger.info('Starting heartbeat publishing...');
        this.heartbeatInterval = setInterval(async () => {
            try {
                const heartbeatData = {
                    timestamp: new Date().toISOString(),
                    status: 'alive',
                    uptime: process.uptime(),
                    memory: process.memoryUsage(),
                    service: 'node-scraper'
                };

                await this.redis.publish('heartbeat:node-scraper', heartbeatData);
                logger.debug('Heartbeat published successfully');
            } catch (error) {
                logger.error('Failed to publish heartbeat:', error);
            }
        }, 30000); // Every 30 seconds
    }

    private setupGracefulShutdown(): void {
        const signals: NodeJS.Signals[] = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

        signals.forEach(signal => {
            process.on(signal, async () => {
                if (this.isShuttingDown) {
                    logger.warn(`Received ${signal} during shutdown, forcing exit`);
                    process.exit(1);
                }

                logger.info(`Received ${signal}, starting graceful shutdown...`);
                this.isShuttingDown = true;
                await this.shutdown();
                process.exit(0);
            });
        });

        // Handle uncaught exceptions
        process.on('uncaughtException', (error) => {
            logger.error('Uncaught Exception:', error);
            this.shutdown().then(() => process.exit(1));
        });

        // Handle unhandled promise rejections
        process.on('unhandledRejection', (reason, promise) => {
            logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
            this.shutdown().then(() => process.exit(1));
        });
    }

    async shutdown(): Promise<void> {
        if (this.isShuttingDown) {
            return;
        }

        logger.info('Shutting down Job Application Service...');
        this.isShuttingDown = true;

        try {
            // Stop processing new tasks
            await this.processor.stopProcessing();

            // Clean up resources
            await this.processor.cleanup();

            // Disconnect from Redis
            await this.redis.disconnect();

            // Stop heartbeat publishing
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
            }

            logger.info('Service shutdown complete');
        } catch (error) {
            logger.error('Error during shutdown:', error);
        }
    }

    async healthCheck(): Promise<any> {
        try {
            const processorHealth = await this.processor.healthCheck();
            const redisHealth = await this.redis.healthCheck();

            return {
                status: processorHealth.status === 'healthy' && redisHealth ? 'healthy' : 'unhealthy',
                timestamp: new Date().toISOString(),
                details: {
                    processor: processorHealth,
                    redis: redisHealth,
                    uptime: process.uptime(),
                    memory: process.memoryUsage()
                }
            };
        } catch (error) {
            return {
                status: 'unhealthy',
                timestamp: new Date().toISOString(),
                error: error instanceof Error ? error.message : String(error)
            };
        }
    }
}

// Main execution
async function main() {
    const service = new JobApplicationService();
    
    try {
        await service.start();
    } catch (error) {
        logger.error('Service failed to start:', error);
        process.exit(1);
    }
}

// Export for testing purposes
export { JobApplicationService };

// Start the service if this file is run directly
if (require.main === module) {
    main().catch((error) => {
        logger.error('Fatal error:', error);
        process.exit(1);
    });
} 