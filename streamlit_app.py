"""
PDF Processing & Image Analysis Application
Streamlit in Snowflake (SiS) Application

This application extracts text and images from PDF files using Snowflake UDFs,
stores them in Snowflake, and uses Cortex AI models to analyze images.

IMPORTANT: Uses ONLY packages available in Streamlit in Snowflake
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark import functions as F
import json

# ================================================================
# CONFIGURATION
# ================================================================

# Database and Schema Configuration
DATABASE = "PDF_ANALYTICS_DB"
SCHEMA = "PDF_PROCESSING"
TEXT_TABLE = "PDF_TEXT_DATA"
ANALYSIS_TABLE = "IMAGE_ANALYSIS_RESULTS"
IMAGE_STAGE = "PDF_IMAGES_STAGE"
PDF_STAGE = "PDF_FILES_STAGE"

# Available Cortex AI Models
AVAILABLE_MODELS = {
    "Claude (Anthropic)": "claude-3-5-sonnet",
    "GPT-4 (OpenAI)": "gpt-4o",
    "Pixtral Large (Mistral)": "pixtral-large"
}

# Analysis Prompt Template
ANALYSIS_PROMPT = """
Analyze this property image or PDF page and provide a detailed assessment for the following categories:

1. **For Sale Sign**: Is there a "For Sale" sign visible?
2. **Solar Panels**: Are there solar panels installed on the property?
3. **Human Presence**: Are there any people visible?
4. **Potential Damage**: Is there any visible damage to the property (roof damage, broken windows, structural issues, etc.)?

For each category, provide:
- A YES/NO answer
- Confidence level (0-100%)
- Brief description of what you observed

Format your response as JSON with this structure:
{{
    "for_sale_sign": {{
        "detected": true/false,
        "confidence": 0-100,
        "description": "..."
    }},
    "solar_panels": {{
        "detected": true/false,
        "confidence": 0-100,
        "description": "..."
    }},
    "human_presence": {{
        "detected": true/false,
        "confidence": 0-100,
        "description": "..."
    }},
    "potential_damage": {{
        "detected": true/false,
        "confidence": 0-100,
        "description": "..."
    }}
}}

