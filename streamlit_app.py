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
# PAGE CONFIGURATION - MUST BE FIRST STREAMLIT COMMAND
# ================================================================

st.set_page_config(
    page_title="PDF Processing & Image Analysis",
    page_icon="📄",
    layout="wide"
)

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

# Set context - use fully qualified names instead of USE statements
# USE DATABASE/SCHEMA not supported in SiS, so we'll use fully qualified table names throughout

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
        import tempfile
        import os
        
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Upload using PUT command via SQL
            stage_path = f"@{DATABASE}.{SCHEMA}.{stage_name}"
            
            # Use PUT command through session.sql
            # Note: PUT command returns to local result set, not stage
            put_result = session.file.put(
                tmp_path,
                stage_path,
                auto_compress=False,
                overwrite=True
            )
            
            return True
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        st.error(f"Error uploading file: {str(e)}")
        return False

def extract_text_from_pdf_bytes(pdf_bytes, file_name):
    """
    Extract text from PDF bytes directly in Streamlit
    
    Args:
        pdf_bytes: PDF file as bytes
        file_name: Name of the PDF file (for reference)
        
    Returns:
        Extracted text string
    """
    try:
        import PyPDF2
        import io
        
        # Create a BytesIO object from the bytes
        pdf_file = io.BytesIO(pdf_bytes)
        
        # Read the PDF
        reader = PyPDF2.PdfReader(pdf_file)
        text = ''
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += f'--- Page {page_num + 1} ---\n'
            text += page.extract_text()
            text += '\n\n'
        
        return text if text.strip() else "No text could be extracted from PDF"
    except Exception as e:
        return f"Error: {str(e)}"

def get_pdf_image_count_bytes(pdf_bytes, file_name):
    """
    Get count of images in PDF from bytes directly in Streamlit
    
    Args:
        pdf_bytes: PDF file as bytes
        file_name: Name of the PDF file (for reference)
        
    Returns:
        Number of images in PDF
    """
    try:
        import PyPDF2
        import io
        
        # Create a BytesIO object from the bytes
        pdf_file = io.BytesIO(pdf_bytes)
        
        # Read the PDF
        reader = PyPDF2.PdfReader(pdf_file)
        image_count = 0
        
        for page in reader.pages:
            # Check if page has resources
            if '/Resources' in page:
                resources = page['/Resources']
                if '/XObject' in resources:
                    xObject = resources['/XObject']
                    if hasattr(xObject, 'get_object'):
                        xObject = xObject.get_object()
                    for obj_name in xObject:
                        obj = xObject[obj_name]
                        if hasattr(obj, 'get_object'):
                            obj = obj.get_object()
                        if '/Subtype' in obj and obj['/Subtype'] == '/Image':
                            image_count += 1
        
        return image_count
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
        from snowflake.snowpark import Row
        from snowflake.snowpark.functions import lit
        
        # Parse text by pages (if formatted with page markers)
        if '--- Page' in text:
            pages = text.split('--- Page')[1:]  # Skip first empty split
            rows_to_insert = []
            
            for page_content in pages:
                lines = page_content.split('\n', 1)
                if len(lines) >= 2:
                    try:
                        page_num = int(lines[0].strip().replace(' ---', ''))
                        page_text = lines[1].strip()
                        rows_to_insert.append((file_name, page_num, page_text, None))
                    except (ValueError, IndexError):
                        continue
            
            # Insert all rows using DataFrame API (safer than string concatenation)
            if rows_to_insert:
                df = session.create_dataframe(
                    rows_to_insert,
                    schema=["FILE_NAME", "PAGE_NUMBER", "EXTRACTED_TEXT", "METADATA"]
                )
                df.write.mode("append").save_as_table(f"{DATABASE}.{SCHEMA}.{TEXT_TABLE}")
        else:
            # Save as single page if no page markers
            df = session.create_dataframe(
                [(file_name, 1, text, None)],
                schema=["FILE_NAME", "PAGE_NUMBER", "EXTRACTED_TEXT", "METADATA"]
            )
            df.write.mode("append").save_as_table(f"{DATABASE}.{SCHEMA}.{TEXT_TABLE}")
        
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
        from snowflake.snowpark.functions import col, lit, call_function
        
        # Get text from PDF using DataFrame API (safer)
        text_df = session.table(f"{DATABASE}.{SCHEMA}.{TEXT_TABLE}") \
            .filter(col("FILE_NAME") == lit(file_name)) \
            .select("EXTRACTED_TEXT") \
            .order_by("PAGE_NUMBER") \
            .limit(5)
        
        text_result = text_df.collect()
        
        if not text_result:
            st.warning(f"No text found for file: {file_name}. Please extract text first.")
            return None
        
        # Combine text from multiple pages
        combined_text = " ".join([row['EXTRACTED_TEXT'][:1000] for row in text_result])
        
        # Create prompt
        prompt = f"{ANALYSIS_PROMPT}\n\nContent to analyze:\n{combined_text}"
        
        # Truncate prompt if too long (Cortex has token limits)
        if len(prompt) > 10000:
            prompt = prompt[:10000] + "\n\n[Content truncated due to length]"
        
        # Call Cortex Complete using Snowpark call_function
        # This is the recommended way to call Cortex functions from Python
        try:
            response_df = session.create_dataframe(
                [(1,)],  # Dummy row
                schema=["dummy"]
            ).select(
                call_function(
                    "SNOWFLAKE.CORTEX.COMPLETE",
                    lit(model_name),
                    lit(prompt)
                ).alias("RESPONSE")
            )
            
            response_result = response_df.collect()
            response = response_result[0]['RESPONSE'] if response_result else ""
        except Exception as cortex_error:
            st.error(f"Cortex API error: {str(cortex_error)}")
            st.info("Trying alternative SQL-based approach...")
            
            # Fallback: Use SQL string approach (properly escaped)
            # Note: This is less preferred but more compatible
            prompt_escaped = prompt.replace("'", "''").replace("\\", "\\\\")
            model_escaped = model_name.replace("'", "''")
            
            try:
                response_result = session.sql(f"""
                    SELECT SNOWFLAKE.CORTEX.COMPLETE(
                        '{model_escaped}',
                        '{prompt_escaped}'
                    ) AS RESPONSE
                """).collect()
                response = response_result[0]['RESPONSE'] if response_result else ""
            except Exception as fallback_error:
                st.error(f"Both Cortex approaches failed: {str(fallback_error)}")
                return None
        
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
        except Exception as parse_error:
            st.warning(f"Could not parse JSON response: {str(parse_error)}")
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
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
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
        
        # Prepare data using DataFrame API (safer than SQL string concatenation)
        data = [(
            file_name,
            image_name,
            model_name,
            page_number,
            for_sale.get('detected', False),
            float(for_sale.get('confidence', 0)),
            solar.get('detected', False),
            float(solar.get('confidence', 0)),
            human.get('detected', False),
            float(human.get('confidence', 0)),
            damage.get('detected', False),
            float(damage.get('confidence', 0)),
            damage.get('description', ''),
            full_text[:500]
        )]
        
        schema = [
            "FILE_NAME", "IMAGE_NAME", "MODEL_NAME", "PAGE_NUMBER",
            "FOR_SALE_SIGN_DETECTED", "FOR_SALE_SIGN_CONFIDENCE",
            "SOLAR_PANEL_DETECTED", "SOLAR_PANEL_CONFIDENCE",
            "HUMAN_PRESENCE_DETECTED", "HUMAN_PRESENCE_CONFIDENCE",
            "POTENTIAL_DAMAGE_DETECTED", "POTENTIAL_DAMAGE_CONFIDENCE",
            "DAMAGE_DESCRIPTION", "FULL_ANALYSIS_TEXT"
        ]
        
        df = session.create_dataframe(data, schema=schema)
        df.write.mode("append").save_as_table(f"{DATABASE}.{SCHEMA}.{ANALYSIS_TABLE}")
        
        return True
        
    except Exception as e:
        st.error(f"Error saving analysis: {str(e)}")
        return False

