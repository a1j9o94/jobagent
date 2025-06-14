import { describe, it, expect } from 'vitest';
import { IntelligentQuestionHandler } from './intelligent-question-handler';
import { EnhancedUserData } from './types/stagehand';

describe('IntelligentQuestionHandler', () => {
  const userData: EnhancedUserData = {
    name: 'John Doe',
    email: 'john@example.com',
    phone: '+1234567890',
    years_experience: 5,
    preferences: {
      preferred_salary: '$120k'
    }
  };

  const handler = new IntelligentQuestionHandler(userData);

  it('should handle experience questions with user data', async () => {
    const result = await handler.analyzeAndRespondToQuestion('How many years of experience do you have?');
    expect(result.success).toBe(true);
    expect(result.response).toContain('5');
    expect(result.confidence).toBe('high');
  });

  it('should handle salary questions strategically', async () => {
    const result = await handler.analyzeAndRespondToQuestion('What are your salary expectations?');
    expect(result.success).toBe(true);
    expect(result.response).toContain('$120k');
    expect(result.confidence).toBe('medium');
  });

  it('should escalate complex behavioral questions', async () => {
    const result = await handler.analyzeAndRespondToQuestion('Describe a time you faced conflict at work');
    expect(result.needsApproval).toBe(true);
    expect(result.reasoning).toContain('Behavioral');
  });
});
