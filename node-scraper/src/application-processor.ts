import { logger } from './utils/logger';
import { RedisManager } from './utils/redis';
import { StagehandWrapper } from './stagehand-wrapper';
import { 
    JobApplicationTask, 
    UpdateJobStatusTask, 
    ApprovalRequestTask,
    TaskType,
    QueueTask,
    TaskResult
} from './types/tasks';
import { ApplicationResult } from './types/stagehand';

export class ApplicationProcessor {
    private redis: RedisManager;
    private stagehand: StagehandWrapper;
    private isProcessing: boolean = false;
    private maxRetries: number;

    constructor(redis: RedisManager) {
        this.redis = redis;
        this.stagehand = new StagehandWrapper();
        this.maxRetries = parseInt(process.env.MAX_RETRIES || '3');
    }

    async initialize(): Promise<void> {
        try {
            await this.stagehand.initialize();
            logger.info('Application processor initialized successfully');
        } catch (error) {
            logger.error('Failed to initialize application processor:', error);
            throw error;
        }
    }

    async cleanup(): Promise<void> {
        try {
            await this.stagehand.cleanup();
            logger.info('Application processor cleaned up successfully');
        } catch (error) {
            logger.error('Error during application processor cleanup:', error);
        }
    }

    async startProcessing(): Promise<void> {
        if (this.isProcessing) {
            logger.warn('Processor is already running');
            return;
        }

        this.isProcessing = true;
        logger.info('Starting job application processing...');

        while (this.isProcessing) {
            try {
                // Wait for new job application tasks (blocking with 5 second timeout)
                const task = await this.redis.consumeTask<JobApplicationTask>(
                    TaskType.JOB_APPLICATION, 
                    5
                );

                if (task) {
                    await this.processJobApplicationTask(task);
                }
            } catch (error) {
                logger.error('Error in processing loop:', error);
                // Wait a bit before retrying to avoid tight error loops
                await this.sleep(5000);
            }
        }

        logger.info('Job application processing stopped');
    }

    async stopProcessing(): Promise<void> {
        logger.info('Stopping job application processing...');
        this.isProcessing = false;
    }

    private async processJobApplicationTask(task: QueueTask<JobApplicationTask>): Promise<void> {
        const startTime = Date.now();
        logger.info(`Processing job application task ${task.id} for job ${task.payload.job_id}`);

        try {
            // Process the application using Stagehand
            const result = await this.stagehand.processJobApplication(task.payload);
            const processingTime = Date.now() - startTime;

            logger.info(`Job application ${task.id} processed in ${processingTime}ms`, {
                taskId: task.id,
                jobId: task.payload.job_id,
                success: result.success,
                processingTimeMs: processingTime
            });

            // Handle different result types
            if (result.success) {
                await this.handleSuccessfulApplication(task, result);
            } else if (result.needsApproval) {
                await this.handleApprovalNeeded(task, result);
            } else {
                await this.handleFailedApplication(task, result);
            }

            // Publish task result for monitoring
            await this.redis.publishResult({
                success: result.success,
                task_id: task.id,
                data: result
            });

        } catch (error) {
            logger.error(`Error processing job application task ${task.id}:`, error);
            
            // Handle retry logic
            const shouldRetry = task.retries < this.maxRetries;
            
            if (shouldRetry) {
                await this.retryTask(task, error);
            } else {
                await this.handleMaxRetriesExceeded(task, error);
            }
        }
    }

    private async handleSuccessfulApplication(
        task: QueueTask<JobApplicationTask>, 
        result: ApplicationResult
    ): Promise<void> {
        logger.info(`Job application ${task.payload.job_id} submitted successfully`);

        const updateTask: UpdateJobStatusTask = {
            job_id: task.payload.job_id,
            application_id: task.payload.application_id,
            status: 'applied',
            notes: result.confirmation_message || 'Application submitted successfully',
            screenshot_url: result.screenshot_url,
            submitted_at: result.submitted_at
        };

        await this.redis.publishTask(TaskType.UPDATE_JOB_STATUS, updateTask);
        logger.info(`Published status update for successful application ${task.payload.job_id}`);
    }

