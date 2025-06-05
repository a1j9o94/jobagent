# app/automation.py
import logging
import asyncio
from playwright.async_api import async_playwright, Browser, Page
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FormSubmissionError(Exception):
    """Raised when form submission fails."""
    pass

class BrowserAutomation:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def submit_job_application(
        self, 
        posting_url: str, 
        form_data: Dict[str, Any],
        credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Submit a job application form.
        
        Returns a dictionary with submission status and details.
        """
        if not self.browser:
            raise FormSubmissionError("Browser not initialized")
        
        page = await self.browser.new_page()
        
        try:
            logger.info(f"Navigating to job posting: {posting_url}")
            await page.goto(posting_url, wait_until='networkidle')
            
            # Platform-specific submission logic
            if 'greenhouse.io' in posting_url:
                return await self._submit_greenhouse_form(page, form_data)
            elif 'workday.com' in posting_url:
                return await self._submit_workday_form(page, form_data, credentials)
            elif 'lever.co' in posting_url:
                return await self._submit_lever_form(page, form_data)
            else:
                return await self._submit_generic_form(page, form_data)
                
        except Exception as e:
            logger.error(f"Form submission failed: {e}")
            # Take screenshot for debugging
            await page.screenshot(path=f"error_{posting_url.split('/')[-1]}.png")
            return {
                "status": "error",
                "message": str(e),
                "screenshot_taken": True
            }
        finally:
            await page.close()
    
    async def _submit_greenhouse_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Greenhouse.io application forms."""
        try:
            # Wait for and click apply button
            await page.wait_for_selector('a[data-mapped="true"]', timeout=10000)
            await page.click('a[data-mapped="true"]')
            
            # Fill basic information
            await page.fill('input[name="first_name"]', form_data.get('first_name', ''))
            await page.fill('input[name="last_name"]', form_data.get('last_name', ''))
            await page.fill('input[name="email"]', form_data.get('email', ''))
            await page.fill('input[name="phone"]', form_data.get('phone', ''))
            
            # Upload resume if provided
            if 'resume_path' in form_data:
                await page.set_input_files('input[type="file"]', form_data['resume_path'])
            
            # Submit form
            await page.click('input[type="submit"]')
            
            # Wait for success confirmation
            await page.wait_for_selector('.confirmation', timeout=15000)
            
            return {
                "status": "success",
                "platform": "greenhouse",
                "message": "Application submitted successfully"
            }
            
        except Exception as e:
            raise FormSubmissionError(f"Greenhouse submission failed: {e}")
    
    async def _submit_workday_form(self, page: Page, form_data: Dict[str, Any], credentials: Dict[str, str]) -> Dict[str, Any]:
        """Handle Workday application forms (requires login)."""
        # This is a more complex implementation due to Workday's authentication
        # Implementation would include login flow, form navigation, etc.
        logger.warning("Workday automation not fully implemented")
        return {
            "status": "pending",
            "platform": "workday",
            "message": "Workday automation requires manual intervention"
        }
    
    async def _submit_lever_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Lever.co application forms."""
        try:
            # Lever typically has simpler forms
            await page.fill('input[name="name"]', f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}")
            await page.fill('input[name="email"]', form_data.get('email', ''))
            await page.fill('input[name="phone"]', form_data.get('phone', ''))
            
            if 'resume_path' in form_data:
                await page.set_input_files('input[name="resume"]', form_data['resume_path'])
            
            await page.click('button[type="submit"]')
            await page.wait_for_url('**/confirmation', timeout=15000)
            
            return {
                "status": "success",
                "platform": "lever",
                "message": "Application submitted successfully"
            }
            
        except Exception as e:
            raise FormSubmissionError(f"Lever submission failed: {e}")
    
    async def _submit_generic_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic job application forms."""
        # Basic form field detection and filling
        logger.info("Attempting generic form submission")
        
        # Common form field patterns
        field_patterns = {
            'first_name': ['input[name*="first"]', 'input[id*="first"]', 'input[placeholder*="First"]'],
            'last_name': ['input[name*="last"]', 'input[id*="last"]', 'input[placeholder*="Last"]'],
            'email': ['input[type="email"]', 'input[name*="email"]', 'input[id*="email"]'],
            'phone': ['input[type="tel"]', 'input[name*="phone"]', 'input[id*="phone"]']
        }
        
        filled_fields = 0
        for field_name, selectors in field_patterns.items():
            if field_name in form_data:
                for selector in selectors:
                    try:
                        if await page.locator(selector).count() > 0:
                            await page.fill(selector, str(form_data[field_name]))
                            filled_fields += 1
                            break
                    except Exception:
                        continue
        
        return {
            "status": "partial",
            "platform": "generic",
            "message": f"Filled {filled_fields} form fields, manual review required"
        } 