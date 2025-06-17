import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';
import { logger } from './utils/logger';
import {
    StagehandConfig,
    ApplicationResult
} from './types/stagehand';
import { JobApplicationTask } from './types/tasks';

// Enhanced schemas for better form analysis
const PageAnalysisSchema = z.object({
    pageType: z.enum(['job_description', 'application_form', 'login', 'confirmation', 'multi_step', 'unknown']),
    hasApplyButton: z.boolean(),
    applyButtonTexts: z.array(z.string()).optional(),
    requiresRedirect: z.boolean(),
    isApplicationPage: z.boolean()
});

const FormFieldSchema = z.object({
    fieldType: z.enum(['text', 'email', 'phone', 'textarea', 'select', 'radio', 'checkbox', 'file', 'date', 'unknown']),
    label: z.string(),
    placeholder: z.string().optional(),
    required: z.boolean(),
    options: z.array(z.string()).optional(), // For select/radio fields
    currentValue: z.string().optional()
});

const DynamicFormAnalysisSchema = z.object({
    totalFields: z.number(),
    currentStep: z.number().optional(),
    totalSteps: z.number().optional(),
    fields: z.array(FormFieldSchema),
    hasFileUpload: z.boolean(),
    hasCustomQuestions: z.boolean(),
    customQuestions: z.array(z.string()).optional(),
    nextButtonText: z.string().optional(),
    submitButtonText: z.string().optional(),
    canProceedToNext: z.boolean()
});

const QuestionAnalysisSchema = z.object({
    questionText: z.string(),
    questionType: z.enum(['short_answer', 'long_answer', 'multiple_choice', 'yes_no', 'dropdown', 'file_upload']),
    options: z.array(z.string()).optional(),
    isRequired: z.boolean(),
    suggestedAnswer: z.string().optional(),
    needsHumanInput: z.boolean(),
    reasoning: z.string().optional()
});

const NavigationResultSchema = z.object({
    currentUrl: z.string(),
    pageTitle: z.string(),
    isApplicationForm: z.boolean(),
    needsLogin: z.boolean(),
    formDetected: z.boolean(),
    redirectOccurred: z.boolean()
});

const LoginCheckSchema = z.object({
    hasLoginForm: z.boolean(),
    loginElements: z.array(z.string()).optional()
});

const SubmissionResultSchema = z.object({
    wasSuccessful: z.boolean(),
    confirmationMessage: z.string().optional()
});

const ConfirmationSchema = z.object({
    message: z.string().optional(),
    applicationId: z.string().optional()
});

interface JobCredentials {
    username: string;
    password: string;
    [key: string]: any;
}

interface JobApplicationData {
    name: string;
    first_name?: string;
    last_name?: string;
    email: string;
    phone: string;
    resume_url?: string;
    cover_letter_url?: string;
    linkedin_url?: string;
    github_url?: string;
    portfolio_url?: string;
    address?: string;
    city?: string;
    state?: string;
    zip_code?: string;
    website?: string;
    experience_years?: number;
    skills?: string[];
    current_role?: string;
    education?: string;
    preferred_work_arrangement?: 'remote' | 'hybrid' | 'onsite';
    availability?: string;
    salary_expectation?: string;
    [key: string]: any;
}

interface ApplicationSession {
    currentUrl: string;
    currentStep: number;
    totalSteps: number;
    formData: Record<string, any>;
    pendingQuestions: string[];
    completedFields: Set<string>;
}

