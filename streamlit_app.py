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
    "GPT-5 (OpenAI)": "openai-gpt-5",
    "Pixtral Large (Mistral)": "pixtral-large"
}

# Default Analysis Categories
DEFAULT_CATEGORIES = [
    {"id": "for_sale_sign", "name": "For Sale Sign", "description": "Is there a 'For Sale' sign visible?"},
    {"id": "solar_panels", "name": "Solar Panels", "description": "Are there solar panels installed on the property?"},
    {"id": "human_presence", "name": "Human Presence", "description": "Are there any people visible?"},
    {"id": "potential_damage", "name": "Potential Damage", "description": "Is there any visible damage to the property (roof damage, broken windows, structural issues, etc.)?"}
]

def build_analysis_prompt(categories):
    """Build analysis prompt dynamically based on selected categories"""
    category_text = ""
    for idx, cat in enumerate(categories, 1):
        category_text += f"{idx}. **{cat['name']}**: {cat['description']}\n"
    
    json_structure = "{\n"
    json_structure += '    "is_property_image": {\n'
    json_structure += '        "detected": true/false,\n'
    json_structure += '        "confidence": 0-100,\n'
    json_structure += '        "description": "..."\n'
    json_structure += '    },\n'
    for cat in categories:
        json_structure += f'    "{cat["id"]}": {{\n'
        json_structure += '        "detected": true/false,\n'
        json_structure += '        "confidence": 0-100,\n'
        json_structure += '        "description": "..."\n'
        json_structure += '    },\n'
    json_structure = json_structure.rstrip(',\n') + '\n}'
    
    prompt = f"""
IMPORTANT: First determine if this is an actual house or property image. 
- DO NOT analyze logos, company logos, brand marks, maps, diagrams, charts, or non-property images.
- ONLY analyze if this is a photograph or rendering of an actual residential or commercial property/building.

If this is NOT a property image (e.g., it's a logo, map, diagram, or text page), return:
{{
    "is_property_image": {{"detected": false, "confidence": 95, "description": "This is a [logo/map/diagram/etc], not a property image"}},
    ... (set all other categories to false with 0 confidence)
}}

If this IS a property or house image, analyze it for the following categories:

{category_text}

For each category, provide:
- A YES/NO answer
- Confidence level (0-100%)
- Brief description of what you observed

Format your response as JSON with this structure:
{json_structure}

If this is a text page from a PDF, analyze the text content for mentions of these categories.
"""
    return prompt

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

