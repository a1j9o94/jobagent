import { EnhancedUserData, QuestionResponse } from './types/stagehand';

export class IntelligentQuestionHandler {
    private userData: EnhancedUserData;

    constructor(userData: EnhancedUserData) {
        this.userData = userData;
    }

    async analyzeAndRespondToQuestion(questionText: string): Promise<QuestionResponse> {
        const text = questionText.toLowerCase();

        if (text.includes('years of experience') || text.includes('how many years')) {
            const years = this.userData.years_experience ?? 0;
            return {
                success: true,
                response: `${years} years of experience`,
                confidence: 'high'
            };
        }

        if (text.includes('salary')) {
            const salary = this.userData.preferences?.preferred_salary;
            const response = salary ? `I am targeting around ${salary}` : 'I am open to discussing competitive compensation.';
            return {
                success: true,
                response,
                confidence: 'medium'
            };
        }

        if (text.includes('describe') || text.includes('leadership')) {
            return {
                success: false,
                confidence: 'low',
                needsApproval: true,
                reasoning: 'Behavioral question requires human input'
            };
        }

        return {
            success: false,
            confidence: 'low',
            needsApproval: true,
            reasoning: 'Unknown question'
        };
    }
}
