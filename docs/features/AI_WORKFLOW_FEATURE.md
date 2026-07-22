
# AI Workflow Generation Feature

## Overview
This feature adds interactive AI-powered workflow generation to the Actions Manager application.

## Components Added

### Backend (`backend/ai_workflows.py`)
- **OpenAI Integration**: Uses GPT-3.5-turbo for workflow generation and enhancement
- **Session Management**: Maintains conversation state for ongoing interactions
- **Endpoints**:
  - `POST /api/ai/generate-workflow`: Generate initial workflow from project requirements
  - `POST /api/ai/chat-interaction`: Interactive chat to customize workflows
  - `GET /api/ai/test`: Test AI integration status
  - `GET /api/ai/session/{session_id}`: Get session information
  - `DELETE /api/ai/session/{session_id}`: Delete session

### Frontend Components
- **AIWorkflowChat.js**: Interactive chat modal for workflow customization
- **aiWorkflows.js API**: Frontend API integration for AI endpoints
- **Enhanced Workflows.js**: Added "Generate Workflow with AI" button and chat integration

### Styling
- **AIWorkflowChat.css**: Comprehensive styling for the chat interface with dark theme support

## User Flow
1. User clicks "Generate Workflow with AI" button in the Workflows section
2. AI generates an initial workflow based on:
   - Project name and code
   - Selected repositories
   - Detected build types
   - User requirements
3. Interactive chat opens with suggested customization options:
   - Add security scanning (CodeQL, SonarQube)
   - Include Docker image building
   - Set up deployment automation
   - Add specific testing frameworks
4. User can chat with AI to customize the workflow
5. Workflow YAML updates in real-time in the Monaco editor
6. User can continue the conversation to further refine the workflow

## Configuration
- Requires `OPENAI_API_KEY` environment variable to be set
- Uses GPT-3.5-turbo model for cost efficiency
- Session data stored in memory (can be upgraded to Redis/database for production)

## Error Handling
- Graceful fallback when API key is not configured
- User-friendly error messages for failed requests
- Session management with cleanup capabilities
