import { describe, it, expect } from 'vitest';
import { 
  TaskType, 
  JobApplicationTask, 
  UpdateJobStatusTask, 
  ApprovalRequestTask 
} from './tasks';

describe('Task Types', () => {
  describe('TaskType enum', () => {
    it('should have correct string values', () => {
      expect(TaskType.JOB_APPLICATION).toBe('job_application');
      expect(TaskType.UPDATE_JOB_STATUS).toBe('update_job_status');
      expect(TaskType.APPROVAL_REQUEST).toBe('approval_request');
      expect(TaskType.SEND_NOTIFICATION).toBe('send_notification');
    });
  });

  describe('JobApplicationTask interface', () => {
    it('should validate a complete task payload', () => {
      const validTask: JobApplicationTask = {
        job_id: 123,
        job_url: 'https://example.com/job',
        company: 'TestCorp',
        title: 'Software Engineer',
        user_data: {
          name: 'John Doe',
          email: 'john@example.com',
          phone: '+1234567890',
          first_name: 'John',
          last_name: 'Doe'
        },
        application_id: 456
      };

      expect(validTask.job_id).toBe(123);
      expect(validTask.job_url).toBe('https://example.com/job');
      expect(validTask.user_data.name).toBe('John Doe');
      expect(validTask.application_id).toBe(456);
    });

    it('should allow optional fields', () => {
      const taskWithOptionals: JobApplicationTask = {
        job_id: 123,
        job_url: 'https://example.com/job',
        company: 'TestCorp',
        title: 'Software Engineer',
        user_data: {
          name: 'John Doe',
          email: 'john@example.com',
          phone: '+1234567890',
          resume_url: 'https://example.com/resume.pdf',
          linkedin_url: 'https://linkedin.com/in/johndoe'
        },
        credentials: {
          username: 'john@example.com',
          password: 'secret123'
        },
        custom_answers: {
          'years_experience': '5',
          'willing_to_relocate': true
        },
        application_id: 456
      };

      expect(taskWithOptionals.credentials?.username).toBe('john@example.com');
      expect(taskWithOptionals.custom_answers?.years_experience).toBe('5');
      expect(taskWithOptionals.user_data.resume_url).toBe('https://example.com/resume.pdf');
    });
  });

  describe('UpdateJobStatusTask interface', () => {
    it('should validate status update task', () => {
      const statusTask: UpdateJobStatusTask = {
        job_id: 123,
        application_id: 456,
        status: 'applied',
        notes: 'Application submitted successfully',
        submitted_at: '2024-01-01T12:00:00Z'
      };

      expect(statusTask.status).toBe('applied');
      expect(statusTask.notes).toBe('Application submitted successfully');
    });

    it('should allow error fields for failed applications', () => {
      const errorTask: UpdateJobStatusTask = {
        job_id: 123,
        application_id: 456,
        status: 'failed',
        error_message: 'Network timeout',
        screenshot_url: 'https://example.com/error_screenshot.png'
      };

      expect(errorTask.status).toBe('failed');
      expect(errorTask.error_message).toBe('Network timeout');
      expect(errorTask.screenshot_url).toBe('https://example.com/error_screenshot.png');
    });
  });

  describe('ApprovalRequestTask interface', () => {
    it('should validate approval request task', () => {
      const approvalTask: ApprovalRequestTask = {
        job_id: 123,
        application_id: 456,
        question: 'What is your salary expectation?',
        current_state: '{"page": "application_form", "step": 2}',
        screenshot_url: 'https://example.com/approval_screenshot.png',
        context: {
          page_title: 'Job Application - Step 2',
          page_url: 'https://company.com/apply/step2',
          form_fields: ['salary_expectation', 'start_date']
        }
      };

      expect(approvalTask.question).toBe('What is your salary expectation?');
      expect(approvalTask.context?.page_title).toBe('Job Application - Step 2');
      expect(approvalTask.context?.form_fields).toContain('salary_expectation');
    });

    it('should allow minimal approval request', () => {
      const minimalTask: ApprovalRequestTask = {
        job_id: 123,
        application_id: 456,
        question: 'Please confirm your application'
      };

      expect(minimalTask.question).toBe('Please confirm your application');
      expect(minimalTask.current_state).toBeUndefined();
      expect(minimalTask.context).toBeUndefined();
    });
  });
}); 