If this is a text page from a PDF, analyze the text content for mentions of these categories.
"""

# ================================================================
# SESSION INITIALIZATION
# ================================================================

@st.cache_resource
def get_snowflake_session():
    """Get active Snowflake session"""
    return get_active_session()

session = get_snowflake_session()

# Set context
try:
    session.sql(f"USE DATABASE {DATABASE}").collect()
    session.sql(f"USE SCHEMA {SCHEMA}").collect()
except Exception as e:
    st.error(f"Error setting database context: {str(e)}")
    st.stop()

# ================================================================
# HELPER FUNCTIONS
# ================================================================

def upload_pdf_to_stage(uploaded_file, stage_name):
    """
    Upload PDF file to Snowflake stage
    
    Args:
        uploaded_file: Streamlit uploaded file object
        stage_name: Name of the stage to upload to
        
    Returns:
        Success boolean
    """
    try:
        # Write file to stage using Snowpark
        file_bytes = uploaded_file.getvalue()
        
        # Create a temporary file path
        stage_path = f"@{stage_name}/{uploaded_file.name}"
        
        # Use PUT command to upload
        put_result = session.file.put_stream(
            uploaded_file,
            stage_path,
            auto_compress=False,
            overwrite=True
        )
        
        return True
    except Exception as e:
        st.error(f"Error uploading file: {str(e)}")
        return False

def extract_text_from_pdf_udf(file_name, stage_name):
    """
    Extract text from PDF using Snowflake UDF
    
    Args:
        file_name: Name of the PDF file
        stage_name: Name of the stage where file is located
        
    Returns:
        Extracted text string
    """
    try:
        file_path = f"@{stage_name}/{file_name}"
        
        # Call the UDF
        result = session.sql(f"SELECT EXTRACT_PDF_TEXT(BUILD_SCOPED_FILE_URL(@{stage_name}, '{file_name}')) AS TEXT").collect()
        
        if result and len(result) > 0:
            return result[0]['TEXT']
        else:
            return "No text extracted"
    except Exception as e:
        return f"Error: {str(e)}"

def get_pdf_image_count_udf(file_name, stage_name):
    """
    Get count of images in PDF using Snowflake UDF
    
    Args:
        file_name: Name of the PDF file
        stage_name: Name of the stage where file is located
        
    Returns:
        Number of images in PDF
    """
    try:
        result = session.sql(f"SELECT GET_PDF_IMAGE_COUNT(BUILD_SCOPED_FILE_URL(@{stage_name}, '{file_name}')) AS COUNT").collect()
        
        if result and len(result) > 0:
            return result[0]['COUNT']
        else:
            return 0
    except Exception as e:
        st.error(f"Error getting image count: {str(e)}")
        return 0

def save_text_to_table(file_name, text):
    """
    Save extracted text to Snowflake table
    
    Args:
        file_name: Name of the PDF file
        text: Extracted text content
    """
    try:
        # Parse text by pages (if formatted with page markers)
        if '--- Page' in text:
            pages = text.split('--- Page')[1:]  # Skip first empty split
            for page_content in pages:
                lines = page_content.split('\n', 1)
                if len(lines) >= 2:
                    page_num = int(lines[0].strip().replace(' ---', ''))
                    page_text = lines[1].strip().replace("'", "''")
                    
                    query = f"""
                    INSERT INTO {TEXT_TABLE} (FILE_NAME, PAGE_NUMBER, EXTRACTED_TEXT)
                    VALUES ('{file_name}', {page_num}, '{page_text}')
                    """
                    session.sql(query).collect()
        else:
            # Save as single page if no page markers
            text_escaped = text.replace("'", "''")
            query = f"""
            INSERT INTO {TEXT_TABLE} (FILE_NAME, PAGE_NUMBER, EXTRACTED_TEXT)
            VALUES ('{file_name}', 1, '{text_escaped}')
            """
            session.sql(query).collect()
        
        return True
    except Exception as e:
        st.error(f"Error saving text: {str(e)}")
        return False

def analyze_pdf_with_cortex(file_name, model_name, stage_name):
    """
    Analyze PDF content using Snowflake Cortex AI
    
    Args:
        file_name: Name of the PDF file
        model_name: Cortex model identifier
        stage_name: Stage where PDF is located
        
    Returns:
        Analysis results dictionary
    """
    try:
        # Get text from PDF
        text_result = session.sql(f"""
            SELECT EXTRACTED_TEXT 
            FROM {TEXT_TABLE} 
            WHERE FILE_NAME = '{file_name}'
            ORDER BY PAGE_NUMBER
            LIMIT 5
        """).collect()
        
        if not text_result:
            return None
        
        # Combine text from multiple pages
        combined_text = " ".join([row['EXTRACTED_TEXT'][:1000] for row in text_result])
        
        # Create prompt
        prompt = f"{ANALYSIS_PROMPT}\n\nContent to analyze:\n{combined_text}"
        
        # Escape single quotes for SQL
        prompt_escaped = prompt.replace("'", "''")
        
        # Call Cortex Complete API using SQL
        cortex_query = f"""
            SELECT SNOWFLAKE.CORTEX.COMPLETE(
                '{model_name}',
                '{prompt_escaped}'
            ) AS RESPONSE
        """
        
        response_result = session.sql(cortex_query).collect()
        response = response_result[0]['RESPONSE'] if response_result else ""
        
        # Parse response
        try:
            # Try to extract JSON from response
            if '{' in response:
                json_start = response.index('{')
                json_end = response.rindex('}') + 1
                json_str = response[json_start:json_end]
                analysis_json = json.loads(json_str)
            else:
                # Create default response
                analysis_json = {
                    "for_sale_sign": {"detected": False, "confidence": 0, "description": "Could not parse"},
                    "solar_panels": {"detected": False, "confidence": 0, "description": "Could not parse"},
                    "human_presence": {"detected": False, "confidence": 0, "description": "Could not parse"},
                    "potential_damage": {"detected": False, "confidence": 0, "description": "Could not parse"}
                }
        except:
            analysis_json = {
                "for_sale_sign": {"detected": False, "confidence": 0, "description": response[:200]},
                "solar_panels": {"detected": False, "confidence": 0, "description": ""},
                "human_presence": {"detected": False, "confidence": 0, "description": ""},
                "potential_damage": {"detected": False, "confidence": 0, "description": ""}
            }
        
        # Save results
        save_analysis_results(file_name, file_name, model_name, 1, analysis_json, response)
        
        return analysis_json
        
    except Exception as e:
        st.error(f"Error in Cortex analysis: {str(e)}")
        return None

def save_analysis_results(file_name, image_name, model_name, page_number, analysis_json, full_text):
    """
    Save analysis results to Snowflake table
    """
    try:
        for_sale = analysis_json.get("for_sale_sign", {})
        solar = analysis_json.get("solar_panels", {})
        human = analysis_json.get("human_presence", {})
        damage = analysis_json.get("potential_damage", {})
        
        query = f"""
        INSERT INTO {ANALYSIS_TABLE} (
            FILE_NAME, IMAGE_NAME, MODEL_NAME, PAGE_NUMBER,
            FOR_SALE_SIGN_DETECTED, FOR_SALE_SIGN_CONFIDENCE,
            SOLAR_PANEL_DETECTED, SOLAR_PANEL_CONFIDENCE,
            HUMAN_PRESENCE_DETECTED, HUMAN_PRESENCE_CONFIDENCE,
            POTENTIAL_DAMAGE_DETECTED, POTENTIAL_DAMAGE_CONFIDENCE,
            DAMAGE_DESCRIPTION, FULL_ANALYSIS_TEXT
        )
        VALUES (
            '{file_name}', '{image_name}', '{model_name}', {page_number},
            {str(for_sale.get('detected', False)).upper()}, {for_sale.get('confidence', 0)},
            {str(solar.get('detected', False)).upper()}, {solar.get('confidence', 0)},
            {str(human.get('detected', False)).upper()}, {human.get('confidence', 0)},
            {str(damage.get('detected', False)).upper()}, {damage.get('confidence', 0)},
            '{damage.get('description', '').replace("'", "''")}',
            '{full_text[:500].replace("'", "''")}'
        )
        """
        
        session.sql(query).collect()
        return True
        
    except Exception as e:
        st.error(f"Error saving analysis: {str(e)}")
        return False

# ================================================================
# STREAMLIT UI
# ================================================================

# Page Configuration
st.set_page_config(
    page_title="PDF Processing & Image Analysis",
    page_icon="📄",
    layout="wide"
)

# Title and Description
st.title("📄 PDF Processing & Image Analysis")
st.markdown("""
This application extracts text from PDF files using **Snowflake UDFs** and **Cortex AI models** for analysis.
All processing happens within Snowflake - no external libraries required!
""")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.subheader("Snowflake Objects")
    st.info(f"""
    **Database:** `{DATABASE}`  
    **Schema:** `{SCHEMA}`  
    **Text Table:** `{TEXT_TABLE}`  
    **Analysis Table:** `{ANALYSIS_TABLE}`  
    **PDF Stage:** `{PDF_STAGE}`
    """)
    
    st.subheader("Model Selection")
    selected_model_name = st.selectbox(
        "Choose AI Model",
        list(AVAILABLE_MODELS.keys()),
        help="Select the Cortex AI model for analysis"
    )
    selected_model = AVAILABLE_MODELS[selected_model_name]
    
    st.subheader("Analysis Categories")
    st.markdown("""
    - 🏠 For Sale Signs
    - ☀️ Solar Panels
    - 👥 Human Presence
    - ⚠️ Potential Damage
    """)

# Main Content Area
tab1, tab2, tab3 = st.tabs(["📤 Upload & Process", "📊 View Results", "🔍 Analysis Results"])

# ================================================================
# TAB 1: UPLOAD & PROCESS
# ================================================================
with tab1:
    st.header("Upload PDF File")
    
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Select a PDF file to process"
    )
    
    if uploaded_file is not None:
        st.success(f"✅ File uploaded: **{uploaded_file.name}**")
        
        # Upload to stage button
        if st.button("📤 Upload to Snowflake Stage", use_container_width=True):
            with st.spinner(f"Uploading {uploaded_file.name} to Snowflake..."):
                if upload_pdf_to_stage(uploaded_file, PDF_STAGE):
                    st.success("✅ File uploaded to Snowflake stage successfully!")
                    st.session_state['current_file'] = uploaded_file.name
        
        # If file is uploaded to stage, show processing options
        if 'current_file' in st.session_state:
            st.divider()
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔤 Extract Text", use_container_width=True):
                    with st.spinner("Extracting text using Snowflake UDF..."):
                        text = extract_text_from_pdf_udf(st.session_state['current_file'], PDF_STAGE)
                        
                        if text and not text.startswith("Error"):
                            # Save to table
                            if save_text_to_table(st.session_state['current_file'], text):
                                st.success("✅ Text extracted and saved to Snowflake!")
                                
                                # Preview
                                with st.expander("Preview Extracted Text"):
                                    st.text_area("Text", text[:2000], height=300)
                        else:
                            st.error(f"Failed to extract text: {text}")
            
            with col2:
                if st.button("🖼️ Get Image Info", use_container_width=True):
                    with st.spinner("Getting image count..."):
                        count = get_pdf_image_count_udf(st.session_state['current_file'], PDF_STAGE)
                        st.info(f"Found **{count}** images in PDF")
                        
                        if count > 0:
                            st.warning("Note: Image extraction requires manual processing. Use Cortex AI to analyze PDF content.")
            
            # Analyze button
            st.divider()
            st.subheader("🤖 Analyze PDF with Cortex AI")
            
            if st.button("▶️ Run Analysis", type="primary", use_container_width=True):
                with st.spinner(f"Analyzing with {selected_model_name}..."):
                    results = analyze_pdf_with_cortex(
                        st.session_state['current_file'],
                        selected_model,
                        PDF_STAGE
                    )
                    
                    if results:
                        st.success("✅ Analysis complete!")
                        
                        # Show results
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            for_sale = results.get("for_sale_sign", {})
                            if for_sale.get("detected"):
                                st.metric("🏠 For Sale Sign", "YES", f"{for_sale.get('confidence', 0)}%")
                        
                        with col2:
                            solar = results.get("solar_panels", {})
                            if solar.get("detected"):
                                st.metric("☀️ Solar Panels", "YES", f"{solar.get('confidence', 0)}%")
                        
                        with col3:
                            human = results.get("human_presence", {})
                            if human.get("detected"):
                                st.metric("👥 Human Presence", "YES", f"{human.get('confidence', 0)}%")
                        
                        with col4:
                            damage = results.get("potential_damage", {})
                            if damage.get("detected"):
                                st.metric("⚠️ Potential Damage", "YES", f"{damage.get('confidence', 0)}%")

# ================================================================
# TAB 2: VIEW RESULTS
# ================================================================
with tab2:
    st.header("📊 Processing Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 Extracted Text")
        
        # Query text data
        try:
            text_df = session.sql(f"SELECT * FROM {TEXT_TABLE} ORDER BY UPLOAD_TIMESTAMP DESC LIMIT 100").to_pandas()
            
            if not text_df.empty:
                st.metric("Total Text Records", len(text_df))
                st.dataframe(text_df, use_container_width=True, height=400)
                
                # Download option
                csv = text_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Text Data",
                    data=csv,
                    file_name=f"extracted_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No text data available. Upload and process a PDF first.")
        except Exception as e:
            st.error(f"Error loading text data: {str(e)}")
    
    with col2:
        st.subheader("📁 PDF Files")
        
        # List files in stage
        try:
            stage_result = session.sql(f"LIST @{PDF_STAGE}").collect()
            
            if stage_result:
                file_list = []
                for row in stage_result:
                    file_list.append({
                        'name': row['name'].split('/')[-1],
                        'size': f"{row['size'] / 1024:.2f} KB",
                        'last_modified': row['last_modified']
                    })
                
                file_df = pd.DataFrame(file_list)
                st.metric("Total PDF Files", len(file_df))
                st.dataframe(file_df, use_container_width=True, height=400)
            else:
                st.info("No files in stage. Upload a PDF first.")
        except Exception as e:
            st.error(f"Error listing stage: {str(e)}")

# ================================================================
# TAB 3: ANALYSIS RESULTS
# ================================================================
with tab3:
    st.header("🔍 Analysis Results")
    
    # Query analysis data
    try:
        analysis_df = session.sql(f"""
            SELECT 
                FILE_NAME,
                IMAGE_NAME,
                MODEL_NAME,
                PAGE_NUMBER,
                FOR_SALE_SIGN_DETECTED,
                FOR_SALE_SIGN_CONFIDENCE,
                SOLAR_PANEL_DETECTED,
                SOLAR_PANEL_CONFIDENCE,
                HUMAN_PRESENCE_DETECTED,
                HUMAN_PRESENCE_CONFIDENCE,
                POTENTIAL_DAMAGE_DETECTED,
                POTENTIAL_DAMAGE_CONFIDENCE,
                DAMAGE_DESCRIPTION,
                ANALYSIS_TIMESTAMP
            FROM {ANALYSIS_TABLE}
            ORDER BY ANALYSIS_TIMESTAMP DESC
        """).to_pandas()
        
        if not analysis_df.empty:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                for_sale_count = analysis_df['FOR_SALE_SIGN_DETECTED'].sum()
                st.metric("🏠 For Sale Signs", int(for_sale_count))
            
            with col2:
                solar_count = analysis_df['SOLAR_PANEL_DETECTED'].sum()
                st.metric("☀️ Solar Panels", int(solar_count))
            
            with col3:
                human_count = analysis_df['HUMAN_PRESENCE_DETECTED'].sum()
                st.metric("👥 Human Presence", int(human_count))
            
            with col4:
                damage_count = analysis_df['POTENTIAL_DAMAGE_DETECTED'].sum()
                st.metric("⚠️ Potential Damage", int(damage_count))
            
            st.divider()
            
            # Detailed results
            st.subheader("Detailed Analysis Results")
            st.dataframe(analysis_df, use_container_width=True, height=400)
            
            # Download option
            csv = analysis_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Analysis Results",
                data=csv,
                file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No analysis results available. Process a PDF and run analysis first.")
            
    except Exception as e:
        st.error(f"Error loading analysis results: {str(e)}")

# Footer
st.divider()
st.markdown("""
---
**PDF Processing & Image Analysis** | Powered by Snowflake Cortex AI  
Uses Snowflake UDFs (PyPDF2) for PDF processing - No external dependencies!
""")
