import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from io import BytesIO
import xlsxwriter
from typing import List, Dict, Any
import hashlib
import os

# Page configuration
st.set_page_config(
    page_title="GSC URL Inspection Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #1f77b4;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'inspection_results' not in st.session_state:
    st.session_state.inspection_results = []
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'service' not in st.session_state:
    st.session_state.service = None
if 'properties' not in st.session_state:
    st.session_state.properties = []
if 'cache' not in st.session_state:
    st.session_state.cache = {}
if 'quota_usage' not in st.session_state:
    st.session_state.quota_usage = {'daily': 0, 'per_minute': 0, 'last_reset': datetime.now()}

class GSCInspector:
    def __init__(self, service):
        self.service = service
        self.daily_limit = 2000
        self.minute_limit = 600
        
    def get_cache_key(self, site_url: str, inspection_url: str) -> str:
        """Generate cache key for URL inspection"""
        return hashlib.md5(f"{site_url}:{inspection_url}".encode()).hexdigest()
    
    def check_quota(self) -> bool:
        """Check if we're within quota limits"""
        now = datetime.now()
        
        # Reset daily quota if needed
        if now.date() > st.session_state.quota_usage['last_reset'].date():
            st.session_state.quota_usage['daily'] = 0
            st.session_state.quota_usage['last_reset'] = now
        
        # Check daily limit
        if st.session_state.quota_usage['daily'] >= self.daily_limit:
            return False
            
        # Reset minute counter if needed
        if now - st.session_state.quota_usage.get('minute_reset', now) > timedelta(minutes=1):
            st.session_state.quota_usage['per_minute'] = 0
            st.session_state.quota_usage['minute_reset'] = now
            
        # Check minute limit
        if st.session_state.quota_usage['per_minute'] >= self.minute_limit:
            return False
            
        return True
    
    def update_quota(self):
        """Update quota usage"""
        st.session_state.quota_usage['daily'] += 1
        st.session_state.quota_usage['per_minute'] += 1
    
    def inspect_url(self, site_url: str, inspection_url: str, use_cache: bool = True) -> Dict[str, Any]:
        """Inspect a single URL"""
        cache_key = self.get_cache_key(site_url, inspection_url)
        
        # Check cache first
        if use_cache and cache_key in st.session_state.cache:
            cached_data = st.session_state.cache[cache_key]
            if datetime.now() - cached_data['timestamp'] < timedelta(hours=24):
                return cached_data['data']
        
        # Check quota
        if not self.check_quota():
            raise Exception("Quota limit reached. Please try again later.")
        
        try:
            request = {
                'siteUrl': site_url,
                'inspectionUrl': inspection_url,
                'languageCode': 'en-US'
            }
            
            response = self.service.urlInspection().index().inspect(body=request).execute()
            
            # Update quota
            self.update_quota()
            
            # Cache the result
            st.session_state.cache[cache_key] = {
                'data': response,
                'timestamp': datetime.now()
            }
            
            return response
            
        except HttpError as e:
            error_content = json.loads(e.content.decode())
            raise Exception(f"API Error: {error_content.get('error', {}).get('message', 'Unknown error')}")
    
    def batch_inspect(self, site_url: str, urls: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """Inspect multiple URLs with rate limiting"""
        results = []
        total_urls = len(urls)
        
        for i, url in enumerate(urls):
            try:
                # Rate limiting - wait if we're approaching minute limit
                if st.session_state.quota_usage['per_minute'] >= self.minute_limit - 10:
                    time.sleep(60)  # Wait a minute
                    st.session_state.quota_usage['per_minute'] = 0
                    st.session_state.quota_usage['minute_reset'] = datetime.now()
                
                result = self.inspect_url(site_url, url)
                results.append({
                    'url': url,
                    'status': 'success',
                    'data': result,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Small delay to avoid hitting rate limits
                time.sleep(0.1)
                
            except Exception as e:
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
            
            if progress_callback:
                progress_callback((i + 1) / total_urls, f"Processed {i + 1} of {total_urls} URLs")
        
        return results

def authenticate_gsc(credentials_json: Dict[str, Any]) -> Any:
    """Authenticate with Google Search Console API"""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            credentials_json,
            scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        
        service = build('searchconsole', 'v1', credentials=credentials)
        
        # Test authentication by getting site list
        sites = service.sites().list().execute()
        properties = [site['siteUrl'] for site in sites.get('siteEntry', [])]
        
        return service, properties
        
    except Exception as e:
        raise Exception(f"Authentication failed: {str(e)}")

def parse_inspection_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Parse inspection result into a flat dictionary"""
    parsed = {
        'inspection_url': result.get('url', ''),
        'inspection_result_link': '',
        'verdict': '',
        'coverage_state': '',
        'indexing_state': '',
        'last_crawl_time': '',
        'page_fetch_state': '',
        'robots_txt_state': '',
        'user_canonical': '',
        'google_canonical': '',
        'mobile_verdict': '',
        'rich_results_verdict': '',
        'rich_results_detected': '',
        'crawled_as': ''
    }
    
    if 'inspectionResult' in result.get('data', {}):
        inspection = result['data']['inspectionResult']
        parsed['inspection_result_link'] = inspection.get('inspectionResultLink', '')
        
        # Index status
        if 'indexStatusResult' in inspection:
            idx_status = inspection['indexStatusResult']
            parsed['verdict'] = idx_status.get('verdict', '')
            parsed['coverage_state'] = idx_status.get('coverageState', '')
            parsed['indexing_state'] = idx_status.get('indexingState', '')
            parsed['last_crawl_time'] = idx_status.get('lastCrawlTime', '')
            parsed['page_fetch_state'] = idx_status.get('pageFetchState', '')
            parsed['robots_txt_state'] = idx_status.get('robotsTxtState', '')
            parsed['user_canonical'] = idx_status.get('userCanonical', '')
            parsed['google_canonical'] = idx_status.get('googleCanonical', '')
            parsed['crawled_as'] = idx_status.get('crawledAs', '')
        
        # Mobile usability
        if 'mobileUsabilityResult' in inspection:
            parsed['mobile_verdict'] = inspection['mobileUsabilityResult'].get('verdict', '')
        
        # Rich results
        if 'richResultsResult' in inspection:
            rich_results = inspection['richResultsResult']
            parsed['rich_results_verdict'] = rich_results.get('verdict', '')
            detected_items = rich_results.get('detectedItems', [])
            parsed['rich_results_detected'] = ', '.join([item.get('richResultType', '') for item in detected_items])
    
    return parsed

def create_visualizations(df: pd.DataFrame):
    """Create visualizations from inspection results"""
    col1, col2 = st.columns(2)
    
    with col1:
        # Indexing status pie chart
        status_counts = df['coverage_state'].value_counts()
        fig_status = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Coverage State Distribution",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        st.plotly_chart(fig_status, use_container_width=True)
        
        # Mobile usability
        mobile_counts = df['mobile_verdict'].value_counts()
        fig_mobile = px.bar(
            x=mobile_counts.index,
            y=mobile_counts.values,
            title="Mobile Usability Status",
            labels={'x': 'Verdict', 'y': 'Count'},
            color=mobile_counts.index,
            color_discrete_map={'PASS': 'green', 'FAIL': 'red', 'NEUTRAL': 'gray'}
        )
        st.plotly_chart(fig_mobile, use_container_width=True)
    
    with col2:
        # Page fetch state
        fetch_counts = df['page_fetch_state'].value_counts()
        fig_fetch = px.pie(
            values=fetch_counts.values,
            names=fetch_counts.index,
            title="Page Fetch State Distribution",
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        st.plotly_chart(fig_fetch, use_container_width=True)
        
        # Crawled as (Mobile vs Desktop)
        crawled_counts = df['crawled_as'].value_counts()
        fig_crawled = px.bar(
            x=crawled_counts.index,
            y=crawled_counts.values,
            title="Crawled As (Mobile vs Desktop)",
            labels={'x': 'Crawled As', 'y': 'Count'},
            color=crawled_counts.index,
            color_discrete_map={'MOBILE': 'blue', 'DESKTOP': 'orange'}
        )
        st.plotly_chart(fig_crawled, use_container_width=True)

def export_to_excel(df: pd.DataFrame) -> BytesIO:
    """Export DataFrame to Excel with formatting"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='URL Inspection Results', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['URL Inspection Results']
        
        # Add formatting
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BD',
            'border': 1
        })
        
        # Write headers with formatting
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Auto-fit columns
        for i, col in enumerate(df.columns):
            column_width = max(df[col].astype(str).str.len().max(), len(col)) + 2
            worksheet.set_column(i, i, min(column_width, 50))
    
    output.seek(0)
    return output

def main():
    st.title("🔍 Google Search Console URL Inspection Tool")
    st.markdown("Bulk inspect URLs using the Google Search Console API with advanced features")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Authentication section
        st.subheader("🔐 Authentication")
        
        if not st.session_state.authenticated:
            st.info("Upload your service account credentials JSON file")
            uploaded_file = st.file_uploader("Choose credentials file", type=['json'])
            
            if uploaded_file is not None:
                try:
                    credentials = json.load(uploaded_file)
                    service, properties = authenticate_gsc(credentials)
                    st.session_state.service = service
                    st.session_state.properties = properties
                    st.session_state.authenticated = True
                    st.success("✅ Authentication successful!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {str(e)}")
        else:
            st.success("✅ Authenticated")
            if st.button("🚪 Logout"):
                st.session_state.authenticated = False
                st.session_state.service = None
                st.session_state.properties = []
                st.rerun()
        
        # Quota information
        st.subheader("📊 Quota Usage")
        quota_progress = st.session_state.quota_usage['daily'] / 2000
        st.progress(quota_progress)
        st.caption(f"Daily: {st.session_state.quota_usage['daily']}/2000")
        st.caption(f"Per minute: {st.session_state.quota_usage['per_minute']}/600")
        
        # Cache settings
        st.subheader("💾 Cache Settings")
        use_cache = st.checkbox("Use cache (24h)", value=True)
        if st.button("🗑️ Clear Cache"):
            st.session_state.cache = {}
            st.success("Cache cleared!")
    
    # Main content
    if st.session_state.authenticated:
        inspector = GSCInspector(st.session_state.service)
        
        # Property selection
        st.subheader("🌐 Select Property")
        selected_property = st.selectbox(
            "Choose a Search Console property",
            st.session_state.properties,
            help="Select the property you want to inspect URLs for"
        )
        
        # URL input
        st.subheader("📝 Enter URLs to Inspect")
        
        tab1, tab2 = st.tabs(["Manual Input", "Upload CSV"])
        
        with tab1:
            urls_text = st.text_area(
                "Enter URLs (one per line)",
                height=200,
                placeholder="https://example.com/page1\nhttps://example.com/page2\nhttps://example.com/page3"
            )
            
        with tab2:
            uploaded_csv = st.file_uploader("Upload CSV file with URLs", type=['csv'])
            url_column = st.text_input("URL column name", value="url")
        
        # Inspection options
        col1, col2, col3 = st.columns(3)
        with col1:
            batch_size = st.number_input("Batch size", min_value=1, max_value=100, value=10)
        with col2:
            delay_between_batches = st.number_input("Delay between batches (seconds)", min_value=0, max_value=60, value=5)
        with col3:
            export_format = st.selectbox("Export format", ["CSV", "Excel", "JSON"])
        
        # Start inspection
        if st.button("🚀 Start Inspection", type="primary"):
            # Prepare URLs
            urls_to_inspect = []
            
            if urls_text:
                urls_to_inspect = [url.strip() for url in urls_text.split('\n') if url.strip()]
            elif uploaded_csv:
                df_urls = pd.read_csv(uploaded_csv)
                if url_column in df_urls.columns:
                    urls_to_inspect = df_urls[url_column].dropna().tolist()
                else:
                    st.error(f"Column '{url_column}' not found in CSV")
            
            if urls_to_inspect:
                st.info(f"🔄 Starting inspection of {len(urls_to_inspect)} URLs...")
                
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process URLs in batches
                all_results = []
                for i in range(0, len(urls_to_inspect), batch_size):
                    batch = urls_to_inspect[i:i+batch_size]
                    
                    def update_progress(progress, text):
                        overall_progress = (i + progress * len(batch)) / len(urls_to_inspect)
                        progress_bar.progress(overall_progress)
                        status_text.text(text)
                    
                    batch_results = inspector.batch_inspect(
                        selected_property,
                        batch,
                        progress_callback=update_progress
                    )
                    all_results.extend(batch_results)
                    
                    # Delay between batches
                    if i + batch_size < len(urls_to_inspect):
                        time.sleep(delay_between_batches)
                
                # Store results
                st.session_state.inspection_results = all_results
                
                # Clear progress
                progress_bar.empty()
                status_text.empty()
                
                st.success(f"✅ Inspection complete! Processed {len(all_results)} URLs")
            else:
                st.warning("⚠️ No URLs to inspect")
        
        # Display results
        if st.session_state.inspection_results:
            st.header("📊 Inspection Results")
            
            # Parse results into DataFrame
            parsed_results = []
            for result in st.session_state.inspection_results:
                if result['status'] == 'success':
                    parsed = parse_inspection_result(result)
                    parsed['url'] = result['url']
                    parsed['status'] = 'success'
                    parsed['timestamp'] = result['timestamp']
                    parsed_results.append(parsed)
                else:
                    parsed_results.append({
                        'url': result['url'],
                        'status': 'error',
                        'error': result.get('error', 'Unknown error'),
                        'timestamp': result['timestamp']
                    })
            
            df_results = pd.DataFrame(parsed_results)
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                total_urls = len(df_results)
                st.metric("Total URLs", total_urls)
            with col2:
                success_count = len(df_results[df_results['status'] == 'success'])
                st.metric("Successful", success_count)
            with col3:
                error_count = len(df_results[df_results['status'] == 'error'])
                st.metric("Errors", error_count)
            with col4:
                if 'coverage_state' in df_results.columns:
                    indexed_count = len(df_results[df_results['coverage_state'].str.contains('Indexed', na=False)])
                    st.metric("Indexed", indexed_count)
            
            # Visualizations
            if success_count > 0:
                st.subheader("📈 Visualizations")
                df_success = df_results[df_results['status'] == 'success'].copy()
                create_visualizations(df_success)
            
            # Detailed results table
            st.subheader("📋 Detailed Results")
            
            # Filters
            with st.expander("🔍 Filters"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    filter_status = st.multiselect(
                        "Status",
                        options=df_results['status'].unique(),
                        default=df_results['status'].unique()
                    )
                with col2:
                    if 'coverage_state' in df_results.columns:
                        coverage_states = df_results['coverage_state'].dropna().unique()
                        filter_coverage = st.multiselect(
                            "Coverage State",
                            options=coverage_states,
                            default=coverage_states
                        )
                with col3:
                    if 'mobile_verdict' in df_results.columns:
                        mobile_verdicts = df_results['mobile_verdict'].dropna().unique()
                        filter_mobile = st.multiselect(
                            "Mobile Verdict",
                            options=mobile_verdicts,
                            default=mobile_verdicts
                        )
            
            # Apply filters
            filtered_df = df_results[df_results['status'].isin(filter_status)]
            if 'coverage_state' in df_results.columns and filter_coverage:
                filtered_df = filtered_df[filtered_df['coverage_state'].isin(filter_coverage)]
            if 'mobile_verdict' in df_results.columns and filter_mobile:
                filtered_df = filtered_df[filtered_df['mobile_verdict'].isin(filter_mobile)]
            
            # Display table
            st.dataframe(
                filtered_df,
                use_container_width=True,
                height=400
            )
            
            # Export options
            st.subheader("💾 Export Results")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if export_format == "CSV":
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"gsc_inspection_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                if export_format == "Excel":
                    excel_file = export_to_excel(filtered_df)
                    st.download_button(
                        label="📥 Download Excel",
                        data=excel_file,
                        file_name=f"gsc_inspection_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            with col3:
                if export_format == "JSON":
                    json_data = json.dumps(st.session_state.inspection_results, indent=2)
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_data,
                        file_name=f"gsc_inspection_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
    else:
        st.info("👈 Please authenticate using your Google Search Console service account credentials in the sidebar.")
        
        with st.expander("📖 How to get service account credentials"):
            st.markdown("""
            1. Go to [Google Cloud Console](https://console.cloud.google.com/)
            2. Create a new project or select an existing one
            3. Enable the **Google Search Console API**
            4. Go to **APIs & Services** → **Credentials**
            5. Click **Create Credentials** → **Service Account**
            6. Download the JSON key file
            7. Add the service account email as an **owner** in Google Search Console for your properties
            """)

if __name__ == "__main__":
    main()