# Initialize session state for categories
if 'analysis_categories' not in st.session_state:
    st.session_state['analysis_categories'] = DEFAULT_CATEGORIES.copy()

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
                                
                                # Save to temporary file
                                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp_file:
                                    tmp_file.write(data)
                                    tmp_path = tmp_file.name
                                
                                try:
                                    # Upload to Snowflake stage
                                    stage_path = f"@{DATABASE}.{SCHEMA}.{IMAGE_STAGE}"
                                    
                                    # Create a meaningful filename
                                    base_name = file_name.replace('.pdf', '').replace(' ', '_')
                                    image_filename = f"{base_name}_page{page_num}_img{image_counter}.{ext}"
                                    
                                    put_result = session.file.put(
                                        tmp_path,
                                        stage_path,
                                        auto_compress=False,
                                        overwrite=True
                                    )
                                    
                                    # Get the actual uploaded filename from PUT result
                                    if put_result and len(put_result) > 0:
                                        uploaded_filename = put_result[0].target
                                        # Extract just the filename without path
                                        actual_image_name = uploaded_filename.split('/')[-1]
                                        extracted_images.append(actual_image_name)
                                        st.info(f"✅ Uploaded image {image_counter}: {actual_image_name}")
                                    else:
                                        st.warning(f"⚠️ Could not confirm upload for image {image_counter}")
                                finally:
                                    # Clean up temp file
                                    if os.path.exists(tmp_path):
                                        os.unlink(tmp_path)
                                        
                            except Exception as img_error:
                                st.warning(f"Could not extract image {image_counter} from page {page_num}: {str(img_error)}")
                                continue
        
        # Summary
        if extracted_images:
            st.success(f"📊 Extraction Summary: {len(extracted_images)} images extracted from {len(reader.pages)} pages")
        else:
            st.warning(f"⚠️ No images found in PDF ({len(reader.pages)} pages scanned)")
        
        return extracted_images
    except Exception as e:
        st.error(f"Error extracting images: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
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

def analyze_pdf_with_cortex(file_name, model_name, stage_name, categories):
    """
    Analyze PDF content using Snowflake Cortex AI
    
    Args:
        file_name: Name of the PDF file
        model_name: Cortex model identifier
        stage_name: Stage where PDF is located
        categories: List of analysis categories
        
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
        
        # Create prompt with dynamic categories
        analysis_prompt = build_analysis_prompt(categories)
        prompt = f"{analysis_prompt}\n\nContent to analyze:\n{combined_text}"
        
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
                # Create default response with all categories
                analysis_json = {}
                for cat in categories:
                    analysis_json[cat['id']] = {"detected": False, "confidence": 0, "description": "Could not parse"}
        except Exception as parse_error:
            st.warning(f"Could not parse JSON response: {str(parse_error)}")
            analysis_json = {}
            for cat in categories:
                analysis_json[cat['id']] = {"detected": False, "confidence": 0, "description": response[:200] if cat == categories[0] else ""}
        
        # Save results
        save_analysis_results(file_name, file_name, model_name, 1, analysis_json, response)
        
        return analysis_json
        
    except Exception as e:
        st.error(f"Error in Cortex analysis: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return None

def analyze_images_with_cortex(file_name, image_files, model_name, categories, batch_size=5):
    """
    Analyze extracted images using Snowflake Cortex AI vision models (batch processing)
    
    Args:
        file_name: Name of the PDF file
        image_files: List of extracted image file names
        model_name: Cortex model identifier
        categories: List of analysis categories
        batch_size: Number of images to process in parallel (default: 5)
        
    Returns:
        List of analysis results for each image
    """
    all_results = []
    
    try:
        from snowflake.snowpark.functions import col, lit, call_function
        import concurrent.futures
        from threading import Lock
        
        # Create progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_lock = Lock()
        
        # Build prompt with dynamic categories
        analysis_prompt = build_analysis_prompt(categories)
        prompt_escaped = analysis_prompt.replace("'", "''")
        model_escaped = model_name.replace("'", "''")
        
        def analyze_single_image(img_data):
            """Analyze a single image"""
            img_idx, image_name = img_data
            try:
                # Call COMPLETE with model, prompt, and TO_FILE for image
                response_result = session.sql(f"""
                    SELECT SNOWFLAKE.CORTEX.COMPLETE(
                        '{model_escaped}',
                        '{prompt_escaped}',
                        TO_FILE('@{DATABASE}.{SCHEMA}.{IMAGE_STAGE}', '{image_name}')
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
                        analysis_json = {}
                        for cat in categories:
                            analysis_json[cat['id']] = {"detected": False, "confidence": 0, "description": "Could not parse"}
                except Exception as parse_error:
                    analysis_json = {}
                    for cat in categories:
                        analysis_json[cat['id']] = {"detected": False, "confidence": 0, "description": response[:200] if cat == categories[0] else ""}
                
                # Save results
                save_analysis_results(file_name, image_name, model_name, img_idx, analysis_json, response)
                
                return (img_idx, image_name, analysis_json, None)
                
            except Exception as img_error:
                import traceback
                return (img_idx, image_name, None, f"{str(img_error)}\n{traceback.format_exc()}")
        
        # Process images in batches
        total_images = len(image_files)
        completed = 0
        
        # Create list of (index, image_name) tuples
        image_data = [(idx + 1, img) for idx, img in enumerate(image_files)]
        
        # Process in batches using ThreadPoolExecutor
        for batch_start in range(0, total_images, batch_size):
            batch_end = min(batch_start + batch_size, total_images)
            batch = image_data[batch_start:batch_end]
            
            status_text.text(f"Processing batch {batch_start//batch_size + 1} ({batch_start + 1}-{batch_end} of {total_images} images)...")
            
            # Process batch in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                batch_results = list(executor.map(analyze_single_image, batch))
            
            # Collect results
            for img_idx, image_name, analysis_json, error in batch_results:
                if error:
                    st.warning(f"⚠️ Error analyzing {image_name}: {error}")
                else:
                    all_results.append((img_idx, image_name, analysis_json))
                
                completed += 1
                progress_bar.progress(completed / total_images)
        
        status_text.text(f"✅ Completed analysis of {len(all_results)} images!")
        
        return all_results
        
    except Exception as e:
        st.error(f"Error in image analysis: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def save_analysis_results(file_name, image_name, model_name, page_number, analysis_json, full_text):
    """
    Save analysis results to Snowflake table
    Stores all categories (including custom ones) in METADATA field
    """
    try:
        # Get default categories for backward compatibility
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
        
        # Convert full analysis JSON to string for METADATA (stores ALL categories including custom)
        metadata_json = json.dumps(analysis_json)
        metadata_escaped = metadata_json.replace("'", "''")
        
        # Use explicit INSERT with column names
        # Store default categories in specific columns for easy querying
        # Store COMPLETE analysis (including custom categories) in METADATA using PARSE_JSON()
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
            '{damage_desc_escaped}', '{full_text_escaped}', PARSE_JSON('{metadata_escaped}')
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
    
    # Display current categories
    for cat in st.session_state['analysis_categories']:
        st.markdown(f"- **{cat['name']}**: {cat['description']}")
    
    # Add new category form
    with st.expander("➕ Add Custom Category"):
        with st.form("add_category_form"):
            new_cat_name = st.text_input("Category Name", placeholder="e.g., Pool Detected")
            new_cat_desc = st.text_area("Category Description", placeholder="e.g., Is there a swimming pool visible?")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Add Category", use_container_width=True):
                    if new_cat_name and new_cat_desc:
                        # Generate ID from name
                        cat_id = new_cat_name.lower().replace(" ", "_").replace("-", "_")
                        new_category = {
                            "id": cat_id,
                            "name": new_cat_name,
                            "description": new_cat_desc
                        }
                        st.session_state['analysis_categories'].append(new_category)
                        st.success(f"✅ Added category: {new_cat_name}")
                        st.rerun()
                    else:
                        st.error("Please fill in both name and description")
            
            with col2:
                if st.form_submit_button("Reset to Defaults", use_container_width=True):
                    st.session_state['analysis_categories'] = DEFAULT_CATEGORIES.copy()
                    st.success("✅ Reset to default categories")
                    st.rerun()

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
                        PDF_STAGE,
                        st.session_state['analysis_categories']
                    )
                    
                    if results:
                        st.success("✅ Text analysis complete!")
                        
                        # Show results dynamically based on categories
                        num_cols = min(len(st.session_state['analysis_categories']), 4)
                        cols = st.columns(num_cols)
                        
                        for idx, cat in enumerate(st.session_state['analysis_categories'][:num_cols]):
                            with cols[idx]:
                                cat_result = results.get(cat['id'], {})
                                if cat_result.get("detected"):
                                    st.metric(f"{cat['name']}", "YES", f"{cat_result.get('confidence', 0)}%")
        
        with col_b:
            if st.button("🖼️ Analyze Images (Batch)", use_container_width=True, type="primary"):
                if 'extracted_images' in st.session_state and st.session_state['extracted_images']:
                    # Add batch size selector
                    batch_size = st.slider("Batch Size (parallel processing)", min_value=1, max_value=10, value=5, 
                                          help="Number of images to process simultaneously")
                    
                    with st.spinner(f"Analyzing {len(st.session_state['extracted_images'])} images with {selected_model_name}..."):
                        results = analyze_images_with_cortex(
                            uploaded_file.name,
                            st.session_state['extracted_images'],
                            selected_model,
                            st.session_state['analysis_categories'],
                            batch_size
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
    
    # Query analysis data including METADATA for custom categories
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
                ANALYSIS_TIMESTAMP,
                METADATA
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
            
            # Detailed results with thumbnails
            st.subheader("Detailed Analysis Results")
            
            # Display results in a more visual format with thumbnails
            for idx, row in analysis_df.iterrows():
                with st.expander(f"📄 {row['FILE_NAME']} - Image: {row['IMAGE_NAME']} (Page {row['PAGE_NUMBER']})"):
                    col_img, col_data = st.columns([1, 3])
                    
                    with col_img:
                        # Display thumbnail
                        try:
                            # Get image from stage using GET_PRESIGNED_URL
                            image_url_query = f"""
                                SELECT GET_PRESIGNED_URL(@{DATABASE}.{SCHEMA}.{IMAGE_STAGE}, '{row['IMAGE_NAME']}', 3600) AS URL
                            """
                            url_result = session.sql(image_url_query).collect()
                            
                            if url_result and url_result[0]['URL']:
                                image_url = url_result[0]['URL']
                                st.image(image_url, caption=row['IMAGE_NAME'], use_container_width=True)
                            else:
                                st.info("🖼️ Image thumbnail not available")
                        except Exception as img_error:
                            st.warning(f"Could not load thumbnail: {str(img_error)}")
                            st.info("🖼️ Image thumbnail not available")
                    
                    with col_data:
                        st.markdown(f"**Model:** {row['MODEL_NAME']}")
                        st.markdown(f"**Analysis Time:** {row['ANALYSIS_TIMESTAMP']}")
                        
                        # Display detection results - use METADATA if available (contains all categories)
                        st.markdown("#### Detection Results:")
                        
                        # Try to parse METADATA for all categories (including custom)
                        all_categories = {}
                        if pd.notna(row['METADATA']) and row['METADATA']:
                            try:
                                if isinstance(row['METADATA'], str):
                                    all_categories = json.loads(row['METADATA'])
                                elif isinstance(row['METADATA'], dict):
                                    all_categories = row['METADATA']
                            except:
                                pass
                        
                        # Display all categories from METADATA
                        if all_categories:
                            # Check if it's a property image first
                            is_property = all_categories.get('is_property_image', {})
                            if is_property and not is_property.get('detected', True):
                                st.warning(f"⚠️ Not a property image: {is_property.get('description', 'N/A')}")
                            
                            # Display all other categories dynamically
                            category_items = [(k, v) for k, v in all_categories.items() if k != 'is_property_image']
                            
                            # Display in rows of 4
                            for i in range(0, len(category_items), 4):
                                result_cols = st.columns(min(4, len(category_items) - i))
                                for col_idx, (cat_id, cat_data) in enumerate(category_items[i:i+4]):
                                    with result_cols[col_idx]:
                                        detected = cat_data.get('detected', False)
                                        confidence = cat_data.get('confidence', 0)
                                        # Format category name nicely
                                        cat_name = cat_id.replace('_', ' ').title()
                                        
                                        if detected:
                                            st.success(f"✓ {cat_name}: YES ({confidence:.0f}%)")
                                        else:
                                            st.info(f"✗ {cat_name}: NO ({confidence:.0f}%)")
                                        
                                        # Show description if available
                                        desc = cat_data.get('description', '')
                                        if desc and len(desc) > 0:
                                            st.caption(desc[:100])
                        else:
                            # Fallback to default columns if METADATA not available
                            result_cols = st.columns(4)
                            with result_cols[0]:
                                if row['FOR_SALE_SIGN_DETECTED']:
                                    st.success(f"🏠 For Sale: YES ({row['FOR_SALE_SIGN_CONFIDENCE']:.0f}%)")
                                else:
                                    st.info(f"🏠 For Sale: NO ({row['FOR_SALE_SIGN_CONFIDENCE']:.0f}%)")
                            
                            with result_cols[1]:
                                if row['SOLAR_PANEL_DETECTED']:
                                    st.success(f"☀️ Solar: YES ({row['SOLAR_PANEL_CONFIDENCE']:.0f}%)")
                                else:
                                    st.info(f"☀️ Solar: NO ({row['SOLAR_PANEL_CONFIDENCE']:.0f}%)")
                            
                            with result_cols[2]:
                                if row['HUMAN_PRESENCE_DETECTED']:
                                    st.success(f"👥 Human: YES ({row['HUMAN_PRESENCE_CONFIDENCE']:.0f}%)")
                                else:
                                    st.info(f"👥 Human: NO ({row['HUMAN_PRESENCE_CONFIDENCE']:.0f}%)")
                            
                            with result_cols[3]:
                                if row['POTENTIAL_DAMAGE_DETECTED']:
                                    st.warning(f"⚠️ Damage: YES ({row['POTENTIAL_DAMAGE_CONFIDENCE']:.0f}%)")
                                else:
                                    st.info(f"⚠️ Damage: NO ({row['POTENTIAL_DAMAGE_CONFIDENCE']:.0f}%)")
                            
                            if row['DAMAGE_DESCRIPTION']:
                                st.markdown(f"**Damage Description:** {row['DAMAGE_DESCRIPTION']}")
            
            st.divider()
            
            # Also show tabular view
            st.subheader("Tabular View")
            st.dataframe(analysis_df, use_container_width=True, height=300)
            
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
