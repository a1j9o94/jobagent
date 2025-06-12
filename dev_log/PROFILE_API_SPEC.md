# Profile and User Preferences API Specification

This document outlines how to structure and submit profiles with user preferences using the Job Agent API.

## Overview

The Job Agent API supports creating profiles with associated user preferences through a structured approach:

1. **Profile Creation**: Create the main profile with headline and summary
2. **Preference Management**: Add detailed user preferences as key-value pairs
3. **Retrieval**: Get profiles with all preferences included automatically

## API Endpoints

### Base URL
```
http://localhost:8000
```

### Authentication
- **GET requests**: No authentication required
- **POST/PUT/DELETE requests**: Require `X-API-Key` header

## 1. Profile Management

### Create Profile
```http
POST /profile
Content-Type: application/json
X-API-Key: your-api-key

{
  "headline": "Senior Full-Stack Developer | Python & React Expert",
  "summary": "Passionate full-stack developer with 8+ years of experience building scalable web applications. Expert in Python, React, and cloud technologies. Love solving complex problems and mentoring junior developers."
}
```

**Response (201 Created):**
```json
{
  "status": "created",
  "message": "Profile created successfully.",
  "profile_id": 1
}
```

### Get Profile with Preferences
```http
GET /profile/{profile_id}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "headline": "Senior Full-Stack Developer | Python & React Expert",
  "summary": "Passionate full-stack developer with 8+ years...",
  "created_at": "2025-06-11T15:30:00Z",
  "updated_at": "2025-06-11T15:30:00Z",
  "preferences": [
    {
      "id": 1,
      "key": "first_name",
      "value": "Alex",
      "last_updated": "2025-06-11T15:31:00Z"
    },
    {
      "id": 2,
      "key": "email",
      "value": "alex.johnson@email.com",
      "last_updated": "2025-06-11T15:31:00Z"
    }
  ],
  "preferences_dict": {
    "first_name": "Alex",
    "email": "alex.johnson@email.com",
    "phone": "+1-555-0101",
    "location": "San Francisco, CA"
  }
}
```

### Update Profile
```http
PUT /profile/{profile_id}
Content-Type: application/json
X-API-Key: your-api-key

{
  "headline": "Updated headline (optional)",
  "summary": "Updated summary (optional)"
}
```

## 2. User Preferences Management

### Create Preference
```http
POST /profile/{profile_id}/preferences
Content-Type: application/json
X-API-Key: your-api-key

{
  "key": "email",
  "value": "alex.johnson@email.com"
}
```

### Update Preference
```http
PUT /profile/{profile_id}/preferences/{key}
Content-Type: application/json
X-API-Key: your-api-key

{
  "value": "new_value"
}
```

### Get All Preferences
```http
GET /profile/{profile_id}/preferences
```

### Get Specific Preference
```http
GET /profile/{profile_id}/preferences/{key}
```

### Delete Preference
```http
DELETE /profile/{profile_id}/preferences/{key}
X-API-Key: your-api-key
```

## 3. Complete Profile Structure Guide

### Standard User Preference Keys

Based on the application's job automation needs, here are the recommended preference keys:

#### Personal Information
```json
{
  "first_name": "Alex",
  "last_name": "Johnson",
  "email": "alex.johnson@email.com",
  "phone": "+1-555-0101",
  "location": "San Francisco, CA"
}
```

#### Professional Links
```json
{
  "linkedin": "https://linkedin.com/in/alexjohnson",
  "github": "https://github.com/alexjohnson",
  "portfolio": "https://alexjohnson.dev",
  "website": "https://personal-site.com"
}
```

#### Job Search Preferences
```json
{
  "desired_salary": "$140,000 - $180,000",
  "work_mode": "remote",
  "availability": "2 weeks notice",
  "visa_status": "US Citizen",
  "willing_to_relocate": "false"
}
```

#### Document References
```json
{
  "resume_url": "https://storage.example.com/resumes/alex-resume.pdf",
  "cover_letter_template": "Dear Hiring Manager, I am excited to apply...",
  "references": "Available upon request"
}
```

#### Skills & Experience
```json
{
  "years_experience": "8",
  "primary_skills": "Python, React, FastAPI, PostgreSQL",
  "certifications": "AWS Solutions Architect, Certified ScrumMaster",
  "education": "BS Computer Science, Stanford University"
}
```

## 4. Complete Example Workflow