# ================================================================
# STREAMLIT UI
# ================================================================

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
        
        # Store PDF bytes in session state
        pdf_bytes = uploaded_file.getvalue()
        st.session_state['current_file'] = uploaded_file.name
        st.session_state['pdf_bytes'] = pdf_bytes
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔤 Extract Text", use_container_width=True):
                with st.spinner("Extracting text from PDF..."):
                    text = extract_text_from_pdf_bytes(pdf_bytes, uploaded_file.name)
                    
                    if text and not text.startswith("Error"):
                        # Save to table
                        if save_text_to_table(uploaded_file.name, text):
                            st.success("✅ Text extracted and saved to Snowflake!")
                            
                            # Preview
                            with st.expander("Preview Extracted Text"):
                                st.text_area("Text", text[:2000], height=300)
                    else:
                        st.error(f"Failed to extract text: {text}")
        
        with col2:
            if st.button("🖼️ Get Image Info", use_container_width=True):
                with st.spinner("Counting images..."):
                    count = get_pdf_image_count_bytes(pdf_bytes, uploaded_file.name)
                    st.info(f"Found **{count}** images in PDF")
                    
                    if count > 0:
                        st.warning("Note: Image extraction requires manual processing. Use Cortex AI to analyze PDF content.")
        
        # Analyze button
        st.divider()
        st.subheader("🤖 Analyze PDF with Cortex AI")
        
        if st.button("▶️ Run Analysis", type="primary", use_container_width=True):
            with st.spinner(f"Analyzing with {selected_model_name}..."):
                results = analyze_pdf_with_cortex(
                    uploaded_file.name,
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
            text_df = session.sql(f"SELECT * FROM {DATABASE}.{SCHEMA}.{TEXT_TABLE} ORDER BY UPLOAD_TIMESTAMP DESC LIMIT 100").to_pandas()
            
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
            stage_result = session.sql(f"LIST @{DATABASE}.{SCHEMA}.{PDF_STAGE}").collect()
            
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
            FROM {DATABASE}.{SCHEMA}.{ANALYSIS_TABLE}
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
