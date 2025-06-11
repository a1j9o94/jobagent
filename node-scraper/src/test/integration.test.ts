import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import { RedisManager } from '../utils/redis';
import { ApplicationProcessor } from '../application-processor';
import { TaskType, JobApplicationTask } from '../types/tasks';

// Integration tests require Redis to be running
describe('Integration Tests', () => {
  let redisManager: RedisManager;
  let processor: ApplicationProcessor;

  beforeAll(async () => {
    // Skip integration tests if Redis is not available
    const testRedisUrl = process.env.NODE_REDIS_URL || 'redis://localhost:6380';
    redisManager = new RedisManager(testRedisUrl);
    
    try {
      await redisManager.connect();
      const isHealthy = await redisManager.healthCheck();
      if (!isHealthy) {
        console.log('Skipping integration tests - Redis not available');
        return;
      }
      
      processor = new ApplicationProcessor(redisManager);
      await processor.initialize();
    } catch (error) {
      console.log('Skipping integration tests - Redis connection failed');
      return;
    }
  }, 5000); // Reduced timeout

  afterAll(async () => {
    if (processor) {
      await processor.cleanup();
    }
    if (redisManager) {
      await redisManager.disconnect();
    }
  });

  it('should handle complete job application workflow', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    // Create a sample job application task
    const jobApplicationPayload: JobApplicationTask = {
      job_id: 123,
      job_url: 'https://example.com/test-job',
      company: 'TestCorp Integration',
      title: 'Integration Test Engineer',
      user_data: {
        name: 'Test User',
        email: 'test@example.com',
        phone: '+1234567890',
        first_name: 'Test',
        last_name: 'User'
      },
      application_id: 456
    };

    // Publish job application task
    const taskId = await redisManager.publishTask(TaskType.JOB_APPLICATION, jobApplicationPayload);
    expect(taskId).toBeDefined();
    expect(taskId).toMatch(/^job_application_\d+_[a-z0-9]+$/);

    // Verify task was queued
    const queueLength = await redisManager.getQueueLength(TaskType.JOB_APPLICATION);
    expect(queueLength).toBeGreaterThanOrEqual(1);

    // Consume the task
    const consumedTask = await redisManager.consumeTask(TaskType.JOB_APPLICATION);
    expect(consumedTask).toBeDefined();
    expect(consumedTask?.id).toBe(taskId);
    expect((consumedTask?.payload as any)?.job_id).toBe(123);
    expect((consumedTask?.payload as any)?.company).toBe('TestCorp Integration');

    // Verify queue length decreased
    const newQueueLength = await redisManager.getQueueLength(TaskType.JOB_APPLICATION);
    expect(newQueueLength).toBe(queueLength - 1);
  }, 15000); // Extended timeout for Redis operations

  it('should handle queue statistics correctly', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    // Get initial stats
    const initialStats = await redisManager.getQueueStats();
    expect(initialStats).toBeDefined();
    expect(typeof initialStats.job_application).toBe('number');

    // Add some tasks
    await redisManager.publishTask(TaskType.UPDATE_JOB_STATUS, {
      job_id: 1,
      application_id: 1,
      status: 'applied'
    });

    await redisManager.publishTask(TaskType.APPROVAL_REQUEST, {
      job_id: 2,
      application_id: 2,
      question: 'Test question?'
    });

    // Check updated stats
    const updatedStats = await redisManager.getQueueStats();
    expect(updatedStats.update_job_status).toBeGreaterThanOrEqual(initialStats.update_job_status + 1);
    expect(updatedStats.approval_request).toBeGreaterThanOrEqual(initialStats.approval_request + 1);

    // Clean up by consuming the tasks
    await redisManager.consumeTask(TaskType.UPDATE_JOB_STATUS);
    await redisManager.consumeTask(TaskType.APPROVAL_REQUEST);
  }, 10000);

  it('should handle processor health check', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    const health = await processor.healthCheck();
    expect(health.status).toBe('healthy');
    expect(health.details.redis).toBe(true);
    expect(health.details.isProcessing).toBe(false);
    expect(health.details.queueStats).toBeDefined();
  });

  it('should handle multiple task types in correct order', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    // Publish tasks in order
    const task1Id = await redisManager.publishTask(TaskType.JOB_APPLICATION, {
      job_id: 1,
      job_url: 'https://example.com/job1',
      company: 'Company1',
      title: 'Job1',
      user_data: { name: 'User1', email: 'user1@example.com', phone: '+1111111111' },
      application_id: 1
    });

    const task2Id = await redisManager.publishTask(TaskType.JOB_APPLICATION, {
      job_id: 2,
      job_url: 'https://example.com/job2',
      company: 'Company2',
      title: 'Job2',
      user_data: { name: 'User2', email: 'user2@example.com', phone: '+2222222222' },
      application_id: 2
    });

    // Consume in FIFO order
    const firstTask = await redisManager.consumeTask(TaskType.JOB_APPLICATION);
    const secondTask = await redisManager.consumeTask(TaskType.JOB_APPLICATION);

    expect(firstTask?.id).toBe(task1Id);
    expect((firstTask?.payload as any)?.job_id).toBe(1);
    
    expect(secondTask?.id).toBe(task2Id);
    expect((secondTask?.payload as any)?.job_id).toBe(2);
  });
}); 