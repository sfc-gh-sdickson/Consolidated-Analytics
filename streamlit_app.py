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

def extract_images_from_pdf_bytes(pdf_bytes, file_name):
    """
    Extract images from PDF and save to Snowflake stage
    
    Args:
        pdf_bytes: PDF file as bytes
        file_name: Name of the PDF file (for reference)
        
    Returns:
        List of extracted image file names
    """
    try:
        import PyPDF2
        import io
        import tempfile
        import os
        from PIL import Image
        
        # Create a BytesIO object from the bytes
        pdf_file = io.BytesIO(pdf_bytes)
        
        # Read the PDF
        reader = PyPDF2.PdfReader(pdf_file)
        extracted_images = []
        image_counter = 0
        
        for page_num, page in enumerate(reader.pages, start=1):
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
                            image_counter += 1
                            
                            # Extract image data
                            try:
                                # Get image properties
                                size = (obj['/Width'], obj['/Height'])
                                data = obj.get_data()
                                
                                # Determine image format
                                if '/Filter' in obj:
                                    filter_type = obj['/Filter']
                                    if filter_type == '/DCTDecode':
                                        ext = 'jpg'
                                    elif filter_type == '/FlateDecode':
                                        ext = 'png'
                                    elif filter_type == '/JPXDecode':
                                        ext = 'jp2'
                                    else:
                                        ext = 'png'  # default
                                else:
                                    ext = 'png'
                                
                                # Create image file name
                                base_name = file_name.rsplit('.', 1)[0]
                                image_name = f"{base_name}_page{page_num}_img{image_counter}.{ext}"
                                
                                # Save to temporary file
                                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp_file:
                                    tmp_file.write(data)
                                    tmp_path = tmp_file.name
                                
                                try:
                                    # Upload to Snowflake stage
                                    stage_path = f"@{DATABASE}.{SCHEMA}.{IMAGE_STAGE}"
                                    session.file.put(
                                        tmp_path,
                                        stage_path,
                                        auto_compress=False,
                                        overwrite=True
                                    )
                                    extracted_images.append(image_name)
                                finally:
                                    # Clean up temp file
                                    if os.path.exists(tmp_path):
                                        os.unlink(tmp_path)
                                        
                            except Exception as img_error:
                                st.warning(f"Could not extract image {image_counter} from page {page_num}: {str(img_error)}")
                                continue
        
        return extracted_images
    except Exception as e:
        st.error(f"Error extracting images: {str(e)}")
        return []

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
            
            # Insert all rows using SQL INSERT with explicit column names
            if rows_to_insert:
                for file_name, page_num, page_text, metadata in rows_to_insert:
                    # Escape single quotes in text
                    page_text_escaped = page_text.replace("'", "''")
                    
                    query = f"""
                    INSERT INTO {DATABASE}.{SCHEMA}.{TEXT_TABLE} 
                    (FILE_NAME, PAGE_NUMBER, EXTRACTED_TEXT, METADATA)
                    VALUES ('{file_name}', {page_num}, '{page_text_escaped}', NULL)
                    """
                    session.sql(query).collect()
        else:
            # Save as single page if no page markers
            text_escaped = text.replace("'", "''")
            query = f"""
            INSERT INTO {DATABASE}.{SCHEMA}.{TEXT_TABLE} 
            (FILE_NAME, PAGE_NUMBER, EXTRACTED_TEXT, METADATA)
            VALUES ('{file_name}', 1, '{text_escaped}', NULL)
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

def analyze_images_with_cortex(file_name, image_files, model_name):
    """
    Analyze extracted images using Snowflake Cortex AI vision models
    
    Args:
        file_name: Name of the PDF file
        image_files: List of extracted image file names
        model_name: Cortex model identifier
        
    Returns:
        List of analysis results for each image
    """
    all_results = []
    
    try:
        from snowflake.snowpark.functions import col, lit, call_function
        
        for img_idx, image_name in enumerate(image_files, start=1):
            st.write(f"Analyzing image {img_idx}/{len(image_files)}: {image_name}")
            
            try:
                # Build scoped URL for the image
                image_url_query = f"""
                    SELECT BUILD_SCOPED_FILE_URL(@{DATABASE}.{SCHEMA}.{IMAGE_STAGE}, '{image_name}') AS IMAGE_URL
                """
                url_result = session.sql(image_url_query).collect()
                
                if not url_result:
                    st.warning(f"Could not get URL for {image_name}")
                    continue
                    
                image_url = url_result[0]['IMAGE_URL']
                
                # Call Cortex Complete with vision model using Snowflake array functions
                prompt = ANALYSIS_PROMPT
                prompt_escaped = prompt.replace("'", "''")
                model_escaped = model_name.replace("'", "''")
                
                # Use ARRAY_CONSTRUCT and OBJECT_CONSTRUCT for proper Snowflake syntax
                response_result = session.sql(f"""
                    SELECT SNOWFLAKE.CORTEX.COMPLETE(
                        '{model_escaped}',
                        ARRAY_CONSTRUCT(
                            OBJECT_CONSTRUCT(
                                'role', 'user',
                                'content', ARRAY_CONSTRUCT(
                                    OBJECT_CONSTRUCT('type', 'text', 'text', '{prompt_escaped}'),
                                    OBJECT_CONSTRUCT('type', 'image_url', 'image_url', '{image_url}')
                                )
                            )
                        )
                    ) AS RESPONSE
                """).collect()
                
                response = response_result[0]['RESPONSE'] if response_result else ""
                
                # Parse response
                try:
                    if '{' in response:
                        json_start = response.index('{')
                        json_end = response.rindex('}') + 1
                        json_str = response[json_start:json_end]
                        analysis_json = json.loads(json_str)
                    else:
                        analysis_json = {
                            "for_sale_sign": {"detected": False, "confidence": 0, "description": "Could not parse"},
                            "solar_panels": {"detected": False, "confidence": 0, "description": "Could not parse"},
                            "human_presence": {"detected": False, "confidence": 0, "description": "Could not parse"},
                            "potential_damage": {"detected": False, "confidence": 0, "description": "Could not parse"}
                        }
                except Exception as parse_error:
                    st.warning(f"Could not parse response for {image_name}: {str(parse_error)}")
                    analysis_json = {
                        "for_sale_sign": {"detected": False, "confidence": 0, "description": response[:200]},
                        "solar_panels": {"detected": False, "confidence": 0, "description": ""},
                        "human_presence": {"detected": False, "confidence": 0, "description": ""},
                        "potential_damage": {"detected": False, "confidence": 0, "description": ""}
                    }
                
                # Save results
                save_analysis_results(file_name, image_name, model_name, img_idx, analysis_json, response)
                all_results.append(analysis_json)
                
            except Exception as img_error:
                st.error(f"Error analyzing {image_name}: {str(img_error)}")
                import traceback
                st.error(f"Traceback: {traceback.format_exc()}")
                continue
        
        return all_results
        
    except Exception as e:
        st.error(f"Error in image analysis: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def save_analysis_results(file_name, image_name, model_name, page_number, analysis_json, full_text):
    """
    Save analysis results to Snowflake table
    """
    try:
        for_sale = analysis_json.get("for_sale_sign", {})
        solar = analysis_json.get("solar_panels", {})
        human = analysis_json.get("human_presence", {})
        damage = analysis_json.get("potential_damage", {})
        
        # Escape strings for SQL
        file_name_escaped = file_name.replace("'", "''")
        image_name_escaped = image_name.replace("'", "''")
        model_name_escaped = model_name.replace("'", "''")
        damage_desc_escaped = damage.get('description', '').replace("'", "''")
        full_text_escaped = full_text[:500].replace("'", "''")
        
        # Use explicit INSERT with column names
        query = f"""
        INSERT INTO {DATABASE}.{SCHEMA}.{ANALYSIS_TABLE} (
            FILE_NAME, IMAGE_NAME, MODEL_NAME, PAGE_NUMBER,
            FOR_SALE_SIGN_DETECTED, FOR_SALE_SIGN_CONFIDENCE,
            SOLAR_PANEL_DETECTED, SOLAR_PANEL_CONFIDENCE,
            HUMAN_PRESENCE_DETECTED, HUMAN_PRESENCE_CONFIDENCE,
            POTENTIAL_DAMAGE_DETECTED, POTENTIAL_DAMAGE_CONFIDENCE,
            DAMAGE_DESCRIPTION, FULL_ANALYSIS_TEXT, METADATA
        )
        VALUES (
            '{file_name_escaped}', '{image_name_escaped}', '{model_name_escaped}', {page_number},
            {str(for_sale.get('detected', False)).upper()}, {float(for_sale.get('confidence', 0))},
            {str(solar.get('detected', False)).upper()}, {float(solar.get('confidence', 0))},
            {str(human.get('detected', False)).upper()}, {float(human.get('confidence', 0))},
            {str(damage.get('detected', False)).upper()}, {float(damage.get('confidence', 0))},
            '{damage_desc_escaped}', '{full_text_escaped}', NULL
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
            if st.button("🖼️ Extract Images", use_container_width=True):
                with st.spinner("Extracting images from PDF..."):
                    extracted_images = extract_images_from_pdf_bytes(pdf_bytes, uploaded_file.name)
                    
                    if extracted_images:
                        st.success(f"✅ Extracted **{len(extracted_images)}** images!")
                        st.session_state['extracted_images'] = extracted_images
                        
                        with st.expander("Extracted Image Files"):
                            for img_name in extracted_images:
                                st.text(f"• {img_name}")
                    else:
                        st.warning("No images found or could not extract images from PDF")
        
        # Analyze buttons
        st.divider()
        st.subheader("🤖 Analyze with Cortex AI")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            if st.button("📝 Analyze Text Content", use_container_width=True):
                with st.spinner(f"Analyzing text with {selected_model_name}..."):
                    results = analyze_pdf_with_cortex(
                        uploaded_file.name,
                        selected_model,
                        PDF_STAGE
                    )
                    
                    if results:
                        st.success("✅ Text analysis complete!")
                        
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
        
        with col_b:
            if st.button("🖼️ Analyze Images", use_container_width=True, type="primary"):
                if 'extracted_images' in st.session_state and st.session_state['extracted_images']:
                    with st.spinner(f"Analyzing {len(st.session_state['extracted_images'])} images with {selected_model_name}..."):
                        results = analyze_images_with_cortex(
                            uploaded_file.name,
                            st.session_state['extracted_images'],
                            selected_model
                        )
                        
                        if results:
                            st.success(f"✅ Analyzed {len(results)} images!")
                            st.info("View detailed results in the 'Analysis Results' tab")
                else:
                    st.warning("⚠️ Please extract images first before analyzing them!")

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
