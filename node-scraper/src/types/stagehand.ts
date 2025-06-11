export interface StagehandConfig {
    headless: boolean;
    timeout?: number;
    viewport?: {
        width: number;
        height: number;
    };
    userAgent?: string;
    locale?: string;
}

export interface ApplicationResult {
    success: boolean;
    needsApproval?: boolean;
    question?: string;
    state?: string;
    error?: string;
    screenshot_url?: string;
    submitted_at?: string;
    form_data_captured?: Record<string, any>;
    page_title?: string;
    confirmation_message?: string;
}

export interface FormField {
    name: string;
    type: string;
    value?: string;
    required?: boolean;
    options?: string[];
    placeholder?: string;
}

export interface PageState {
    url: string;
    title: string;
    forms: FormField[];
    timestamp: string;
    screenshot_url?: string;
}

export interface StagehandAction {
    type: 'click' | 'fill' | 'select' | 'upload' | 'wait' | 'extract';
    selector?: string;
    text?: string;
    file_path?: string;
    timeout?: number;
    description: string;
}

export interface AutomationStep {
    action: StagehandAction;
    success: boolean;
    error?: string;
    duration_ms: number;
    screenshot_url?: string;
} 