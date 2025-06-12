import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { StagehandWrapper } from './stagehand-wrapper';
import { JobApplicationTask } from './types/tasks';

// StagehandWrapper tests - tests actual browser automation
// These tests require Browserbase credentials to run properly
describe('StagehandWrapper', () => {
  let wrapper: StagehandWrapper;

  beforeEach(() => {
    wrapper = new StagehandWrapper();
  });

  afterEach(async () => {
    if (wrapper) {
      await wrapper.cleanup();
    }
  });

  describe('initialization', () => {
    it('should initialize successfully with Browserbase credentials', async () => {
      // Skip if no Browserbase credentials
      const hasCredentials = process.env.BROWSERBASE_API_KEY && 
                           process.env.BROWSERBASE_PROJECT_ID && 
                           process.env.OPENAI_API_KEY;
      
      if (!hasCredentials) {
        console.log('Skipping Stagehand test - missing Browserbase credentials');
        return;
      }

      await expect(wrapper.initialize()).resolves.not.toThrow();
      expect(wrapper.isAvailable()).toBe(true);
    });

    it('should handle missing credentials gracefully', async () => {
      // Temporarily clear credentials
      const originalApiKey = process.env.BROWSERBASE_API_KEY;
      const originalProjectId = process.env.BROWSERBASE_PROJECT_ID;
      const originalOpenAIKey = process.env.OPENAI_API_KEY;

      delete process.env.BROWSERBASE_API_KEY;
      delete process.env.BROWSERBASE_PROJECT_ID;
      delete process.env.OPENAI_API_KEY;

      await wrapper.initialize();
      expect(wrapper.isAvailable()).toBe(false);

      // Restore credentials
      if (originalApiKey) process.env.BROWSERBASE_API_KEY = originalApiKey;
      if (originalProjectId) process.env.BROWSERBASE_PROJECT_ID = originalProjectId;
      if (originalOpenAIKey) process.env.OPENAI_API_KEY = originalOpenAIKey;
    });

    it('should skip initialization in test environment', async () => {
      // Set test environment
      const originalNodeEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'test';

      await wrapper.initialize();
      expect(wrapper.isAvailable()).toBe(false);

      // Restore environment
      if (originalNodeEnv) {
        process.env.NODE_ENV = originalNodeEnv;
      } else {
        delete process.env.NODE_ENV;
      }
    });
  });

  describe('mock mode processing', () => {
    it('should return mock results when Stagehand is not available', async () => {
      // Initialize without credentials (mock mode)
      const originalApiKey = process.env.BROWSERBASE_API_KEY;
      delete process.env.BROWSERBASE_API_KEY;

      await wrapper.initialize();
      expect(wrapper.isAvailable()).toBe(false);

      const mockTask: JobApplicationTask = {
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
      };

      const result = await wrapper.processJobApplication(mockTask);

      expect(result.success).toBe(true);
      expect(result.confirmation_message).toContain('Mock application submitted');
      expect(result.needsApproval).toBe(false);

      // Restore credential
      if (originalApiKey) process.env.BROWSERBASE_API_KEY = originalApiKey;
    });
  });

  describe('real browser automation', () => {
    beforeAll(() => {
      // Skip these tests if no Browserbase credentials
      const hasCredentials = process.env.BROWSERBASE_API_KEY && 
                           process.env.BROWSERBASE_PROJECT_ID && 
                           process.env.OPENAI_API_KEY;
      
      if (!hasCredentials) {
        console.log('Skipping real browser automation tests - missing Browserbase credentials');
      }
    });

    it('should handle basic page navigation', async () => {
      // Skip if no credentials
      const hasCredentials = process.env.BROWSERBASE_API_KEY && 
                           process.env.BROWSERBASE_PROJECT_ID && 
                           process.env.OPENAI_API_KEY;
      
      if (!hasCredentials) {
        console.log('Skipping - missing Browserbase credentials');
        return;
      }

      await wrapper.initialize();
      
      if (!wrapper.isAvailable()) {
        console.log('Skipping - Stagehand not available');
        return;
      }

      const testTask: JobApplicationTask = {
        job_id: 999,
        job_url: 'https://httpbin.org/html', // Simple test page
        company: 'Test Company',
        title: 'Test Position',
        user_data: {
          name: 'Test User',
          email: 'test@example.com',
          phone: '+1234567890'
        },
        application_id: 999
      };

      // This should attempt to process but likely fail gracefully since it's not a real job page
      const result = await wrapper.processJobApplication(testTask);
      
      // Should return a result (success or failure)
      expect(result).toBeDefined();
      expect(typeof result.success).toBe('boolean');
      expect(typeof result.needsApproval).toBe('boolean');
    }, 30000); // Extended timeout for browser operations

    it('should handle errors gracefully', async () => {
      // Skip if no credentials
      const hasCredentials = process.env.BROWSERBASE_API_KEY && 
                           process.env.BROWSERBASE_PROJECT_ID && 
                           process.env.OPENAI_API_KEY;
      
      if (!hasCredentials) {
        console.log('Skipping - missing Browserbase credentials');
        return;
      }

      await wrapper.initialize();
      
      if (!wrapper.isAvailable()) {
        console.log('Skipping - Stagehand not available');
        return;
      }

      const invalidTask: JobApplicationTask = {
        job_id: 998,
        job_url: 'https://invalid-url-that-does-not-exist.com',
        company: 'Invalid Company',
        title: 'Invalid Position',
        user_data: {
          name: 'Test User',
          email: 'test@example.com',
          phone: '+1234567890'
        },
        application_id: 998
      };

      const result = await wrapper.processJobApplication(invalidTask);
      
      // Should handle the error gracefully
      expect(result).toBeDefined();
      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(typeof result.error).toBe('string');
    }, 30000);
  });

  describe('cleanup', () => {
    it('should cleanup successfully', async () => {
      await wrapper.initialize();
      await expect(wrapper.cleanup()).resolves.not.toThrow();
    });

    it('should handle cleanup when not initialized', async () => {
      // Don't initialize, just cleanup
      await expect(wrapper.cleanup()).resolves.not.toThrow();
    });
  });
}); 