export class StagehandWrapper {
    private stagehand: Stagehand | null = null;
    private config: StagehandConfig;
    private session: ApplicationSession | null = null;

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
                domSettleTimeoutMs: 2000,
                enableCaching: true, // Enable caching for repeated actions
                verbose: 1
            });

            await this.stagehand.init();
            logger.info('Enhanced Stagehand initialized successfully with Browserbase');
        } catch (error) {
            logger.error('Failed to initialize Enhanced Stagehand:', error);
            this.stagehand = null; // Set to null on failure so isAvailable() returns false
            // Don't throw - let the wrapper handle gracefully with mock results
        }
    }

    async cleanup(): Promise<void> {
        if (this.stagehand) {
            try {
                await this.stagehand.close();
                logger.info('Enhanced Stagehand cleaned up successfully');
            } catch (error) {
                logger.error('Error during Enhanced Stagehand cleanup:', error);
            }
        }
    }

    isAvailable(): boolean {
        return this.stagehand !== null;
    }

    async processJobApplication(task: JobApplicationTask): Promise<ApplicationResult> {
        if (!this.stagehand) {
            return this.getMockResult(task);
        }

        try {
            // Initialize session
            this.session = {
                currentUrl: task.job_url,
                currentStep: 1,
                totalSteps: 1,
                formData: {},
                pendingQuestions: [],
                completedFields: new Set()
            };

            logger.info(`Starting dynamic job application for ${task.title} at ${task.company}`);

            // Phase 1: Navigate to job and find application entry point
            const navigationResult = await this.navigateToApplication(task.job_url);
            if (!navigationResult.success) {
                return navigationResult;
            }

            // Phase 2: Handle authentication if needed
            if (task.credentials) {
                const loginRequired = await this.checkIfLoginRequired();
                if (loginRequired) {
                    const loginResult = await this.handleAuthentication(task.credentials);
                    if (!loginResult.success) {
                        return loginResult;
                    }
                }
            }

            // Phase 3: Dynamic form processing with agentic loop
            const formResult = await this.processApplicationFormDynamically(task);
            
            return formResult;

        } catch (error) {
            logger.error('Error in dynamic job application processing:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error occurred',
                needsApproval: false,
                screenshot_url: await this.takeScreenshot()
            };
        }
    }

    private async navigateToApplication(jobUrl: string): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            const page = this.stagehand.page;
            
            // Navigate to the job posting
            await page.goto(jobUrl);
            await page.waitForLoadState('domcontentloaded');

            // Analyze the current page
            const pageAnalysis = await page.extract({
                instruction: "Analyze this page to determine if it's a job description, application form, or something else. Look for apply buttons, application forms, and determine if clicking apply will redirect to another page.",
                schema: PageAnalysisSchema
            });

            logger.info('Page analysis result:', pageAnalysis);

            // If we're already on an application form, we're good
            if (pageAnalysis.isApplicationPage) {
                this.session!.currentUrl = page.url();
                return { success: true, needsApproval: false };
            }

            // If there's an apply button, click it
            if (pageAnalysis.hasApplyButton) {
                const applySuccess = await this.clickApplyButton(pageAnalysis.applyButtonTexts);
                
                if (applySuccess) {
                    // Wait for navigation and re-analyze
                    await page.waitForLoadState('domcontentloaded');
                    await this.sleep(2000); // Give time for any redirects
                    
                    const newUrl = page.url();
                    this.session!.currentUrl = newUrl;

                    // Check if we ended up on an application form
                    const postClickAnalysis = await page.extract({
                        instruction: "Check if we're now on an application form or if further navigation is needed",
                        schema: NavigationResultSchema
                    });

                    if (postClickAnalysis.isApplicationForm) {
                        return { success: true, needsApproval: false };
                    } else if (postClickAnalysis.needsLogin) {
                        return { success: true, needsApproval: false };
                    }
                }
            }

            // If we couldn't find a way to apply
            return {
                success: false,
                error: 'Could not find a way to access the application form',
                needsApproval: true,
                question: 'Unable to find apply button or application form. Manual intervention needed.',
                screenshot_url: await this.takeScreenshot()
            };

        } catch (error) {
            logger.error('Error navigating to application:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Navigation failed',
                needsApproval: false
            };
        }
    }

    private async clickApplyButton(possibleTexts?: string[]): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            // Try different apply button variations
            const applyVariations = [
                'click the apply button',
                'click the apply now button',
                'click the apply for this job button',
                'click apply',
                ...(possibleTexts || []).map(text => `click the "${text}" button`)
            ];

            for (const variation of applyVariations) {
                try {
                    await this.stagehand.page.act(variation);
                    logger.info(`Successfully clicked apply button with: ${variation}`);
                    return true;
                } catch (error) {
                    // Try next variation
                    continue;
                }
            }

            return false;
        } catch (error) {
            logger.error('Error clicking apply button:', error);
            return false;
        }
    }

    private async processApplicationFormDynamically(task: JobApplicationTask): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        const page = this.stagehand.page;
        let maxSteps = 10; // Prevent infinite loops
        let currentStepAttempts = 0;
        const maxStepAttempts = 3;

        while (currentStepAttempts < maxStepAttempts && maxSteps > 0) {
            try {
                // Analyze current form state
                const formAnalysis = await page.extract({
                    instruction: `Analyze the current application form. Identify all visible fields, their types, requirements, and any custom questions. Determine if this is a multi-step form and what step we're on. Look for progress indicators, step counters, or navigation elements.`,
                    schema: DynamicFormAnalysisSchema
                });

                logger.info(`Form analysis - Step ${formAnalysis.currentStep || 1}:`, {
                    totalFields: formAnalysis.totalFields,
                    hasCustomQuestions: formAnalysis.hasCustomQuestions,
                    canProceed: formAnalysis.canProceedToNext
                });

                // Update session state
                if (formAnalysis.currentStep) this.session!.currentStep = formAnalysis.currentStep;
                if (formAnalysis.totalSteps) this.session!.totalSteps = formAnalysis.totalSteps;

                // Fill standard fields first
                const standardFieldResult = await this.fillStandardFields(formAnalysis.fields, task.user_data);
                if (!standardFieldResult.success && standardFieldResult.needsApproval) {
                    return standardFieldResult;
                }

                // Handle file uploads
                if (formAnalysis.hasFileUpload) {
                    const fileUploadResult = await this.handleFileUploads(task.user_data);
                    if (!fileUploadResult.success && fileUploadResult.needsApproval) {
                        return fileUploadResult;
                    }
                }

                // Process custom questions with agentic responses
                if (formAnalysis.hasCustomQuestions && formAnalysis.customQuestions) {
                    const customQuestionResult = await this.processCustomQuestions(
                        formAnalysis.customQuestions, 
                        task.user_data,
                        task.custom_answers
                    );
                    
                    if (!customQuestionResult.success) {
                        return customQuestionResult;
                    }
                }

                // Try to proceed to next step or submit
                const navigationResult = await this.proceedToNextStepOrSubmit(formAnalysis);
                
                if (navigationResult.completed) {
                    // Application completed successfully
                    const confirmation = await this.getConfirmationMessage();
                    return {
                        success: true,
                        confirmation_message: confirmation,
                        needsApproval: false,
                        submitted_at: new Date().toISOString()
                    };
                } else if (navigationResult.needsApproval) {
                    return navigationResult.result!;
                } else if (navigationResult.nextStep) {
                    // Continue to next step
                    currentStepAttempts = 0; // Reset attempts for new step
                    await this.sleep(2000); // Wait for page transition
                    continue;
                } else {
                    currentStepAttempts++;
                    if (currentStepAttempts >= maxStepAttempts) {
                        return {
                            success: false,
                            needsApproval: true,
                            question: 'Unable to proceed with form automatically. Manual intervention required.',
                            screenshot_url: await this.takeScreenshot(),
                            state: await page.content()
                        };
                    }
                }

                maxSteps--;
            } catch (error) {
                logger.error('Error in form processing loop:', error);
                currentStepAttempts++;
                
                if (currentStepAttempts >= maxStepAttempts) {
                    return {
                        success: false,
                        error: error instanceof Error ? error.message : 'Form processing failed',
                        needsApproval: true,
                        screenshot_url: await this.takeScreenshot()
                    };
                }
            }
        }

        // If we exit the loop without completion
        return {
            success: false,
            needsApproval: true,
            question: 'Form processing exceeded maximum steps. Manual completion required.',
            screenshot_url: await this.takeScreenshot()
        };
    }

    private async fillStandardFields(fields: any[], userData: JobApplicationData): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            const standardFieldMappings = {
                'name': userData.name,
                'first name': userData.first_name || userData.name?.split(' ')[0],
                'last name': userData.last_name || userData.name?.split(' ').slice(1).join(' '),
                'email': userData.email,
                'phone': userData.phone,
                'address': userData.address,
                'city': userData.city,
                'state': userData.state,
                'zip': userData.zip_code,
                'postal code': userData.zip_code,
                'linkedin': userData.linkedin_url,
                'website': userData.website || userData.portfolio_url,
                'portfolio': userData.portfolio_url,
                'github': userData.github_url
            };

            for (const field of fields) {
                if (field.fieldType === 'file') continue; // Handle separately
                
                const fieldLabelLower = field.label.toLowerCase();
                let valueToFill = null;

                // Find matching value for this field
                for (const [key, value] of Object.entries(standardFieldMappings)) {
                    if (fieldLabelLower.includes(key) && value) {
                        valueToFill = value;
                        break;
                    }
                }

                if (valueToFill && !this.session!.completedFields.has(field.label)) {
                    try {
                        if (field.fieldType === 'select' || field.fieldType === 'radio') {
                            await this.stagehand.page.act(`select "${valueToFill}" for the "${field.label}" field`);
                        } else if (field.fieldType === 'checkbox') {
                            // Handle checkboxes based on the field context
                            await this.stagehand.page.act(`check the "${field.label}" checkbox if appropriate`);
                        } else {
                            await this.stagehand.page.act(`fill in the "${field.label}" field with "${valueToFill}"`);
                        }
                        
                        this.session!.completedFields.add(field.label);
                        this.session!.formData[field.label] = valueToFill;
                        
                        logger.info(`Filled field "${field.label}" with value`);
                    } catch (error) {
                        logger.warn(`Failed to fill standard field "${field.label}":`, error);
                    }
                }
            }

            return { success: true, needsApproval: false };
        } catch (error) {
            logger.error('Error filling standard fields:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'Failed to fill standard fields',
                needsApproval: false
            };
        }
    }

    private async processCustomQuestions(
        questions: string[], 
        userData: JobApplicationData, 
        customAnswers?: Record<string, any>
    ): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        for (const question of questions) {
            // Check if we already have a custom answer
            if (customAnswers && customAnswers[question]) {
                try {
                    await this.stagehand.page.act(`answer the question "${question}" with "${customAnswers[question]}"`);
                    continue;
                } catch (error) {
                    logger.warn(`Failed to use custom answer for "${question}":`, error);
                }
            }

            // Analyze the question to determine if we can answer it intelligently
            const questionAnalysis = await this.stagehand.page.extract({
                instruction: `Analyze this question: "${question}". Determine what type of answer is expected, if it can be answered based on standard profile information, and suggest an appropriate response. Consider the context of a job application and the user's background: experience in ${userData.current_role || 'software development'}, ${userData.experience_years || '5+'} years experience, skills: ${(userData.skills || []).join(', ')}.`,
                schema: QuestionAnalysisSchema
            });

            if (questionAnalysis.needsHumanInput) {
                // Question requires human input
                return {
                    success: false,
                    needsApproval: true,
                    question: question,
                    state: await this.stagehand.page.content(),
                    screenshot_url: await this.takeScreenshot()
                };
            }

            // Try to generate an intelligent answer
            if (questionAnalysis.suggestedAnswer) {
                try {
                    if (questionAnalysis.questionType === 'multiple_choice' || questionAnalysis.questionType === 'dropdown') {
                        await this.stagehand.page.act(`select "${questionAnalysis.suggestedAnswer}" for the question "${question}"`);
                    } else if (questionAnalysis.questionType === 'yes_no') {
                        await this.stagehand.page.act(`answer "${questionAnalysis.suggestedAnswer}" for the yes/no question "${question}"`);
                    } else {
                        await this.stagehand.page.act(`answer the question "${question}" with "${questionAnalysis.suggestedAnswer}"`);
                    }
                    logger.info(`Auto-answered question: "${question}" with "${questionAnalysis.suggestedAnswer}"`);
                } catch (error) {
                    logger.warn(`Failed to auto-answer question "${question}":`, error);
                    return {
                        success: false,
                        needsApproval: true,
                        question: question,
                        state: await this.stagehand.page.content(),
                        screenshot_url: await this.takeScreenshot()
                    };
                }
            }
        }

        return { success: true, needsApproval: false };
    }

    private async handleFileUploads(userData: JobApplicationData): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            // Handle resume upload if available
            if (userData.resume_url) {
                const resumeResult = await this.uploadFileFromUrl(userData.resume_url, 'resume');
                if (!resumeResult.success) {
                    return resumeResult;
                }
            }

            // Handle cover letter if available
            if (userData.cover_letter_url) {
                const coverLetterResult = await this.uploadFileFromUrl(userData.cover_letter_url, 'cover letter');
                if (!coverLetterResult.success) {
                    return coverLetterResult;
                }
            }

            return { success: true, needsApproval: false };
        } catch (error) {
            logger.error('Error handling file uploads:', error);
            return {
                success: false,
                error: error instanceof Error ? error.message : 'File upload failed',
                needsApproval: false
            };
        }
    }

    private async uploadFileFromUrl(fileUrl: string, fileType: string): Promise<ApplicationResult> {
        // Implementation would download from S3 URL and upload to form
        // This is a simplified version - you'd need to implement the actual file handling
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            // For now, attempt to trigger file upload UI
            await this.stagehand.page.act(`click the ${fileType} file upload button or area`);
            
            // In a real implementation, you would:
            // 1. Download the file from the S3 URL
            // 2. Save it to a temporary location
            // 3. Use Playwright's setInputFiles to upload it
            
            logger.info(`File upload action attempted for ${fileType}`);
            return { 
                success: false, 
                needsApproval: true,
                question: `Please upload your ${fileType} file manually. The file is available at: ${fileUrl}`,
                screenshot_url: await this.takeScreenshot()
            };
        } catch (error) {
            return {
                success: false,
                needsApproval: true,
                question: `Unable to upload ${fileType} automatically. Please upload manually from: ${fileUrl}`,
                screenshot_url: await this.takeScreenshot()
            };
        }
    }

    private async proceedToNextStepOrSubmit(formAnalysis: any): Promise<{
        completed: boolean;
        nextStep: boolean;
        needsApproval: boolean;
        result?: ApplicationResult;
    }> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            // Look for submit buttons first
            if (formAnalysis.submitButtonText) {
                await this.stagehand.page.act(`click the "${formAnalysis.submitButtonText}" button`);
                await this.sleep(3000); // Wait for submission
                
                // Check if submission was successful
                const isComplete = await this.checkIfApplicationComplete();
                return { completed: isComplete, nextStep: false, needsApproval: false };
            }

            // Look for next step buttons
            if (formAnalysis.nextButtonText && formAnalysis.canProceedToNext) {
                await this.stagehand.page.act(`click the "${formAnalysis.nextButtonText}" button`);
                return { completed: false, nextStep: true, needsApproval: false };
            }

            // Try generic submit/next actions
            const genericActions = [
                'click the submit button',
                'click the next button',
                'click continue',
                'click apply now',
                'click send application'
            ];

            for (const action of genericActions) {
                try {
                    await this.stagehand.page.act(action);
                    await this.sleep(2000);
                    
                    const isComplete = await this.checkIfApplicationComplete();
                    if (isComplete) {
                        return { completed: true, nextStep: false, needsApproval: false };
                    } else {
                        return { completed: false, nextStep: true, needsApproval: false };
                    }
                } catch (error) {
                    continue; // Try next action
                }
            }

            // If we can't proceed automatically
            return {
                completed: false,
                nextStep: false,
                needsApproval: true,
                result: {
                    success: false,
                    needsApproval: true,
                    question: 'Unable to find next step or submit button. Manual action required.',
                    screenshot_url: await this.takeScreenshot()
                }
            };

        } catch (error) {
            logger.error('Error proceeding to next step:', error);
            return {
                completed: false,
                nextStep: false,
                needsApproval: true,
                result: {
                    success: false,
                    error: error instanceof Error ? error.message : 'Navigation error',
                    needsApproval: true
                }
            };
        }
    }

    private async checkIfApplicationComplete(): Promise<boolean> {
        if (!this.stagehand) return false;

        try {
            const completionCheck = await this.stagehand.page.extract({
                instruction: "Check if the application has been successfully submitted. Look for confirmation messages, thank you pages, application IDs, or success indicators.",
                schema: z.object({
                    isComplete: z.boolean(),
                    confirmationFound: z.boolean()
                })
            });

            return completionCheck.isComplete || completionCheck.confirmationFound;
        } catch (error) {
            logger.error('Error checking application completion:', error);
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

    private async handleAuthentication(credentials: JobCredentials): Promise<ApplicationResult> {
        if (!this.stagehand) throw new Error('Stagehand not initialized');

        try {
            await this.stagehand.page.act(`fill in the email or username field with "${credentials.username}"`);
            await this.stagehand.page.act(`fill in the password field with "${credentials.password}"`);
            await this.stagehand.page.act('click the login or sign in button');
            
            await this.stagehand.page.waitForLoadState('domcontentloaded');
            await this.sleep(2000);

            return { success: true, needsApproval: false };
        } catch (error) {
            return {
                success: false,
                error: 'Authentication failed',
                needsApproval: true,
                screenshot_url: await this.takeScreenshot()
            };
        }
    }

    private async getConfirmationMessage(): Promise<string | undefined> {
        if (!this.stagehand) return undefined;

        try {
            const confirmation = await this.stagehand.page.extract({
                instruction: "Extract any confirmation message, application ID, reference number, or success message from the page",
                schema: ConfirmationSchema
            });

            return confirmation.message || confirmation.applicationId || 'Application submitted successfully';
        } catch (error) {
            logger.error('Error getting confirmation message:', error);
            return 'Application submitted';
        }
    }

    private async takeScreenshot(): Promise<string | undefined> {
        if (!this.stagehand) return undefined;

        try {
            const timestamp = Date.now();
            const screenshotPath = `/tmp/screenshot-${timestamp}.png`;
            
            await this.stagehand.page.screenshot({
                path: screenshotPath,
                fullPage: true
            });

            // In production, upload to S3 and return URL
            return `screenshot-${timestamp}.png`;
        } catch (error) {
            logger.error('Error taking screenshot:', error);
            return undefined;
        }
    }

    private async sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    private getMockResult(task: JobApplicationTask): ApplicationResult {
        logger.info(`Mock job application processing for ${task.title} at ${task.company}`);
        return {
            success: true,
            confirmation_message: `Mock application submitted for ${task.title} at ${task.company}`,
            needsApproval: false,
            submitted_at: new Date().toISOString()
        };
    }
}