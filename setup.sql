-- ================================================================
-- Snowflake Setup Script for PDF Processing Application
-- FOR STREAMLIT IN SNOWFLAKE (SiS)
-- ================================================================
-- This script creates the necessary Snowflake objects for the
-- PDF processing and image analysis application using ONLY
-- Snowflake-native capabilities and UDFs.
-- ================================================================

-- Step 1: Create Database and Schema
-- ================================================================
CREATE DATABASE IF NOT EXISTS PDF_ANALYTICS_DB
    COMMENT = 'Database for PDF processing and image analysis';

USE DATABASE PDF_ANALYTICS_DB;

CREATE SCHEMA IF NOT EXISTS PDF_PROCESSING
    COMMENT = 'Schema for PDF text extraction and image analysis';

USE SCHEMA PDF_PROCESSING;

-- Step 2: Create Table for Extracted Text
-- ================================================================
CREATE OR REPLACE TABLE PDF_TEXT_DATA (
    ID NUMBER AUTOINCREMENT PRIMARY KEY,
    FILE_NAME STRING NOT NULL,
    PAGE_NUMBER NUMBER NOT NULL,
    EXTRACTED_TEXT STRING,
    UPLOAD_TIMESTAMP TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    METADATA VARIANT
) COMMENT = 'Stores extracted text from PDF files';

-- Step 3: Create Table for Image Analysis Results
-- ================================================================
CREATE OR REPLACE TABLE IMAGE_ANALYSIS_RESULTS (
    ID NUMBER AUTOINCREMENT PRIMARY KEY,
    FILE_NAME STRING NOT NULL,
    IMAGE_NAME STRING NOT NULL,
    MODEL_NAME STRING NOT NULL,
    PAGE_NUMBER NUMBER,
    FOR_SALE_SIGN_DETECTED BOOLEAN,
    FOR_SALE_SIGN_CONFIDENCE FLOAT,
    SOLAR_PANEL_DETECTED BOOLEAN,
    SOLAR_PANEL_CONFIDENCE FLOAT,
    HUMAN_PRESENCE_DETECTED BOOLEAN,
    HUMAN_PRESENCE_CONFIDENCE FLOAT,
    POTENTIAL_DAMAGE_DETECTED BOOLEAN,
    POTENTIAL_DAMAGE_CONFIDENCE FLOAT,
    DAMAGE_DESCRIPTION STRING,
    FULL_ANALYSIS_TEXT STRING,
    ANALYSIS_TIMESTAMP TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    METADATA STRING
) COMMENT = 'Stores image analysis results from Cortex AI models';

-- Step 4: Create Internal Stage for Images
-- ================================================================
-- Must use Snowflake-managed encryption (not client-side) for TO_FILE with COMPLETE
CREATE OR REPLACE STAGE PDF_IMAGES_STAGE
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    DIRECTORY = ( ENABLE = TRUE )
    COMMENT = 'Stage for storing extracted images from PDFs';

-- Step 5: Create Internal Stage for PDF Files
-- ================================================================
CREATE OR REPLACE STAGE PDF_FILES_STAGE
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    DIRECTORY = ( ENABLE = TRUE )
    COMMENT = 'Stage for storing uploaded PDF files';

-- Step 6: Create File Format for CSV Export (Optional)
-- ================================================================
CREATE OR REPLACE FILE FORMAT CSV_FORMAT
    TYPE = 'CSV'
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    COMPRESSION = 'NONE';

-- Step 7: Grant Necessary Permissions
-- ================================================================
-- Note: Adjust role names based on your Snowflake account setup
-- GRANT USAGE ON DATABASE PDF_ANALYTICS_DB TO ROLE <YOUR_ROLE>;
-- GRANT USAGE ON SCHEMA PDF_PROCESSING TO ROLE <YOUR_ROLE>;
-- GRANT SELECT, INSERT, UPDATE ON TABLE PDF_TEXT_DATA TO ROLE <YOUR_ROLE>;
-- GRANT SELECT, INSERT, UPDATE ON TABLE IMAGE_ANALYSIS_RESULTS TO ROLE <YOUR_ROLE>;
-- GRANT READ, WRITE ON STAGE PDF_IMAGES_STAGE TO ROLE <YOUR_ROLE>;
-- GRANT READ, WRITE ON STAGE PDF_FILES_STAGE TO ROLE <YOUR_ROLE>;

-- Step 8: Create View for Latest Analysis Results
-- ================================================================
CREATE OR REPLACE VIEW VW_LATEST_IMAGE_ANALYSIS AS
SELECT 
    FILE_NAME,
    IMAGE_NAME,
    MODEL_NAME,
    PAGE_NUMBER,
    FOR_SALE_SIGN_DETECTED,
    SOLAR_PANEL_DETECTED,
    HUMAN_PRESENCE_DETECTED,
    POTENTIAL_DAMAGE_DETECTED,
    DAMAGE_DESCRIPTION,
    ANALYSIS_TIMESTAMP
FROM IMAGE_ANALYSIS_RESULTS
QUALIFY ROW_NUMBER() OVER (PARTITION BY FILE_NAME, IMAGE_NAME ORDER BY ANALYSIS_TIMESTAMP DESC) = 1
ORDER BY ANALYSIS_TIMESTAMP DESC;

-- Step 9: Create Python UDF for PDF Text Extraction
-- ================================================================
CREATE OR REPLACE FUNCTION EXTRACT_PDF_TEXT(file_path STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
HANDLER = 'extract_text'
PACKAGES = ('pypdf2', 'requests')
AS
$$
import PyPDF2
import sys
import io
import requests

def extract_text(file_path):
    try:
        # Use requests to fetch the scoped file URL
        response = requests.get(file_path)
        response.raise_for_status()
        pdf_data = response.content
        pdf_file = io.BytesIO(pdf_data)
        
        reader = PyPDF2.PdfReader(pdf_file)
        text = ''
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += f'--- Page {page_num + 1} ---\n'
            text += page.extract_text()
            text += '\n\n'
        return text
    except Exception as e:
        return f'Error extracting text: {str(e)}'
$$;

-- Step 10: Create Python UDF for PDF Image Extraction Info
-- ================================================================
CREATE OR REPLACE FUNCTION GET_PDF_IMAGE_COUNT(file_path STRING)
RETURNS NUMBER
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
HANDLER = 'count_images'
PACKAGES = ('pypdf2', 'requests')
AS
$$
import PyPDF2
import io
import requests

def count_images(file_path):
    try:
        # Use requests to fetch the scoped file URL
        response = requests.get(file_path)
        response.raise_for_status()
        pdf_data = response.content
        pdf_file = io.BytesIO(pdf_data)
        
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
        return 0
$$;

-- Step 11: Verify Setup
-- ================================================================
-- Show all created objects
SHOW TABLES IN SCHEMA PDF_PROCESSING;
SHOW STAGES IN SCHEMA PDF_PROCESSING;
SHOW VIEWS IN SCHEMA PDF_PROCESSING;
SHOW FUNCTIONS IN SCHEMA PDF_PROCESSING;

-- Display sample queries
SELECT 'Setup completed successfully!' AS STATUS;
SELECT COUNT(*) AS TEXT_RECORDS FROM PDF_TEXT_DATA;
SELECT COUNT(*) AS ANALYSIS_RECORDS FROM IMAGE_ANALYSIS_RESULTS;

-- ================================================================
-- END OF SETUP SCRIPT
-- ================================================================