### Step 1: Create Profile
```bash
curl -X POST http://localhost:8000/profile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "headline": "Senior Full-Stack Developer | Python & React Expert",
    "summary": "Passionate full-stack developer with 8+ years of experience building scalable web applications. Expert in Python, React, and cloud technologies. Love solving complex problems and mentoring junior developers."
  }'
```

### Step 2: Add Personal Information
```bash
# First Name
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "first_name", "value": "Alex"}'

# Last Name
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "last_name", "value": "Johnson"}'

# Email
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "email", "value": "alex.johnson@email.com"}'

# Phone
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "phone", "value": "+1-555-0101"}'

# Location
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "location", "value": "San Francisco, CA"}'
```

### Step 3: Add Professional Information
```bash
# LinkedIn
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "linkedin", "value": "https://linkedin.com/in/alexjohnson"}'

# GitHub
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "github", "value": "https://github.com/alexjohnson"}'

# Desired Salary
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "desired_salary", "value": "$140,000 - $180,000"}'

# Work Mode
curl -X POST http://localhost:8000/profile/1/preferences \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"key": "work_mode", "value": "remote"}'
```

### Step 4: Verify Complete Profile
```bash
curl http://localhost:8000/profile/1
```

## 5. Batch Creation Script Example

For convenience, here's a Python script to create a complete profile:

```python
import requests
import json

API_BASE = "http://localhost:8000"
API_KEY = "your-api-key"

def create_complete_profile(profile_data, preferences_data):
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Step 1: Create profile
    response = requests.post(
        f"{API_BASE}/profile",
        json=profile_data,
        headers=headers
    )
    
    if response.status_code != 201:
        raise Exception(f"Profile creation failed: {response.text}")
    
    profile_id = response.json()["profile_id"]
    print(f"Profile created with ID: {profile_id}")
    
    # Step 2: Add preferences
    for key, value in preferences_data.items():
        pref_response = requests.post(
            f"{API_BASE}/profile/{profile_id}/preferences",
            json={"key": key, "value": value},
            headers=headers
        )
        
        if pref_response.status_code != 201:
            print(f"Warning: Failed to create preference {key}: {pref_response.text}")
        else:
            print(f"Added preference: {key}")
    
    return profile_id

# Example usage
profile_data = {
    "headline": "Senior Full-Stack Developer | Python & React Expert",
    "summary": "Passionate full-stack developer with 8+ years of experience..."
}

preferences_data = {
    "first_name": "Alex",
    "last_name": "Johnson",
    "email": "alex.johnson@email.com",
    "phone": "+1-555-0101",
    "location": "San Francisco, CA",
    "linkedin": "https://linkedin.com/in/alexjohnson",
    "github": "https://github.com/alexjohnson",
    "desired_salary": "$140,000 - $180,000",
    "work_mode": "remote",
    "years_experience": "8",
    "primary_skills": "Python, React, FastAPI, PostgreSQL"
}

profile_id = create_complete_profile(profile_data, preferences_data)
print(f"Complete profile created with ID: {profile_id}")
```

## 6. Validation Rules

### Profile Fields
- **headline**: Required, string, max 255 characters
- **summary**: Required, string, no length limit (stored as TEXT)

### Preference Fields
- **key**: Required, string, case-sensitive, no spaces recommended
- **value**: Required, string, stored as text
- **Keys are unique per profile**: Cannot create duplicate keys for the same profile

### Best Practices
1. **Use consistent key naming**: lowercase with underscores (e.g., `first_name`, `desired_salary`)
2. **Store URLs as complete URLs**: Include `https://` for web links
3. **Use structured values**: For complex data, consider JSON strings
4. **Phone format**: Use international format (e.g., `+1-555-0101`)
5. **Salary ranges**: Use consistent format (e.g., `$X,XXX - $Y,YYY`)

## 7. Error Handling

### Common Error Responses

**Profile Not Found (404):**
```json
{
  "detail": "Profile not found"
}
```

**Duplicate Preference Key (409):**
```json
{
  "detail": "Preference with this key already exists"
}
```

**Missing API Key (403):**
```json
{
  "detail": "API key required"
}
```

**Validation Error (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "headline"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## 8. Rate Limits

- **Profile operations**: 10 requests per minute
- **Preference operations**: 20 requests per minute
- **GET requests**: No rate limiting

## 9. HTML View Support

Profiles can also be viewed in a browser by accessing:
```
http://localhost:8000/profile/{profile_id}
```

With `Accept: text/html` header for a formatted web view including all preferences.

## 10. Database Seeding for Testing

For development/testing, you can populate the database with sample data:
```http
GET /test/seed-db
```

This creates 3 complete profiles with all preference types as examples. 