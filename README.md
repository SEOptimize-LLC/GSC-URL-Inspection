# Google Search Console URL Inspection Tool

A powerful Streamlit application for bulk URL inspection using the Google Search Console API. This tool allows you to inspect multiple URLs at once, visualize indexation status, and export comprehensive reports.

## 🌟 Features

### Core Functionality
- **Bulk URL Inspection**: Inspect multiple URLs at once with automatic rate limiting
- **Service Account Authentication**: Secure authentication using Google service account credentials
- **Multi-Property Support**: Switch between different Google Search Console properties
- **Smart Caching**: 24-hour cache to minimize API calls and preserve quota

### Data Input Options
- **Manual Input**: Paste URLs directly into the text area
- **CSV Upload**: Upload a CSV file containing URLs
- **Batch Processing**: Process URLs in configurable batch sizes with delays

### Visualizations
- **Coverage State Distribution**: Pie chart showing indexation status
- **Mobile Usability Status**: Bar chart of mobile-friendly verdicts
- **Page Fetch State**: Distribution of successful vs failed fetches
- **Crawl Type Analysis**: Mobile vs Desktop crawling statistics

### Export Options
- **CSV Export**: Download results as CSV for further analysis
- **Excel Export**: Formatted Excel file with auto-fitted columns
- **JSON Export**: Raw JSON data for programmatic use

### Advanced Features
- **Real-time Progress Tracking**: Visual progress bars during inspection
- **Quota Management**: Track daily (2000) and per-minute (600) API limits
- **Error Handling**: Comprehensive error messages and recovery
- **Filtering**: Filter results by status, coverage state, and mobile verdict
- **Historical Comparison**: Cache results for trend analysis

## 🚀 Deployment on Streamlit Cloud

### Prerequisites
1. A Google Cloud Platform account
2. Google Search Console API enabled
3. Service account with proper permissions
4. Access to Google Search Console properties

### Setup Instructions

#### 1. Google Cloud Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Search Console API**:
   - Navigate to APIs & Services → Library
   - Search for "Google Search Console API"
   - Click Enable

#### 2. Create Service Account
1. Go to APIs & Services → Credentials
2. Click "Create Credentials" → "Service Account"
3. Fill in service account details
4. Grant appropriate roles (optional)
5. Create and download JSON key file

#### 3. Configure Google Search Console
1. Go to [Google Search Console](https://search.google.com/search-console)
2. For each property you want to inspect:
   - Go to Settings → Users and permissions
   - Add the service account email as an **Owner**
   - The email format: `your-service-account@your-project.iam.gserviceaccount.com`
