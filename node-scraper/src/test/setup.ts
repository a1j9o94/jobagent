import { beforeAll, afterAll } from 'vitest';

// Mock environment variables for tests
process.env.NODE_ENV = 'test';
process.env.LOG_LEVEL = 'error';
process.env.NODE_REDIS_URL = 'redis://localhost:6380'; // Test Redis port
process.env.STAGEHAND_HEADLESS = 'true';
process.env.STAGEHAND_TIMEOUT = '5000';
process.env.MAX_RETRIES = '1';

// Global test setup
beforeAll(async () => {
  // Any global setup can go here
});

afterAll(async () => {
  // Global cleanup
});

// Mock Stagehand for tests since it requires browser setup
vi.mock('@browserbasehq/stagehand', () => ({
  Stagehand: vi.fn().mockImplementation(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    page: {
      goto: vi.fn().mockResolvedValue(undefined),
      waitForLoadState: vi.fn().mockResolvedValue(undefined),
      act: vi.fn().mockResolvedValue(undefined),
      extract: vi.fn().mockResolvedValue({}),
      title: vi.fn().mockResolvedValue('Test Page'),
      url: vi.fn().mockReturnValue('https://example.com'),
      screenshot: vi.fn().mockResolvedValue(undefined)
    }
  }))
}));

// Mock Winston logger for cleaner test output
vi.mock('../utils/logger', () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn()
  }
})); 