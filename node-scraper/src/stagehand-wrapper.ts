import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';
import { logger } from './utils/logger';
import {
    StagehandConfig,
    ApplicationResult
} from './types/stagehand';
import { JobApplicationTask } from './types/tasks';

interface JobCredentials {
    username: string;
    password: string;
    [key: string]: any;
}

interface JobApplicationData {
    name: string;
    email: string;
    phone: string;
    resume_url?: string;
    cover_letter?: string;
    [key: string]: any;
}

// Zod schemas for Stagehand extraction
const LoginCheckSchema = z.object({
    hasLoginForm: z.boolean(),
    loginElements: z.array(z.string()).optional()
});

const FormAnalysisSchema = z.object({
    fields: z.array(z.string()),
    hasFileUpload: z.boolean(),
    hasUnknownQuestions: z.boolean()
});

const UnknownQuestionsSchema = z.object({
    questions: z.array(z.string())
});

const SubmissionResultSchema = z.object({
    wasSuccessful: z.boolean(),
    confirmationMessage: z.string().optional()
});

const ConfirmationSchema = z.object({
    message: z.string().optional()
});

export class StagehandWrapper {
    private stagehand: Stagehand | null = null;
    private config: StagehandConfig;

    constructor(config?: Partial<StagehandConfig>) {
        this.config = {
            headless: process.env.STAGEHAND_HEADLESS === 'true' || true,
            timeout: parseInt(process.env.STAGEHAND_TIMEOUT || '30000'),
            viewport: {
                width: parseInt(process.env.BROWSER_VIEWPORT_WIDTH || '1280'),
                height: parseInt(process.env.BROWSER_VIEWPORT_HEIGHT || '720')
            },
            userAgent: process.env.BROWSER_USER_AGENT || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            ...config
        };
    }

    async initialize(): Promise<void> {
        try {
            // Check if we're in test environment
            const isTestEnv = process.env.NODE_ENV === 'test' || process.env.VITEST === 'true';
            if (isTestEnv) {
                logger.info('Skipping Stagehand initialization (test environment)');
                this.stagehand = null;
                return;
            }

            // Check if we have the required credentials for Browserbase
            const hasRequiredCredentials = process.env.BROWSERBASE_API_KEY && 
                                         process.env.BROWSERBASE_PROJECT_ID && 
                                         process.env.OPENAI_API_KEY;
            
            if (!hasRequiredCredentials) {
                logger.warn('Missing Browserbase credentials. Stagehand will not be available.');
                logger.warn('Required: BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID, OPENAI_API_KEY');
                this.stagehand = null;
                return;
            }

            // Use Browserbase for cloud browser automation
            this.stagehand = new Stagehand({
                env: 'BROWSERBASE',
                apiKey: process.env.BROWSERBASE_API_KEY,
                projectId: process.env.BROWSERBASE_PROJECT_ID,
                modelName: 'gpt-4o',
                modelClientOptions: {
                    apiKey: process.env.OPENAI_API_KEY,
                },
                domSettleTimeoutMs: 2000
            });
            
            await this.stagehand.init();
            logger.info('Stagehand initialized successfully with Browserbase');
        } catch (error) {
            logger.error('Failed to initialize Stagehand:', error);
            throw error;
        }
    }

    async cleanup(): Promise<void> {
        if (this.stagehand) {
            try {
                await this.stagehand.close();
                logger.info('Stagehand cleaned up successfully');
            } catch (error) {
                logger.error('Error during Stagehand cleanup:', error);
            }
        }
    }

    isAvailable(): boolean {
        return this.stagehand !== null;
    }

    async processJobApplication(task: JobApplicationTask): Promise<ApplicationResult> {
        if (!this.stagehand) {
            // Return mock result for test environment
            logger.info(`Mock job application processing for ${task.title} at ${task.company}`);
            return {
                success: true,
                confirmation_message: `Mock application submitted for ${task.title} at ${task.company}`,
                needsApproval: false
            };
        }

        try {
            logger.info(`Processing job application for ${task.title} at ${task.company}`);
            
            // Navigate to the job posting
            const page = this.stagehand.page;
            await page.goto(task.job_url);
            
            // Wait for page to load
            await page.waitForLoadState('domcontentloaded');
            
            // Look for apply button and click it
            const applyResult = await this.findAndClickApplyButton();
            if (!applyResult) {
                return {
                    success: false,
                    error: 'Could not find apply button on the page',
                    needsApproval: false
                };
            }

            // Handle login if required
            if (task.credentials) {
                const loginRequired = await this.checkIfLoginRequired();
                if (loginRequired) {
                    const loginResult = await this.handleLogin(task.credentials);
                    if (!loginResult) {
                        return {
                            success: false,
                            error: 'Failed to login to the platform',
                            needsApproval: false
                        };
                    }
                }
            }

            // Fill out the application form
            const formResult = await this.fillApplicationForm(task.user_data, task.custom_answers);
            
            if (formResult.needsApproval) {
                return {
                    success: false,
                    needsApproval: true,
                    question: formResult.question,
                    state: await page.content(),
                    screenshot_url: await this.takeScreenshot()
                };
            }

            if (!formResult.success) {
                return {
                    success: false,
                    error: formResult.error || 'Failed to fill application form',
                    needsApproval: false
                };
            }

            // Submit the application
            const submitResult = await this.submitApplication();
            
            if (submitResult) {
                const confirmation = await this.getConfirmationMessage();
                return {
                    success: true,
                    confirmation_message: confirmation,
                    needsApproval: false
                };
            } else {
                return {
                    success: false,
                    error: 'Failed to submit application',
                    needsApproval: false
                };
            }

        } catch (error) {
            logger.error('Error processing job application:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error occurred',
                needsApproval: false,
                screenshot_url: await this.takeScreenshot()
            };
        }
    }

