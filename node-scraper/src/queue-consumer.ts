import { RedisManager } from './utils/redis';
import { logger } from './utils/logger';
import { ApplicationProcessor } from './application-processor';
import { JobApplicationTask, UpdateJobStatusTask, ApprovalRequestTask, TaskType } from './types/tasks';

class JobApplicationService {
    private redisClient: RedisManager;
    private processor: ApplicationProcessor;
    private isRunning = false;
    private heartbeatInterval?: NodeJS.Timeout;

    constructor() {
        this.redisClient = new RedisManager();
        this.processor = new ApplicationProcessor(this.redisClient);
    }

    async start(): Promise<void> {
        try {
            logger.info('Starting Job Application Service...');
            
            await this.redisClient.connect();
            logger.info('Connected to Redis');

            // Initialize ApplicationProcessor (which includes Stagehand)
            await this.processor.initialize();

            // Start heartbeat
            this.startHeartbeat();

            this.isRunning = true;

            // Start processing tasks using ApplicationProcessor
            await this.processor.startProcessing();

        } catch (error) {
            logger.error('Failed to start service:', error);
            throw error;
        }
    }

    private startHeartbeat(): void {
        this.heartbeatInterval = setInterval(async () => {
            try {
                await this.redisClient.publish('heartbeat:node-scraper', {
                    service: 'node-scraper',
                    timestamp: new Date().toISOString(),
                    status: 'healthy'
                });
            } catch (error) {
                logger.error('Failed to send heartbeat:', error);
            }
        }, 30000); // Every 30 seconds
    }

    private async processJobApplications(): Promise<void> {
        // This method is no longer needed as ApplicationProcessor handles the processing loop
        logger.info('Processing delegated to ApplicationProcessor');
    }

    private async handleJobApplication(task: JobApplicationTask): Promise<void> {
        // This method is no longer needed as ApplicationProcessor handles individual tasks
        logger.info('Task handling delegated to ApplicationProcessor');
    }

    async shutdown(): Promise<void> {
        logger.info('Shutting down Job Application Service...');
        
        this.isRunning = false;

        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
        
        logger.info('Stopping job application processing...');
        
        try {
            await this.processor.stopProcessing();
            await this.processor.cleanup();
            logger.info('ApplicationProcessor cleaned up');
        } catch (error) {
            logger.error('Error cleaning up ApplicationProcessor:', error);
        }
        
        try {
            await this.redisClient.disconnect();
            logger.info('Redis client disconnected');
        } catch (error) {
            logger.error('Error disconnecting Redis client:', error);
        }
        
        logger.info('Service shutdown complete');
    }

    // Health check method
    async healthCheck(): Promise<boolean> {
        try {
            return await this.redisClient.healthCheck();
        } catch (error) {
            return false;
        }
    }
}

// Main execution
async function main() {
    const service = new JobApplicationService();
    
    // Handle graceful shutdown
    process.on('SIGINT', async () => {
        logger.info('Received SIGINT, shutting down gracefully...');
        await service.shutdown();
        process.exit(0);
    });
    
    process.on('SIGTERM', async () => {
        logger.info('Received SIGTERM, shutting down gracefully...');
        await service.shutdown();
        process.exit(0);
    });
    
    try {
        await service.start();
    } catch (error) {
        logger.error('Failed to start service:', error);
        process.exit(1);
    }
}

// Start the service
if (require.main === module) {
    main().catch((error) => {
        logger.error('Unhandled error in main:', error);
        process.exit(1);
    });
} 

export { JobApplicationService }; 