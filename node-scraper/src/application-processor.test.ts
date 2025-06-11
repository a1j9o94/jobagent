import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ApplicationProcessor } from './application-processor';
import { RedisManager } from './utils/redis';
import { TaskType, JobApplicationTask } from './types/tasks';

// Mock dependencies
vi.mock('./utils/redis');
vi.mock('./stagehand-wrapper');

// Create mock instances
const mockRedisManager = {
  consumeTask: vi.fn(),
  publishTask: vi.fn(),
  publishResult: vi.fn(),
  healthCheck: vi.fn(),
  getQueueStats: vi.fn()
} as unknown as RedisManager;

const mockStagehandWrapper = {
  initialize: vi.fn().mockResolvedValue(undefined),
  cleanup: vi.fn().mockResolvedValue(undefined),
  processJobApplication: vi.fn()
};

// Mock the StagehandWrapper constructor
vi.mock('./stagehand-wrapper', () => ({
  StagehandWrapper: vi.fn(() => mockStagehandWrapper)
}));

describe('ApplicationProcessor', () => {
  let processor: ApplicationProcessor;

  beforeEach(() => {
    vi.clearAllMocks();
    processor = new ApplicationProcessor(mockRedisManager);
  });

  afterEach(async () => {
    if (processor) {
      await processor.cleanup();
    }
  });

  describe('initialization', () => {
    it('should initialize Stagehand wrapper successfully', async () => {
      await processor.initialize();
      
      expect(mockStagehandWrapper.initialize).toHaveBeenCalled();
    });

    it('should handle initialization errors', async () => {
      mockStagehandWrapper.initialize.mockRejectedValueOnce(new Error('Init failed'));
      
      await expect(processor.initialize()).rejects.toThrow('Init failed');
    });
  });

  describe('cleanup', () => {
    it('should cleanup Stagehand wrapper', async () => {
      await processor.cleanup();
      
      expect(mockStagehandWrapper.cleanup).toHaveBeenCalled();
    });
  });

  describe('health check', () => {
    it('should return healthy status when Redis is healthy', async () => {
      mockRedisManager.healthCheck = vi.fn().mockResolvedValue(true);
      mockRedisManager.getQueueStats = vi.fn().mockResolvedValue({
        job_application: 2,
        update_job_status: 0
      });

      const health = await processor.healthCheck();

      expect(health.status).toBe('healthy');
      expect(health.details.redis).toBe(true);
      expect(health.details.queueStats).toEqual({
        job_application: 2,
        update_job_status: 0
      });
    });

    it('should return unhealthy status when Redis is down', async () => {
      mockRedisManager.healthCheck = vi.fn().mockResolvedValue(false);

      const health = await processor.healthCheck();

      expect(health.status).toBe('unhealthy');
      expect(health.details.redis).toBe(false);
    });
  });

  describe('job application processing', () => {
    const sampleTask = {
      id: 'test_task_123',
      type: TaskType.JOB_APPLICATION,
      payload: {
        job_id: 123,
        job_url: 'https://example.com/job',
        company: 'TestCorp',
        title: 'Software Engineer',
        user_data: {
          name: 'John Doe',
          email: 'john@example.com',
          phone: '+1234567890'
        },
        application_id: 456
      } as JobApplicationTask,
      retries: 0,
      created_at: new Date().toISOString(),
      priority: 0
    };

    it('should handle successful application processing', async () => {
      // Mock successful Stagehand processing
      mockStagehandWrapper.processJobApplication.mockResolvedValueOnce({
        success: true,
        submitted_at: new Date().toISOString(),
        confirmation_message: 'Application submitted successfully',
        screenshot_url: 'http://example.com/screenshot.png'
      });

      // Mock Redis operations
      mockRedisManager.consumeTask = vi.fn().mockResolvedValueOnce(sampleTask);
      mockRedisManager.publishTask = vi.fn().mockResolvedValue('status_update_task_id');
      mockRedisManager.publishResult = vi.fn().mockResolvedValue(undefined);

      // Start processing (we'll manually call the private method for testing)
      // Since startProcessing runs in a loop, we'll test the core logic directly
      const processorAny = processor as any;
      await processorAny.processJobApplicationTask(sampleTask);

      expect(mockStagehandWrapper.processJobApplication).toHaveBeenCalledWith(sampleTask.payload);
      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.UPDATE_JOB_STATUS,
        expect.objectContaining({
          job_id: 123,
          application_id: 456,
          status: 'applied'
        })
      );
    });

    it('should handle application failures', async () => {
      // Mock failed Stagehand processing
      mockStagehandWrapper.processJobApplication.mockResolvedValueOnce({
        success: false,
        error: 'Failed to submit application',
        screenshot_url: 'http://example.com/error_screenshot.png'
      });

      mockRedisManager.publishTask = vi.fn().mockResolvedValue('status_update_task_id');
      mockRedisManager.publishResult = vi.fn().mockResolvedValue(undefined);

      const processorAny = processor as any;
      await processorAny.processJobApplicationTask(sampleTask);

      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.UPDATE_JOB_STATUS,
        expect.objectContaining({
          job_id: 123,
          application_id: 456,
          status: 'failed',
          error_message: 'Failed to submit application'
        })
      );
    });

    it('should handle approval needed scenarios', async () => {
      // Mock approval needed response
      mockStagehandWrapper.processJobApplication.mockResolvedValueOnce({
        success: false,
        needsApproval: true,
        question: 'What is your salary expectation?',
        state: '{"page": "application_form"}',
        screenshot_url: 'http://example.com/approval_screenshot.png'
      });

      mockRedisManager.publishTask = vi.fn().mockResolvedValue('task_id');
      mockRedisManager.publishResult = vi.fn().mockResolvedValue(undefined);

      const processorAny = processor as any;
      await processorAny.processJobApplicationTask(sampleTask);

      // Should publish both status update and approval request
      expect(mockRedisManager.publishTask).toHaveBeenCalledTimes(2);
      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.UPDATE_JOB_STATUS,
        expect.objectContaining({
          status: 'waiting_approval'
        })
      );
      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.APPROVAL_REQUEST,
        expect.objectContaining({
          question: 'What is your salary expectation?',
          current_state: '{"page": "application_form"}'
        })
      );
    });

    it('should handle processing errors with retry logic', async () => {
      const errorTask = { ...sampleTask, retries: 0 };

      // Mock Stagehand error
      mockStagehandWrapper.processJobApplication.mockRejectedValueOnce(
        new Error('Network error')
      );

      mockRedisManager.publishTask = vi.fn().mockResolvedValue('retry_task_id');

      const processorAny = processor as any;
      await processorAny.processJobApplicationTask(errorTask);

      // Should retry the task
      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.JOB_APPLICATION,
        expect.objectContaining({
          job_id: 123,
          application_id: 456
        })
      );
    });

    it('should handle max retries exceeded', async () => {
      const maxRetriesTask = { ...sampleTask, retries: 1 }; // MAX_RETRIES is set to 1 in test env

      mockStagehandWrapper.processJobApplication.mockRejectedValueOnce(
        new Error('Persistent error')
      );

      mockRedisManager.publishTask = vi.fn().mockResolvedValue('final_status_task_id');
      mockRedisManager.publishResult = vi.fn().mockResolvedValue(undefined);

      const processorAny = processor as any;
      await processorAny.processJobApplicationTask(maxRetriesTask);

      // Should publish failure status instead of retrying
      expect(mockRedisManager.publishTask).toHaveBeenCalledWith(
        TaskType.UPDATE_JOB_STATUS,
        expect.objectContaining({
          status: 'failed',
          error_message: expect.stringContaining('Failed after 1 retries')
        })
      );
    });
  });
}); 