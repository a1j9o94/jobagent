export interface JobApplicationTask {
    job_id: number;
    job_url: string;
    company: string;
    title: string;
    user_data: {
        name: string;
        email: string;
        phone: string;
        resume_url?: string;
        first_name?: string;
        last_name?: string;
        linkedin_url?: string;
        github_url?: string;
        portfolio_url?: string;
        [key: string]: any;
    };
    credentials?: {
        username: string;
        password: string;
    };
    custom_answers?: Record<string, any>;
    application_id: number;
}

export interface UpdateJobStatusTask {
    job_id: number;
    application_id: number;
    status: 'applied' | 'failed' | 'waiting_approval' | 'needs_user_info';
    notes?: string;
    error_message?: string;
    screenshot_url?: string;
    submitted_at?: string; // ISO timestamp
}

export interface ApprovalRequestTask {
    job_id: number;
    application_id: number;
    question: string;
    current_state?: string; // Serialized page state
    screenshot_url?: string;
    context?: {
        page_title?: string;
        page_url?: string;
        form_fields?: string[];
    };
}

export enum TaskType {
    JOB_APPLICATION = "job_application",
    UPDATE_JOB_STATUS = "update_job_status", 
    APPROVAL_REQUEST = "approval_request",
    SEND_NOTIFICATION = "send_notification"
}

export interface QueueTask<T = any> {
    id: string;
    type: TaskType;
    payload: T;
    retries: number;
    created_at: string;
    priority?: number;
}

export interface TaskResult {
    success: boolean;
    task_id: string;
    error?: string;
    data?: any;
} 