    private async handleApprovalNeeded(
        task: QueueTask<JobApplicationTask>, 
        result: ApplicationResult
    ): Promise<void> {
        logger.info(`Job application ${task.payload.job_id} needs user approval`);

        // First, update the job status to waiting_approval
        const updateTask: UpdateJobStatusTask = {
            job_id: task.payload.job_id,
            application_id: task.payload.application_id,
            status: 'waiting_approval',
            notes: 'Application requires user input',
            screenshot_url: result.screenshot_url
        };

        await this.redis.publishTask(TaskType.UPDATE_JOB_STATUS, updateTask);

        // Then, send approval request
        const approvalTask: ApprovalRequestTask = {
            job_id: task.payload.job_id,
            application_id: task.payload.application_id,
            question: result.question || 'User input required to complete application',
            current_state: result.state,
            screenshot_url: result.screenshot_url,
            context: {
                page_title: result.page_title,
                page_url: task.payload.job_url
            }
        };

        await this.redis.publishTask(TaskType.APPROVAL_REQUEST, approvalTask);
        logger.info(`Published approval request for application ${task.payload.job_id}`);
    }

    private async handleFailedApplication(
        task: QueueTask<JobApplicationTask>, 
        result: ApplicationResult
    ): Promise<void> {
        logger.error(`Job application ${task.payload.job_id} failed: ${result.error}`);

        const updateTask: UpdateJobStatusTask = {
            job_id: task.payload.job_id,
            application_id: task.payload.application_id,
            status: 'failed',
            error_message: result.error,
            notes: 'Application failed during automation',
            screenshot_url: result.screenshot_url
        };

        await this.redis.publishTask(TaskType.UPDATE_JOB_STATUS, updateTask);
        logger.info(`Published status update for failed application ${task.payload.job_id}`);
    }

    private async retryTask(task: QueueTask<JobApplicationTask>, error: any): Promise<void> {
        const retryCount = task.retries + 1;
        const delayMs = Math.min(1000 * Math.pow(2, retryCount), 30000); // Exponential backoff, max 30s

        logger.warn(`Retrying task ${task.id} (attempt ${retryCount}/${this.maxRetries}) after ${delayMs}ms`, {
            taskId: task.id,
            jobId: task.payload.job_id,
            error: error instanceof Error ? error.message : String(error)
        });

        // Wait before retrying
        await this.sleep(delayMs);

        // Re-queue the task with incremented retry count
        const retryTask: QueueTask<JobApplicationTask> = {
            ...task,
            retries: retryCount,
            id: `${task.id}_retry_${retryCount}`
        };

        await this.redis.publishTask(TaskType.JOB_APPLICATION, retryTask.payload);
    }

    private async handleMaxRetriesExceeded(
        task: QueueTask<JobApplicationTask>, 
        error: any
    ): Promise<void> {
        logger.error(`Task ${task.id} exceeded maximum retries (${this.maxRetries})`, {
            taskId: task.id,
            jobId: task.payload.job_id,
            error: error instanceof Error ? error.message : String(error)
        });

        const updateTask: UpdateJobStatusTask = {
            job_id: task.payload.job_id,
            application_id: task.payload.application_id,
            status: 'failed',
            error_message: `Failed after ${this.maxRetries} retries: ${error instanceof Error ? error.message : String(error)}`,
            notes: 'Application failed - maximum retries exceeded'
        };

        await this.redis.publishTask(TaskType.UPDATE_JOB_STATUS, updateTask);

        // Publish final task result
        await this.redis.publishResult({
            success: false,
            task_id: task.id,
            error: `Maximum retries exceeded: ${error instanceof Error ? error.message : String(error)}`
        });
    }

    private async sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Health check method
    async healthCheck(): Promise<{ status: string; details: any }> {
        try {
            const redisHealthy = await this.redis.healthCheck();
            const queueStats = await this.redis.getQueueStats();

            return {
                status: redisHealthy ? 'healthy' : 'unhealthy',
                details: {
                    redis: redisHealthy,
                    isProcessing: this.isProcessing,
                    queueStats,
                    maxRetries: this.maxRetries
                }
            };
        } catch (error) {
            return {
                status: 'unhealthy',
                details: {
                    error: error instanceof Error ? error.message : String(error)
                }
            };
        }
    }
} 