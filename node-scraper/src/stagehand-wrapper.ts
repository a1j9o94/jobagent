import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';
import { logger } from './utils/logger';
import { 
    ApplicationResult, 
    StagehandConfig,
    PageState,
    AutomationStep 
} from './types/stagehand';
import { JobApplicationTask } from './types/tasks';

// Zod schemas for structured extraction
const FormFieldSchema = z.object({
    name: z.string(),
    type: z.string(),
    required: z.boolean().optional(),
    placeholder: z.string().optional(),
    value: z.string().optional()
});

const ApplicationFormSchema = z.object({
    fields: z.array(FormFieldSchema),
    submitButton: z.string().optional(),
    requiresLogin: z.boolean(),
    hasFileUpload: z.boolean(),
    estimatedSteps: z.number()
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
            this.stagehand = new Stagehand({
                env: 'LOCAL', // or 'BROWSERBASE' for cloud
                headless: this.config.headless,
                domSettleTimeoutMs: 2000
            });

            await this.stagehand.init();
            logger.info('Stagehand initialized successfully');
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

    async processJobApplication(task: JobApplicationTask): Promise<ApplicationResult> {
        if (!this.stagehand) {
            throw new Error('Stagehand not initialized');
        }

        const steps: AutomationStep[] = [];
        let currentUrl = task.job_url;

        try {
            logger.info(`Starting job application for ${task.title} at ${task.company}`);

            // Navigate to the job URL
            const page = this.stagehand.page;
            await page.goto(task.job_url);
            
            // Wait for page to load and analyze the form
            await page.waitForLoadState('domcontentloaded');
            
            // Extract initial page state
            const initialState = await this.extractPageState();
            logger.info(`Initial page state: ${initialState.title}`);

            // Look for "Apply" or "Easy Apply" buttons
            const applyButtonFound = await this.findAndClickApplyButton();
            if (!applyButtonFound) {
                return {
                    success: false,
                    error: 'No apply button found on the page',
                    screenshot_url: await this.takeScreenshot('no_apply_button')
                };
            }

            // Handle potential login requirement
            if (task.credentials && await this.detectLoginRequired()) {
                const loginSuccess = await this.handleLogin(task.credentials);
                if (!loginSuccess) {
                    return {
                        success: false,
                        error: 'Login failed',
                        screenshot_url: await this.takeScreenshot('login_failed')
                    };
                }
            }

            // Analyze the application form
            const formAnalysis = await this.analyzeApplicationForm();
            logger.info(`Form analysis: ${formAnalysis.estimatedSteps} steps, requires login: ${formAnalysis.requiresLogin}`);

            // Fill out the application form step by step
            const fillResult = await this.fillApplicationForm(task.user_data, formAnalysis);
            
            if (fillResult.needsApproval) {
                return {
                    success: false,
                    needsApproval: true,
                    question: fillResult.question,
                    state: await this.serializePageState(),
                    screenshot_url: await this.takeScreenshot('needs_approval')
                };
            }

            // Submit the application
            const submitSuccess = await this.submitApplication();
            
            if (submitSuccess) {
                const confirmationMessage = await this.extractConfirmationMessage();
                
                return {
                    success: true,
                    submitted_at: new Date().toISOString(),
                    confirmation_message: confirmationMessage,
                    screenshot_url: await this.takeScreenshot('success'),
                    page_title: await page.title()
                };
            } else {
                return {
                    success: false,
                    error: 'Failed to submit application',
                    screenshot_url: await this.takeScreenshot('submit_failed')
                };
            }

        } catch (error) {
            logger.error(`Job application failed for ${task.job_id}:`, error);
            
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error occurred',
                screenshot_url: await this.takeScreenshot('error')
            };
        }
    }

    private async findAndClickApplyButton(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Try multiple common apply button patterns
            const applySelectors = [
                'Apply now',
                'Easy Apply',
                'Apply for this job',
                'Submit application',
                'Apply',
                'Quick apply'
            ];

            for (const selector of applySelectors) {
                try {
                    await this.stagehand.page.act(`click "${selector}"`);
                    logger.info(`Successfully clicked apply button: ${selector}`);
                    return true;
                } catch (error) {
                    // Continue to next selector
                    continue;
                }
            }

            return false;
        } catch (error) {
            logger.error('Error finding apply button:', error);
            return false;
        }
    }

    private async detectLoginRequired(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            const loginIndicators = await this.stagehand.page.extract({
                instruction: "Check if this page requires login by looking for email/username and password fields",
                schema: z.object({
                    hasLoginForm: z.boolean(),
                    hasEmailField: z.boolean(),
                    hasPasswordField: z.boolean()
                })
            });

            return loginIndicators.hasLoginForm || (loginIndicators.hasEmailField && loginIndicators.hasPasswordField);
        } catch (error) {
            logger.error('Error detecting login requirement:', error);
            return false;
        }
    }

    private async handleLogin(credentials: { username: string; password: string }): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Fill in email/username
            await this.stagehand.page.act(`fill in the email or username field with "${credentials.username}"`);
            
            // Fill in password
            await this.stagehand.page.act(`fill in the password field with "${credentials.password}"`);
            
            // Click login/sign in button
            await this.stagehand.page.act('click the login or sign in button');
            
            // Wait for navigation and check if login was successful
            await this.stagehand.page.waitForLoadState('domcontentloaded');
            
            // Check if we're still on a login page (indicating failure)
            const stillOnLogin = await this.detectLoginRequired();
            return !stillOnLogin;

        } catch (error) {
            logger.error('Error during login:', error);
            return false;
        }
    }

    private async analyzeApplicationForm() {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            const analysis = await this.stagehand.page.extract({
                instruction: "Analyze this job application form and extract key information about the fields and requirements",
                schema: ApplicationFormSchema
            });

            return analysis;
        } catch (error) {
            logger.error('Error analyzing application form:', error);
            // Return default analysis
            return {
                fields: [],
                requiresLogin: false,
                hasFileUpload: false,
                estimatedSteps: 1
            };
        }
    }

    private async fillApplicationForm(userData: any, formAnalysis: any): Promise<{ success: boolean; needsApproval?: boolean; question?: string }> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            // Fill basic fields
            const basicFields = [
                { field: 'first name', value: userData.first_name || userData.name?.split(' ')[0] },
                { field: 'last name', value: userData.last_name || userData.name?.split(' ').slice(1).join(' ') },
                { field: 'email', value: userData.email },
                { field: 'phone', value: userData.phone },
            ];

            for (const field of basicFields) {
                if (field.value) {
                    try {
                        await this.stagehand.page.act(`fill in the ${field.field} field with "${field.value}"`);
                    } catch (error) {
                        logger.warn(`Could not fill ${field.field}:`, error);
                    }
                }
            }

            // Handle file uploads (resume, cover letter)
            if (formAnalysis.hasFileUpload && userData.resume_url) {
                // This would require downloading the resume file first
                // For now, we'll mark it as needing approval
                return {
                    success: false,
                    needsApproval: true,
                    question: `Please upload your resume. Resume URL: ${userData.resume_url}`
                };
            }

            // Look for any custom questions that might need human input
            const customQuestions = await this.detectCustomQuestions();
            if (customQuestions.length > 0) {
                return {
                    success: false,
                    needsApproval: true,
                    question: `Please answer the following questions: ${customQuestions.join(', ')}`
                };
            }

            return { success: true };

        } catch (error) {
            logger.error('Error filling application form:', error);
            return { 
                success: false, 
                needsApproval: true, 
                question: `Manual intervention needed. Error: ${error instanceof Error ? error.message : 'Unknown error'}` 
            };
        }
    }

    private async detectCustomQuestions(): Promise<string[]> {
        if (!this.stagehand) return [];

        try {
            const questions = await this.stagehand.page.extract({
                instruction: "Find any custom questions or text areas that require personalized answers",
                schema: z.object({
                    questions: z.array(z.string())
                })
            });

            return questions.questions || [];
        } catch (error) {
            logger.error('Error detecting custom questions:', error);
            return [];
        }
    }

    private async submitApplication(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Try to find and click submit button
            const submitActions = [
                'click "Submit application"',
                'click "Submit"', 
                'click "Send application"',
                'click "Apply now"',
                'click the submit button'
            ];

            for (const action of submitActions) {
                try {
                    await this.stagehand.page.act(action);
                    
                    // Wait for response
                    await this.stagehand.page.waitForLoadState('domcontentloaded');
                    
                    // Check if submission was successful
                    const isSuccess = await this.detectSubmissionSuccess();
                    if (isSuccess) {
                        return true;
                    }
                } catch (error) {
                    continue;
                }
            }

            return false;
        } catch (error) {
            logger.error('Error submitting application:', error);
            return false;
        }
    }

    private async detectSubmissionSuccess(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            const success = await this.stagehand.page.extract({
                instruction: "Check if the application was successfully submitted by looking for confirmation messages",
                schema: z.object({
                    submitted: z.boolean(),
                    confirmationMessage: z.string().optional()
                })
            });

            return success.submitted;
        } catch (error) {
            logger.error('Error detecting submission success:', error);
            return false;
        }
    }

    private async extractConfirmationMessage(): Promise<string | undefined> {
        if (!this.stagehand) return undefined;

        try {
            const confirmation = await this.stagehand.page.extract({
                instruction: "Extract any confirmation message or success text from the page",
                schema: z.object({
                    message: z.string().optional()
                })
            });

            return confirmation.message;
        } catch (error) {
            logger.error('Error extracting confirmation message:', error);
            return undefined;
        }
    }

    private async extractPageState(): Promise<PageState> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        const page = this.stagehand.page;
        const url = page.url();
        const title = await page.title();

        try {
            const formFields = await page.extract({
                instruction: "Extract all form fields from this page",
                schema: z.object({
                    fields: z.array(FormFieldSchema)
                })
            });

            return {
                url,
                title,
                forms: formFields.fields || [],
                timestamp: new Date().toISOString()
            };
        } catch (error) {
            logger.error('Error extracting page state:', error);
            return {
                url,
                title,
                forms: [],
                timestamp: new Date().toISOString()
            };
        }
    }

    private async serializePageState(): Promise<string> {
        const state = await this.extractPageState();
        return JSON.stringify(state);
    }

    private async takeScreenshot(context: string): Promise<string | undefined> {
        if (!this.stagehand) return undefined;

        try {
            const timestamp = Date.now();
            const filename = `screenshot_${context}_${timestamp}.png`;
            
            // Take screenshot
            await this.stagehand.page.screenshot({ 
                path: `/tmp/${filename}`,
                fullPage: true 
            });

            // In a real implementation, you'd upload this to S3/MinIO
            // For now, return a placeholder URL
            const screenshotUrl = `${process.env.SCREENSHOT_BASE_URL}/${filename}`;
            
            logger.info(`Screenshot taken: ${screenshotUrl}`);
            return screenshotUrl;
        } catch (error) {
            logger.error('Error taking screenshot:', error);
            return undefined;
        }
    }
} 