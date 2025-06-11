import { createClient, RedisClientType } from 'redis';
import { logger } from './logger';
import { TaskType, QueueTask, TaskResult } from '../types/tasks';

export class RedisManager {
    private client: RedisClientType;
    private isConnected: boolean = false;

    constructor(redisUrl: string = process.env.NODE_REDIS_URL || 'redis://localhost:6379') {
        this.client = createClient({
            url: redisUrl,
            socket: {
                reconnectStrategy: (retries) => Math.min(retries * 50, 500)
            }
        });

        this.client.on('error', (err) => {
            logger.error('Redis Client Error', err);
            this.isConnected = false;
        });

        this.client.on('connect', () => {
            logger.info('Redis Client Connected');
            this.isConnected = true;
        });

        this.client.on('ready', () => {
            logger.info('Redis Client Ready');
            this.isConnected = true;
        });

        this.client.on('end', () => {
            logger.info('Redis Client Connection Ended');
            this.isConnected = false;
        });
    }

    async connect(): Promise<void> {
        if (!this.isConnected) {
            await this.client.connect();
        }
    }

    async disconnect(): Promise<void> {
        if (this.isConnected) {
            await this.client.disconnect();
        }
    }

    private getQueueKey(taskType: TaskType): string {
        return `tasks:${taskType}`;
    }

    async consumeTask<T>(taskType: TaskType, timeout: number = 0): Promise<QueueTask<T> | null> {
        try {
            const queueKey = this.getQueueKey(taskType);
            const result = timeout > 0 
                ? await this.client.blPop(queueKey, timeout)
                : await this.client.lPop(queueKey);

            if (!result) {
                return null;
            }

            const taskData = typeof result === 'string' ? result : result.element;
            const task = JSON.parse(taskData) as QueueTask<T>;
            
            logger.info(`Consumed task ${task.id} of type ${taskType}`);
            return task;
        } catch (error) {
            logger.error(`Error consuming task from ${taskType}:`, error);
            return null;
        }
    }

    async publishTask<T>(taskType: TaskType, payload: T, priority: number = 0): Promise<string> {
        try {
            const taskId = `${taskType}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            const task: QueueTask<T> = {
                id: taskId,
                type: taskType,
                payload,
                retries: 0,
                created_at: new Date().toISOString(),
                priority
            };

            const queueKey = this.getQueueKey(taskType);
            await this.client.rPush(queueKey, JSON.stringify(task));
            
            logger.info(`Published task ${taskId} to ${taskType}`);
            return taskId;
        } catch (error) {
            logger.error(`Error publishing task to ${taskType}:`, error);
            throw error;
        }
    }

    async publishResult(result: TaskResult): Promise<void> {
        try {
            const resultKey = `task_results:${result.task_id}`;
            await this.client.setEx(resultKey, 3600, JSON.stringify(result)); // Expire after 1 hour
            logger.info(`Published result for task ${result.task_id}`);
        } catch (error) {
            logger.error(`Error publishing result for task ${result.task_id}:`, error);
            throw error;
        }
    }

    async publish(channel: string, data: any): Promise<void> {
        try {
            // Store heartbeat data with expiration for health checks
            if (channel.startsWith('heartbeat:')) {
                await this.client.setEx(channel, 120, JSON.stringify(data)); // Expire after 2 minutes
            }
            
            // Also publish to channel for real-time subscribers (optional)
            await this.client.publish(channel, JSON.stringify(data));
            
            logger.debug(`Published to channel ${channel}`);
        } catch (error) {
            logger.error(`Error publishing to channel ${channel}:`, error);
            throw error;
        }
    }

    async getQueueLength(taskType: TaskType): Promise<number> {
        try {
            const queueKey = this.getQueueKey(taskType);
            return await this.client.lLen(queueKey);
        } catch (error) {
            logger.error(`Error getting queue length for ${taskType}:`, error);
            return 0;
        }
    }

    async healthCheck(): Promise<boolean> {
        try {
            const pong = await this.client.ping();
            return pong === 'PONG';
        } catch (error) {
            logger.error('Redis health check failed:', error);
            return false;
        }
    }

    // For debugging and monitoring
    async getQueueStats(): Promise<Record<string, number>> {
        const stats: Record<string, number> = {};
        
        for (const taskType of Object.values(TaskType)) {
            stats[taskType] = await this.getQueueLength(taskType);
        }
        
        return stats;
    }
} 