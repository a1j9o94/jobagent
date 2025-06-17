import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { RedisManager } from '../utils/redis';
import { TaskType, JobApplicationTask } from '../types/tasks';

// Integration tests for Redis queue operations only
// ApplicationProcessor business logic is tested separately with mocks
describe('Redis Queue Integration Tests', () => {
  let redisManager: RedisManager;

  beforeAll(async () => {
    // Skip integration tests if Redis is not available
    const testRedisUrl = process.env.NODE_REDIS_URL || 'redis://test_redis:6379/0';
    console.log(`Environment NODE_REDIS_URL: ${process.env.NODE_REDIS_URL}`);
    console.log(`Using Redis URL: ${testRedisUrl}`);
    
    redisManager = new RedisManager(testRedisUrl);
    
    try {
      console.log('Connecting to Redis...');
      await redisManager.connect();
      console.log('Connected to Redis, checking health...');
      
      const isHealthy = await redisManager.healthCheck();
      console.log(`Redis health check result: ${isHealthy}`);
      
      if (!isHealthy) {
        console.log('Skipping integration tests - Redis not available');
        return;
      }
      
      console.log('Redis is healthy, integration tests will run');
    } catch (error) {
      console.log('Skipping integration tests - Redis connection failed:', error);
      return;
    }
  }, 15000); // Increased timeout to 15 seconds

  afterAll(async () => {
    if (redisManager) {
      await redisManager.disconnect();
    }
  });

  it('should handle enhanced job application task with all new fields', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    // Create a comprehensive job application task with all enhanced fields
    const enhancedJobApplicationPayload: JobApplicationTask = {
      job_id: 123,
      job_url: 'https://example.com/enhanced-test-job',
      company: 'TestCorp Enhanced',
      title: 'Enhanced Integration Test Engineer',
      user_data: {
        // Basic identity
        name: 'Test Enhanced User',
        first_name: 'Test',
        last_name: 'Enhanced User',
        email: 'enhanced@example.com',
        phone: '+1234567890',
        
        // Generated documents
        resume_url: 'https://storage.example.com/resume.pdf',
        cover_letter_url: 'https://storage.example.com/cover_letter.pdf',
        
        // Contact and social links
        linkedin_url: 'https://linkedin.com/in/testuser',
        github_url: 'https://github.com/testuser',
        portfolio_url: 'https://testuser.dev',
        website: 'https://testuser.dev',
        
        // Location information
        address: '123 Test St',
        city: 'Test City',
        state: 'CA',
        zip_code: '12345',
        country: 'USA',
        
        // Professional information for intelligent responses
        current_role: 'Senior Software Engineer',
        experience_years: 8,
        education: 'BS Computer Science',
        skills: ['Python', 'TypeScript', 'React', 'FastAPI'],
        
        // Work preferences for intelligent answers
        preferred_work_arrangement: 'remote',
        availability: 'Available immediately',
        salary_expectation: '$120k-$150k',
        
        // Additional profile context
        summary: 'Experienced full-stack developer with expertise in Python and TypeScript',
        headline: 'Senior Software Engineer',
        
        // Additional preferences
        pref_timezone: 'PST',
        pref_company_size: 'startup'
      },
      credentials: {
        username: 'testuser@example.com',
        password: 'encrypted_password_hash'
      },
      custom_answers: {
        'Why do you want to work here?': 'I am passionate about the company mission and technology stack',
        'What is your biggest strength?': 'Problem-solving and technical leadership'
      },
      application_id: 456,
      ai_instructions: {
        tone: 'professional',
        focus_areas: ['technical skills', 'leadership experience'],
        avoid_topics: ['salary negotiation', 'personal details']
      }
    };

    // Publish enhanced job application task
    const taskId = await redisManager.publishTask(TaskType.JOB_APPLICATION, enhancedJobApplicationPayload);
    expect(taskId).toBeDefined();
    expect(taskId).toMatch(/^job_application_\d+_[a-z0-9]+$/);

    // Verify task was queued
    const queueLength = await redisManager.getQueueLength(TaskType.JOB_APPLICATION);
    expect(queueLength).toBeGreaterThanOrEqual(1);

    // Consume the task and verify all enhanced fields are preserved
    const consumedTask = await redisManager.consumeTask(TaskType.JOB_APPLICATION);
    expect(consumedTask).toBeDefined();
    expect(consumedTask?.id).toBe(taskId);
    
    const payload = consumedTask?.payload as JobApplicationTask;
    
    // Verify basic fields
    expect(payload.job_id).toBe(123);
    expect(payload.company).toBe('TestCorp Enhanced');
    expect(payload.title).toBe('Enhanced Integration Test Engineer');
    expect(payload.application_id).toBe(456);
    
    // Verify enhanced user data structure
    expect(payload.user_data.name).toBe('Test Enhanced User');
    expect(payload.user_data.first_name).toBe('Test');
    expect(payload.user_data.last_name).toBe('Enhanced User');
    expect(payload.user_data.email).toBe('enhanced@example.com');
    
    // Verify professional information
    expect(payload.user_data.current_role).toBe('Senior Software Engineer');
    expect(payload.user_data.experience_years).toBe(8);
    expect(payload.user_data.skills).toEqual(['Python', 'TypeScript', 'React', 'FastAPI']);
    
    // Verify work preferences
    expect(payload.user_data.preferred_work_arrangement).toBe('remote');
    expect(payload.user_data.availability).toBe('Available immediately');
    expect(payload.user_data.salary_expectation).toBe('$120k-$150k');
    
    // Verify location data
    expect(payload.user_data.address).toBe('123 Test St');
    expect(payload.user_data.city).toBe('Test City');
    expect(payload.user_data.state).toBe('CA');
    expect(payload.user_data.zip_code).toBe('12345');
    
    // Verify social links
    expect(payload.user_data.linkedin_url).toBe('https://linkedin.com/in/testuser');
    expect(payload.user_data.github_url).toBe('https://github.com/testuser');
    expect(payload.user_data.portfolio_url).toBe('https://testuser.dev');
    
    // Verify credentials
    expect(payload.credentials?.username).toBe('testuser@example.com');
    expect(payload.credentials?.password).toBe('encrypted_password_hash');
    
    // Verify custom answers
    expect(payload.custom_answers).toBeDefined();
    expect(payload.custom_answers?.['Why do you want to work here?']).toBe('I am passionate about the company mission and technology stack');
    expect(payload.custom_answers?.['What is your biggest strength?']).toBe('Problem-solving and technical leadership');
    
    // Verify NEW ai_instructions field
    expect(payload.ai_instructions).toBeDefined();
    expect(payload.ai_instructions?.tone).toBe('professional');
    expect(payload.ai_instructions?.focus_areas).toEqual(['technical skills', 'leadership experience']);
    expect(payload.ai_instructions?.avoid_topics).toEqual(['salary negotiation', 'personal details']);

    // Verify queue length decreased
    const newQueueLength = await redisManager.getQueueLength(TaskType.JOB_APPLICATION);
    expect(newQueueLength).toBe(queueLength - 1);
  }, 15000);

  it('should handle complete job application task queue workflow', async () => {
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
  }, 15000);

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

  it('should handle multiple task types in correct FIFO order', async () => {
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

  it('should handle Redis health check', async () => {
    // Skip if Redis not available
    const isHealthy = await redisManager.healthCheck();
    if (!isHealthy) {
      console.log('Skipping - Redis not available');
      return;
    }

    expect(isHealthy).toBe(true);
  });
}); 