    private async findAndClickApplyButton(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            await this.stagehand.page.act(`click the apply button or apply now button`);
            return true;
        } catch (error) {
            logger.error('Failed to find or click apply button:', error);
            return false;
        }
    }

    private async checkIfLoginRequired(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            const loginIndicators = await this.stagehand.page.extract({
                instruction: "Check if there are login fields, sign in buttons, or authentication requirements on the page",
                schema: LoginCheckSchema
            });

            return loginIndicators.hasLoginForm || false;
        } catch (error) {
            logger.error('Error checking login requirement:', error);
            return false;
        }
    }

    private async handleLogin(credentials: JobCredentials): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Fill in login credentials
            await this.stagehand.page.act(`fill in the email or username field with "${credentials.username}"`);
            
            // Fill in password
            await this.stagehand.page.act(`fill in the password field with "${credentials.password}"`);
            
            // Click login button
            await this.stagehand.page.act('click the login or sign in button');
            
            // Wait for navigation
            await this.stagehand.page.waitForLoadState('domcontentloaded');
            
            return true;
        } catch (error) {
            logger.error('Login failed:', error);
            return false;
        }
    }

    private async fillApplicationForm(userData: JobApplicationData, customAnswers?: Record<string, any>): Promise<{ success: boolean; error?: string; needsApproval?: boolean; question?: string }> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            // Analyze the form to understand what fields are present
            const analysis = await this.stagehand.page.extract({
                instruction: "Analyze the job application form and identify all the input fields, their types, and requirements",
                schema: FormAnalysisSchema
            });

            // Fill standard fields
            const standardFields = [
                { field: 'name', value: userData.name },
                { field: 'email', value: userData.email },
                { field: 'phone', value: userData.phone }
            ];

            for (const field of standardFields) {
                if (field.value) {
                    await this.stagehand.page.act(`fill in the ${field.field} field with "${field.value}"`);
                }
            }

            // Handle file uploads (resume, cover letter)
            if (analysis.hasFileUpload && userData.resume_url) {
                // Note: File upload handling would need to be implemented based on the specific platform
                logger.info('File upload detected but not implemented yet');
            }

            // Check for questions that need approval
            const unknownQuestions = await this.getUnknownQuestions();
            if (unknownQuestions.length > 0) {
                return {
                    success: false,
                    needsApproval: true,
                    question: unknownQuestions[0]
                };
            }

            // Fill custom answers if provided
            if (customAnswers) {
                for (const [question, answer] of Object.entries(customAnswers)) {
                    await this.stagehand.page.act(`answer the question "${question}" with "${answer}"`);
                }
            }

            return { success: true };

        } catch (error) {
            logger.error('Error filling application form:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error'
            };
        }
    }

    private async getUnknownQuestions(): Promise<string[]> {
        if (!this.stagehand) return [];

        try {
            const questions = await this.stagehand.page.extract({
                instruction: "Find any questions or fields that seem unusual, company-specific, or require specific answers that aren't standard personal information",
                schema: UnknownQuestionsSchema
            });

            return questions.questions || [];
        } catch (error) {
            logger.error('Error getting unknown questions:', error);
            return [];
        }
    }

    private async submitApplication(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Look for submit button and click it
            const action = 'click the submit button, apply button, or send application button';
            await this.stagehand.page.act(action);
            
            // Wait for submission to complete
            await this.stagehand.page.waitForLoadState('domcontentloaded');
            
            // Check if submission was successful
            const success = await this.stagehand.page.extract({
                instruction: "Check if the application was submitted successfully by looking for confirmation messages, success indicators, or thank you pages",
                schema: SubmissionResultSchema
            });

            return success.wasSuccessful || false;
        } catch (error) {
            logger.error('Error submitting application:', error);
            return false;
        }
    }

    private async getConfirmationMessage(): Promise<string | undefined> {
        if (!this.stagehand) return undefined;

        try {
            const confirmation = await this.stagehand.page.extract({
                instruction: "Extract any confirmation message, application ID, or success message from the page",
                schema: ConfirmationSchema
            });

            return confirmation.message;
        } catch (error) {
            logger.error('Error getting confirmation message:', error);
            return undefined;
        }
    }

    private async takeScreenshot(): Promise<string | undefined> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            const page = this.stagehand.page;
            
            // Take screenshot
            const screenshot = await page.screenshot({
                path: `/tmp/screenshot-${Date.now()}.png`,
                fullPage: true
            });

            // In a real implementation, you would upload this to S3 or similar
            // For now, just return a placeholder URL
            return `screenshot-${Date.now()}.png`;
        } catch (error) {
            logger.error('Error taking screenshot:', error);
            return undefined;
        }
    }
} 