import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { RedisManager } from './redis';
import { TaskType } from '../types/tasks';

// Mock Redis client
const mockRedisClient = {
  connect: vi.fn().mockResolvedValue(undefined),
  disconnect: vi.fn().mockResolvedValue(undefined),
  ping: vi.fn().mockResolvedValue('PONG'),
  rPush: vi.fn().mockResolvedValue(1),
  lPop: vi.fn().mockResolvedValue(null),
  blPop: vi.fn().mockResolvedValue(null),
  lLen: vi.fn().mockResolvedValue(0),
  setEx: vi.fn().mockResolvedValue('OK'),
  on: vi.fn()
};

vi.mock('redis', () => ({
  createClient: vi.fn(() => mockRedisClient)
}));

describe('RedisManager', () => {
  let redisManager: RedisManager;

  beforeEach(() => {
    vi.clearAllMocks();
    redisManager = new RedisManager('redis://localhost:6380');
  });

  afterEach(async () => {
    if (redisManager) {
      await redisManager.disconnect();
    }
  });

  describe('connection management', () => {
    it('should connect to Redis successfully', async () => {
      await redisManager.connect();
      expect(mockRedisClient.connect).toHaveBeenCalled();
    });

    it('should disconnect from Redis successfully', async () => {
      // Mark as connected first
      (redisManager as any).isConnected = true;
      await redisManager.disconnect();
      expect(mockRedisClient.disconnect).toHaveBeenCalled();
    });

    it('should handle connection errors gracefully', async () => {
      mockRedisClient.connect.mockRejectedValueOnce(new Error('Connection failed'));
      
      await expect(redisManager.connect()).rejects.toThrow('Connection failed');
    });
  });

  describe('task publishing', () => {
    it('should publish a task successfully', async () => {
      const payload = { job_id: 123, job_url: 'https://example.com' };
      
      const taskId = await redisManager.publishTask(TaskType.JOB_APPLICATION, payload);
      
      expect(taskId).toMatch(/^job_application_\d+_[a-z0-9]+$/);
      expect(mockRedisClient.rPush).toHaveBeenCalledWith(
        'tasks:job_application',
        expect.stringContaining('"job_id":123')
      );
    });

    it('should handle publish errors', async () => {
      mockRedisClient.rPush.mockRejectedValueOnce(new Error('Redis error'));
      
      await expect(
        redisManager.publishTask(TaskType.JOB_APPLICATION, { test: 'data' })
      ).rejects.toThrow('Redis error');
    });
  });

  describe('task consumption', () => {
    it('should consume a task successfully', async () => {
      const taskData = {
        id: 'test_task_123',
        type: 'job_application',
        payload: { job_id: 123 },
        retries: 0,
        created_at: new Date().toISOString(),
        priority: 0
      };
      
      mockRedisClient.lPop.mockResolvedValueOnce(JSON.stringify(taskData));
      
      const task = await redisManager.consumeTask(TaskType.JOB_APPLICATION);
      
      expect(task).toBeDefined();
      expect(task?.id).toBe('test_task_123');
      expect((task?.payload as any)?.job_id).toBe(123);
    });

    it('should return null when no tasks are available', async () => {
      mockRedisClient.lPop.mockResolvedValueOnce(null);
      
      const task = await redisManager.consumeTask(TaskType.JOB_APPLICATION);
      
      expect(task).toBeNull();
    });

    it('should handle blocking pop with timeout', async () => {
      const taskData = {
        id: 'test_task_456',
        type: 'job_application',
        payload: { job_id: 456 },
        retries: 0,
        created_at: new Date().toISOString(),
        priority: 0
      };
      
      mockRedisClient.blPop.mockResolvedValueOnce({ key: 'tasks:job_application', element: JSON.stringify(taskData) });
      
      const task = await redisManager.consumeTask(TaskType.JOB_APPLICATION, 5);
      
      expect(task).toBeDefined();
      expect(task?.id).toBe('test_task_456');
      expect(mockRedisClient.blPop).toHaveBeenCalledWith('tasks:job_application', 5);
    });
  });

  describe('queue statistics', () => {
    it('should get queue length correctly', async () => {
      mockRedisClient.lLen.mockResolvedValueOnce(5);
      
      const length = await redisManager.getQueueLength(TaskType.JOB_APPLICATION);
      
      expect(length).toBe(5);
      expect(mockRedisClient.lLen).toHaveBeenCalledWith('tasks:job_application');
    });

    it('should get statistics for all queues', async () => {
      mockRedisClient.lLen
        .mockResolvedValueOnce(3) // job_application
        .mockResolvedValueOnce(1) // update_job_status
        .mockResolvedValueOnce(0) // approval_request
        .mockResolvedValueOnce(2); // send_notification
      
      const stats = await redisManager.getQueueStats();
      
      expect(stats).toEqual({
        job_application: 3,
        update_job_status: 1,
        approval_request: 0,
        send_notification: 2
      });
    });
  });

  describe('health check', () => {
    it('should return true for healthy Redis connection', async () => {
      mockRedisClient.ping.mockResolvedValueOnce('PONG');
      
      const isHealthy = await redisManager.healthCheck();
      
      expect(isHealthy).toBe(true);
    });

    it('should return false for unhealthy Redis connection', async () => {
      mockRedisClient.ping.mockRejectedValueOnce(new Error('Connection lost'));
      
      const isHealthy = await redisManager.healthCheck();
      
      expect(isHealthy).toBe(false);
    });
  });
}); 